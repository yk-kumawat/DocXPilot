"""Inference module for DocXPilot Activity Autoencoder.

Loads trained weights lazily (only when first called), slides a 28-day
window over the signal with stride=1, computes per-window reconstruction
MSE, and returns a list of flagged date-ranges with their anomaly kind.

Design note
-----------
The autoencoder detects *bursts* and *rhythm breaks* (windows with unusual
pattern). It does NOT reliably detect long inactivity gaps because a
window of all zeros is trivially reconstructed (MSE ≈ 0). Inactivity gaps
are therefore handled by a separate rule-based detector. This split is
deliberate and is documented in the lab report.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from ml.model import WINDOW_SIZE, is_torch_available

if TYPE_CHECKING:
    pass

WEIGHTS_DIR = Path(__file__).resolve().parent / "weights"
_WEIGHTS_PATH = WEIGHTS_DIR / "activity_ae.pt"
_CONFIG_PATH  = WEIGHTS_DIR / "config.json"

# Module-level cache so weights are only loaded once per process
_model_cache: object | None = None
_config_cache: dict | None = None


def _load_model_and_config() -> tuple[object, dict] | tuple[None, None]:
    """Load (model, config) from disk.  Returns (None, None) on any failure."""
    global _model_cache, _config_cache
    if _model_cache is not None:
        return _model_cache, _config_cache  # type: ignore[return-value]

    if not is_torch_available():
        return None, None
    if not _WEIGHTS_PATH.exists() or not _CONFIG_PATH.exists():
        return None, None

    try:
        import torch
        from ml.model import ActivityAutoencoder

        cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        model = ActivityAutoencoder()
        model.load_state_dict(torch.load(str(_WEIGHTS_PATH), map_location="cpu"))
        model.eval()
        _model_cache = model
        _config_cache = cfg
        return model, cfg
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Gap rule (rule-based, independent of the model)
# ---------------------------------------------------------------------------

def detect_inactivity_gaps(
    signals: np.ndarray,
    dates: list[date],
) -> list[tuple[date, date, str, float]]:
    """Detect long zero-commit runs in the raw signal.

    A gap is flagged when a run of zero-commit days is longer than
    max(14, 3 × median_gap_length).

    Args:
        signals: (2, N) log1p-compressed array.
        dates:   List of N dates.

    Returns:
        List of (start_date, end_date, 'inactivity_gap', gap_length_days).
    """
    raw_commits = np.expm1(signals[0])  # back to raw counts
    is_zero = raw_commits == 0.0

    # Collect all individual gap lengths (runs of zeros)
    gaps: list[tuple[int, int]] = []   # (start_idx, end_idx)
    in_gap = False
    gap_start = 0
    for i, z in enumerate(is_zero):
        if z and not in_gap:
            in_gap = True
            gap_start = i
        elif not z and in_gap:
            in_gap = False
            gaps.append((gap_start, i - 1))
    if in_gap:
        gaps.append((gap_start, len(is_zero) - 1))

    if not gaps:
        return []

    gap_lengths = [e - s + 1 for s, e in gaps]
    # Median gap of normal inactivity intervals (e.g. weekends/short lulls < 14 days)
    normal_gaps = [gl for gl in gap_lengths if gl < 14]
    median_gap = float(np.median(normal_gaps)) if normal_gaps else 1.0
    threshold = max(14, 3 * median_gap)

    results = []
    for (s, e), gl in zip(gaps, gap_lengths):
        if gl >= threshold:
            results.append((dates[s], dates[e], "inactivity_gap", float(gl)))

    return results


# ---------------------------------------------------------------------------
# Model-based anomaly detection
# ---------------------------------------------------------------------------

def detect_anomalies_with_model(
    signals: np.ndarray,
    dates: list[date],
) -> tuple[list[tuple[date, date, str, float]], bool]:
    """Slide the autoencoder over *signals* and flag anomalous windows.

    Args:
        signals: (2, N) log1p-compressed, *not yet normalised*.
        dates:   List of N dates.

    Returns:
        ``(anomaly_list, model_used)`` where each anomaly is
        ``(start_date, end_date, kind, score)``.
        *model_used* is False when the model or torch is unavailable.
    """
    model, cfg = _load_model_and_config()
    if model is None or cfg is None:
        return [], False

    try:
        import torch

        threshold = float(cfg["threshold"])
        window_size = int(cfg.get("window_size", WINDOW_SIZE))
        N = signals.shape[1]

        # Normalise using the same procedure as training
        nonzero = signals[signals > 0]
        scale = float(np.percentile(nonzero, 95)) if len(nonzero) > 0 else 1.0
        scale = max(scale, 1e-6)
        norm_sig = np.clip(signals / scale, 0, 3.0).astype(np.float32)

        # Build windows
        windows = []
        win_starts = []
        for start in range(N - window_size + 1):
            windows.append(norm_sig[:, start : start + window_size])
            win_starts.append(start)

        if not windows:
            return [], True

        win_tensor = torch.from_numpy(np.stack(windows, axis=0))

        # Batch inference
        BATCH = 256
        mse_scores = []
        with torch.no_grad():
            for i in range(0, len(win_tensor), BATCH):
                batch = win_tensor[i : i + BATCH]
                recon = model(batch)
                mse = ((recon - batch) ** 2).mean(dim=(1, 2))
                mse_scores.extend(mse.cpu().numpy().tolist())

        mse_scores = np.array(mse_scores)
        flagged = mse_scores > threshold

        # Merge overlapping flagged windows into date ranges
        anomalies: list[tuple[date, date, str, float]] = []
        raw_commits = np.expm1(signals[0])
        normal_mean = float(raw_commits[raw_commits > 0].mean()) if (raw_commits > 0).any() else 1.0

        i = 0
        while i < len(flagged):
            if flagged[i]:
                j = i
                while j < len(flagged) and flagged[j]:
                    j += 1
                # Merged window: [win_starts[i], win_starts[j-1] + window_size - 1]
                seg_start = win_starts[i]
                seg_end   = win_starts[j - 1] + window_size - 1
                seg_end   = min(seg_end, N - 1)

                seg_commits = raw_commits[seg_start : seg_end + 1]
                seg_mean    = float(seg_commits.mean())
                seg_score   = float(mse_scores[i : j].mean())

                # Classify: burst (mean well above normal) vs rhythm break
                kind = "burst" if seg_mean > normal_mean * 2.5 else "rhythm_break"
                anomalies.append((
                    dates[seg_start],
                    dates[seg_end],
                    kind,
                    round(seg_score / threshold, 3),  # score as ratio to threshold
                ))
                i = j
            else:
                i += 1

        return anomalies, True

    except Exception:
        return [], False
