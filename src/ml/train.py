"""Training script for the DocXPilot Activity Autoencoder.

Trains a 1D convolutional autoencoder on sliding 28-day windows of
repository activity signals (real + synthetic), then saves:
  - src/ml/weights/activity_ae.pt   — model state dict
  - src/ml/weights/config.json      — normalization params, threshold,
                                      window size, training metadata

Split strategy: by repository (not by window) to prevent leakage between
neighboring windows from the same repo appearing in both train and val sets.

Usage:
    python src/ml/train.py

Optional flags:
    --epochs N     override max epochs (default 60)
    --seed N       random seed (default 42)
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Guards: require torch for training
# ---------------------------------------------------------------------------
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    _TORCH_AVAILABLE = True
except ImportError:
    torch = None          # type: ignore[assignment]
    nn = None             # type: ignore[assignment]
    DataLoader = None     # type: ignore[assignment]
    TensorDataset = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.model import ActivityAutoencoder, WINDOW_SIZE  # noqa: E402
from ml.synthetic import generate_dataset              # noqa: E402

WEIGHTS_DIR = Path(__file__).resolve().parent / "weights"
DATA_DIR    = Path(__file__).resolve().parent / "data"
SCRATCH_DIR = Path(__file__).resolve().parent / "training_logs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    if _TORCH_AVAILABLE and torch is not None:
        torch.manual_seed(seed)


def load_real_signals() -> list[np.ndarray]:
    """Load all .npy files from ml/data/."""
    signals = []
    for f in DATA_DIR.glob("*.npy"):
        try:
            arr = np.load(str(f))
            if arr.ndim == 2 and arr.shape[0] == 2 and arr.shape[1] >= WINDOW_SIZE * 2:
                signals.append(arr.astype(np.float32))
        except Exception as exc:
            print(f"  Warning: could not load {f.name}: {exc}")
    return signals


def normalize_signal(sig: np.ndarray) -> tuple[np.ndarray, float]:
    """Divide by 95th percentile of nonzero values, clip to 3.

    Args:
        sig: (2, N) array.

    Returns:
        (normalized array, scale factor used)
    """
    nonzero = sig[sig > 0]
    scale = float(np.percentile(nonzero, 95)) if len(nonzero) > 0 else 1.0
    scale = max(scale, 1e-6)
    return np.clip(sig / scale, 0, 3.0).astype(np.float32), scale


def extract_windows(sig: np.ndarray, stride: int = 1) -> np.ndarray:
    """Slide a window of WINDOW_SIZE over sig and return all windows.

    Args:
        sig:    (2, N) array.
        stride: Step size between windows.

    Returns:
        (M, 2, WINDOW_SIZE) float32 array.
    """
    N = sig.shape[1]
    windows = []
    for start in range(0, N - WINDOW_SIZE + 1, stride):
        windows.append(sig[:, start : start + WINDOW_SIZE])
    return np.stack(windows, axis=0) if windows else np.empty((0, 2, WINDOW_SIZE), dtype=np.float32)


def split_repos(
    signals: list[np.ndarray],
    train_frac: float = 0.70,
    val_frac: float = 0.15,
    seed: int = 42,
) -> tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
    """Split by repository (not by window) to prevent data leakage."""
    rng = np.random.default_rng(seed)
    idx = list(range(len(signals)))
    rng.shuffle(idx)
    n_train = max(1, int(len(idx) * train_frac))
    n_val   = max(1, int(len(idx) * val_frac))
    train_idx = idx[:n_train]
    val_idx   = idx[n_train : n_train + n_val]
    test_idx  = idx[n_train + n_val :]
    return ([signals[i] for i in train_idx],
            [signals[i] for i in val_idx],
            [signals[i] for i in test_idx])


# ---------------------------------------------------------------------------
# Main training loop
# ---------------------------------------------------------------------------

def train(max_epochs: int = 60, seed: int = 42) -> None:
    if not _TORCH_AVAILABLE or torch is None:
        print("ERROR: PyTorch is required for training. Install it with:\n"
              "  pip install torch\n"
              "  # or: pip install docxpilot[ml]")
        sys.exit(1)

    set_seed(seed)
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ data
    print("Loading signals...")
    real_signals = load_real_signals()
    print(f"  Real signals loaded: {len(real_signals)}")

    synth_signals = generate_dataset(n_repos=50)
    print(f"  Synthetic signals generated: {len(synth_signals)}")

    all_signals = real_signals + synth_signals
    if not all_signals:
        print("ERROR: No training data found. Run collect_data.py first (or rely on synthetic only).")
        # Allow training on synthetic only
        all_signals = synth_signals

    # Normalize each repo signal independently
    norm_signals = []
    scales = []
    for sig in all_signals:
        ns, sc = normalize_signal(sig)
        norm_signals.append(ns)
        scales.append(sc)

    # Split by repo
    train_sigs, val_sigs, test_sigs = split_repos(norm_signals, seed=seed)
    print(f"  Split: {len(train_sigs)} train / {len(val_sigs)} val / {len(test_sigs)} test repos")

    # Extract windows (stride=1 for train, stride=WINDOW_SIZE for val/test)
    train_wins = np.concatenate([extract_windows(s, stride=1) for s in train_sigs], axis=0)
    val_wins   = np.concatenate([extract_windows(s, stride=WINDOW_SIZE) for s in val_sigs], axis=0)
    print(f"  Windows: {len(train_wins)} train, {len(val_wins)} val")

    if len(train_wins) == 0:
        print("ERROR: No training windows extracted.")
        return

    train_t = torch.from_numpy(train_wins)
    val_t   = torch.from_numpy(val_wins) if len(val_wins) > 0 else train_t[:10]

    train_loader = DataLoader(TensorDataset(train_t), batch_size=64, shuffle=True)
    val_loader   = DataLoader(TensorDataset(val_t),   batch_size=64, shuffle=False)

    # ----------------------------------------------------------------- model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nTraining on: {device}")

    model = ActivityAutoencoder().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.MSELoss()

    # -------------------------------------------------------- training loop
    best_val_loss = float("inf")
    patience_counter = 0
    PATIENCE = 8

    log_path = SCRATCH_DIR / "loss_log.csv"
    with open(log_path, "w", newline="") as lf:
        writer = csv.writer(lf)
        writer.writerow(["epoch", "train_loss", "val_loss"])

    print("\nEpoch  Train Loss   Val Loss")
    print("-" * 35)

    for epoch in range(1, max_epochs + 1):
        # Train
        model.train()
        train_loss = 0.0
        for (batch,) in train_loader:
            batch = batch.to(device)
            optimizer.zero_grad()
            recon = model(batch)
            loss = criterion(recon, batch)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * batch.size(0)
        train_loss /= len(train_t)

        # Validate
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for (batch,) in val_loader:
                batch = batch.to(device)
                recon = model(batch)
                val_loss += criterion(recon, batch).item() * batch.size(0)
        val_loss /= len(val_t)

        print(f"  {epoch:3d}    {train_loss:.6f}    {val_loss:.6f}")

        # Log
        with open(log_path, "a", newline="") as lf:
            csv.writer(lf).writerow([epoch, f"{train_loss:.6f}", f"{val_loss:.6f}"])

        # Early stopping
        if val_loss < best_val_loss - 1e-6:
            best_val_loss = val_loss
            patience_counter = 0
            torch.save(model.state_dict(), WEIGHTS_DIR / "activity_ae.pt")
        else:
            patience_counter += 1
            if patience_counter >= PATIENCE:
                print(f"\nEarly stopping at epoch {epoch} (patience={PATIENCE})")
                break

    # ---------------------------------------------------- compute threshold
    print("\nComputing anomaly threshold on validation set...")
    model.load_state_dict(torch.load(WEIGHTS_DIR / "activity_ae.pt", map_location=device))
    model.eval()

    val_errors = []
    with torch.no_grad():
        for (batch,) in val_loader:
            batch = batch.to(device)
            recon = model(batch)
            # Per-window MSE
            mse = ((recon - batch) ** 2).mean(dim=(1, 2))
            val_errors.extend(mse.cpu().numpy().tolist())

    threshold = float(np.percentile(val_errors, 99)) if val_errors else 0.1
    print(f"  Threshold (99th percentile of val MSE): {threshold:.6f}")

    # ----------------------------------------------------------- save config
    config = {
        "window_size": WINDOW_SIZE,
        "threshold": threshold,
        "normalization": "percentile_95_clip_3",
        "training_date": time.strftime("%Y-%m-%d"),
        "n_train_repos": len(train_sigs),
        "n_val_repos": len(val_sigs),
        "n_test_repos": len(test_sigs),
        "best_val_loss": float(best_val_loss),
        "seed": seed,
    }
    with open(WEIGHTS_DIR / "config.json", "w") as cf:
        json.dump(config, cf, indent=2)

    print(f"\nWeights saved -> {WEIGHTS_DIR / 'activity_ae.pt'}")
    print(f"Config saved  -> {WEIGHTS_DIR / 'config.json'}")

    # --------------------------------------------------------- plot loss curve
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        epochs_log, train_log, val_log = [], [], []
        with open(log_path) as lf:
            reader = csv.DictReader(lf)
            for row in reader:
                epochs_log.append(int(row["epoch"]))
                train_log.append(float(row["train_loss"]))
                val_log.append(float(row["val_loss"]))

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(epochs_log, train_log, label="Train loss", color="#4c8eda")
        ax.plot(epochs_log, val_log,   label="Val loss",   color="#ff9f40")
        ax.set_xlabel("Epoch")
        ax.set_ylabel("MSE Loss")
        ax.set_title("Autoencoder Training Loss")
        ax.legend()
        plt.tight_layout()
        curve_path = WEIGHTS_DIR / "loss_curve.png"
        plt.savefig(str(curve_path), dpi=150)
        plt.close(fig)
        print(f"Loss curve   -> {curve_path}")
    except Exception as exc:
        print(f"Warning: could not plot loss curve: {exc}")

    print("\nTraining complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train DocXPilot activity autoencoder")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    train(max_epochs=args.epochs, seed=args.seed)
