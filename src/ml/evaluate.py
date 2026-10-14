"""Evaluation benchmark for DocXPilot Activity Signal Analyzer.

Compares three anomaly detection approaches on held-out test signals with
injected ground-truth anomalies (bursts and rhythm breaks):
  1. Rolling z-score baseline (28-day window, absolute z > 3)
  2. DSP-only spectral feature change detector (spectral flatness / entropy drift)
  3. Trained 1D Convolutional Autoencoder (MSE reconstruction error)

Measures window-level Precision, Recall, and F1 score.
Outputs a clean Markdown / Rich table suitable for inclusion in the lab report.
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.model import WINDOW_SIZE, is_torch_available
from ml.synthetic import generate_dataset
from ml.train import normalize_signal


def inject_anomalies(
    signal: np.ndarray,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Inject known anomalies into normal activity signal.

    Returns:
        (corrupted_signal, ground_truth_window_labels)
        where ground_truth_window_labels is a boolean array of length N - WINDOW_SIZE + 1
    """
    rng = np.random.default_rng(seed)
    N = signal.shape[1]
    corrupted = signal.copy()
    gt_windows = np.zeros(max(0, N - WINDOW_SIZE + 1), dtype=bool)

    if N < WINDOW_SIZE * 3:
        return corrupted, gt_windows

    # 1. Inject a Burst: 3-8x normal commit count for 2-3 days
    burst_start = rng.integers(WINDOW_SIZE, N - WINDOW_SIZE * 2)
    burst_len = rng.integers(2, 4)
    multiplier = rng.uniform(4.0, 7.0)
    corrupted[0, burst_start : burst_start + burst_len] += np.log1p(multiplier * 5)
    corrupted[1, burst_start : burst_start + burst_len] += np.log1p(multiplier * 200)

    # Any window covering this burst is anomalous
    for w in range(len(gt_windows)):
        w_start = w
        w_end = w + WINDOW_SIZE
        if not (w_end <= burst_start or w_start >= burst_start + burst_len):
            gt_windows[w] = True

    # 2. Inject a Rhythm Break: scramble weekly pattern for 14-21 days
    rhythm_start = rng.integers(burst_start + WINDOW_SIZE, N - WINDOW_SIZE)
    rhythm_len = rng.integers(14, 21)
    noise = rng.exponential(scale=1.5, size=rhythm_len)
    corrupted[0, rhythm_start : rhythm_start + rhythm_len] = np.log1p(noise)

    for w in range(len(gt_windows)):
        w_start = w
        w_end = w + WINDOW_SIZE
        if not (w_end <= rhythm_start or w_start >= rhythm_start + rhythm_len):
            gt_windows[w] = True

    return corrupted, gt_windows


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def detect_rolling_zscore(signal: np.ndarray, threshold: float = 3.0) -> np.ndarray:
    """Detector 1: Rolling z-score baseline over commits channel."""
    commits = signal[0]
    N = len(commits)
    n_win = max(0, N - WINDOW_SIZE + 1)
    preds = np.zeros(n_win, dtype=bool)

    for w in range(n_win):
        win = commits[w : w + WINDOW_SIZE]
        mean = np.mean(win)
        std = np.std(win)
        if std > 1e-4:
            z_scores = np.abs((win - mean) / std)
            if np.any(z_scores > threshold):
                preds[w] = True
    return preds


def detect_dsp_spectral_change(signal: np.ndarray) -> np.ndarray:
    """Detector 2: DSP-only spectral feature drift detector."""
    commits = signal[0]
    N = len(commits)
    n_win = max(0, N - WINDOW_SIZE + 1)
    preds = np.zeros(n_win, dtype=bool)

    flatness = []
    for w in range(n_win):
        win = commits[w : w + WINDOW_SIZE]
        # compute power spectrum of window
        fft = np.abs(np.fft.rfft(win * np.hanning(len(win))))
        pwr = fft ** 2 + 1e-10
        # spectral flatness: geometric mean / arithmetic mean
        geom = np.exp(np.mean(np.log(pwr)))
        arith = np.mean(pwr)
        sf = geom / arith
        flatness.append(sf)

    flatness = np.array(flatness)
    if len(flatness) > 0:
        med = np.median(flatness)
        mad = np.median(np.abs(flatness - med)) + 1e-6
        # Flag if deviation from median spectral flatness > 2.5 MAD
        preds = np.abs(flatness - med) / mad > 2.5

    return preds


def detect_autoencoder(signal: np.ndarray, model, config: dict) -> np.ndarray:
    """Detector 3: Trained 1D Convolutional Autoencoder."""
    import torch

    norm_sig, _ = normalize_signal(signal)
    N = norm_sig.shape[1]
    n_win = max(0, N - WINDOW_SIZE + 1)
    if n_win == 0:
        return np.zeros(0, dtype=bool)

    windows = [norm_sig[:, w : w + WINDOW_SIZE] for w in range(n_win)]
    win_tensor = torch.from_numpy(np.stack(windows, axis=0))

    threshold = float(config.get("threshold", 0.03))
    with torch.no_grad():
        recon = model(win_tensor)
        mse = ((recon - win_tensor) ** 2).mean(dim=(1, 2)).numpy()

    return mse > threshold


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_prf(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float, float]:
    tp = np.sum(y_true & y_pred)
    fp = np.sum((~y_true) & y_pred)
    fn = np.sum(y_true & (~y_pred))

    prec = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    rec = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = float(2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    return prec, rec, f1


def run_benchmark(n_test_repos: int = 15) -> dict:
    weights_path = Path(__file__).resolve().parent / "weights" / "activity_ae.pt"
    config_path = Path(__file__).resolve().parent / "weights" / "config.json"

    model = None
    config = {}
    if is_torch_available() and weights_path.exists() and config_path.exists():
        import torch
        from ml.model import ActivityAutoencoder
        model = ActivityAutoencoder()
        model.load_state_dict(torch.load(str(weights_path), map_location="cpu"))
        model.eval()
        config = json.loads(config_path.read_text(encoding="utf-8"))

    # Generate test signals (different random seed from training seed 42)
    test_signals = generate_dataset(n_repos=n_test_repos, min_days=180, max_days=300)

    zscore_results = []
    dsp_results = []
    ae_results = []

    for i, sig in enumerate(test_signals):
        corrupted, gt = inject_anomalies(sig, seed=100 + i)
        if len(gt) == 0:
            continue

        p_z, r_z, f_z = compute_prf(gt, detect_rolling_zscore(corrupted))
        zscore_results.append((p_z, r_z, f_z))

        p_d, r_d, f_d = compute_prf(gt, detect_dsp_spectral_change(corrupted))
        dsp_results.append((p_d, r_d, f_d))

        if model is not None:
            p_a, r_a, f_a = compute_prf(gt, detect_autoencoder(corrupted, model, config))
            ae_results.append((p_a, r_a, f_a))

    def mean_metrics(res_list):
        if not res_list:
            return 0.0, 0.0, 0.0
        arr = np.array(res_list)
        return float(arr[:, 0].mean()), float(arr[:, 1].mean()), float(arr[:, 2].mean())

    pz, rz, fz = mean_metrics(zscore_results)
    pd, rd, fd = mean_metrics(dsp_results)
    pa, ra, fa = mean_metrics(ae_results)

    return {
        "zscore": {"precision": pz, "recall": rz, "f1": fz},
        "dsp_spectral": {"precision": pd, "recall": rd, "f1": fd},
        "autoencoder": {"precision": pa, "recall": ra, "f1": fa},
    }


if __name__ == "__main__":
    print("Running evaluation on 15 test repositories with injected anomalies...")
    res = run_benchmark(n_test_repos=15)
    print("\n" + "=" * 60)
    print("DETECTOR PERFORMANCE EVALUATION BENCHMARK")
    print("=" * 60)
    print(f"{'Detector':<28} | {'Precision':<10} | {'Recall':<8} | {'F1-Score':<8}")
    print("-" * 60)
    print(f"{'Rolling z-score (z > 3)':<28} | {res['zscore']['precision']:<10.3f} | {res['zscore']['recall']:<8.3f} | {res['zscore']['f1']:<8.3f}")
    print(f"{'DSP Spectral Flatness drift':<28} | {res['dsp_spectral']['precision']:<10.3f} | {res['dsp_spectral']['recall']:<8.3f} | {res['dsp_spectral']['f1']:<8.3f}")
    print(f"{'1D Conv Autoencoder (Ours)':<28} | {res['autoencoder']['precision']:<10.3f} | {res['autoencoder']['recall']:<8.3f} | {res['autoencoder']['f1']:<8.3f}")
    print("=" * 60)
