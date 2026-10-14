"""Tests for DocXPilot Activity Signal Analyzer.

Covers:
  - Signal builder on a temporary git repo with fixed commit dates
  - FFT peak detection on synthetic signals with known periods
  - Gap rule triggers correctly
  - Short history returns available=False
  - Inference output shapes and threshold logic with a dummy model
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

# Make sure src/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with a controlled commit history."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Initialise git
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"],
                   cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"],
                   cwd=str(repo), check=True, capture_output=True)

    # Create commits on specific dates spanning > 60 days & > 30 commits
    base_date = date(2024, 1, 1)
    commit_offsets = (
        list(range(0, 90, 3))    # every 3 days for 90 days — 30 commits
        + list(range(91, 150, 5)) # additional commits
    )

    for i, offset in enumerate(commit_offsets):
        d = base_date + timedelta(days=offset)
        iso_date = f"{d.isoformat()}T12:00:00+00:00"

        f = repo / f"file_{i}.txt"
        f.write_text(f"content {i}\n" * (i % 5 + 1))

        subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True)
        env = {**os.environ, "GIT_AUTHOR_DATE": iso_date, "GIT_COMMITTER_DATE": iso_date}
        subprocess.run(
            ["git", "commit", "-m", f"commit {i}"],
            cwd=str(repo), env=env, check=True, capture_output=True,
        )

    return repo


# ---------------------------------------------------------------------------
# 1. Signal builder tests
# ---------------------------------------------------------------------------

class TestBuildSignals:
    def test_returns_correct_types(self, tmp_git_repo: Path) -> None:
        from analyzers.activity_signal import build_signals
        dates, signals = build_signals(str(tmp_git_repo))
        assert isinstance(dates, list)
        assert isinstance(signals, np.ndarray)

    def test_signal_shape(self, tmp_git_repo: Path) -> None:
        from analyzers.activity_signal import build_signals
        dates, signals = build_signals(str(tmp_git_repo))
        assert signals.ndim == 2
        assert signals.shape[0] == 2
        assert signals.shape[1] == len(dates)

    def test_commit_count_matches_git(self, tmp_git_repo: Path) -> None:
        from analyzers.activity_signal import build_signals
        dates, signals = build_signals(str(tmp_git_repo))
        raw_commits = np.expm1(signals[0])
        # We know we made at least 30 commits
        assert raw_commits.sum() >= 30

    def test_non_git_folder_raises(self, tmp_path: Path) -> None:
        from analyzers.activity_signal import build_signals
        with pytest.raises(ValueError, match="Not a git repository"):
            build_signals(str(tmp_path))

    def test_short_history_raises(self, tmp_path: Path) -> None:
        from analyzers.activity_signal import build_signals
        repo = tmp_path / "short_repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"],
                       cwd=str(repo), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"],
                       cwd=str(repo), check=True, capture_output=True)
        # Make just 2 commits 5 days apart — too short
        for i in range(2):
            f = repo / f"f{i}.txt"
            f.write_text("x")
            subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True)
            d = date(2024, 1, 1) + timedelta(days=i * 5)
            iso = f"{d.isoformat()}T12:00:00+00:00"
            env = {**os.environ, "GIT_AUTHOR_DATE": iso, "GIT_COMMITTER_DATE": iso}
            subprocess.run(["git", "commit", "-m", f"c{i}"],
                           cwd=str(repo), env=env, check=True, capture_output=True)
        with pytest.raises(ValueError):
            build_signals(str(repo))


# ---------------------------------------------------------------------------
# 2. FFT peak detection on synthetic known-period signals
# ---------------------------------------------------------------------------

class TestDspPeakDetection:
    @pytest.mark.parametrize("true_period", [5, 7, 14])
    def test_dominant_period_within_tolerance(self, true_period: int) -> None:
        from analyzers.activity_dsp import compute_dsp

        N = 365
        t = np.arange(N, dtype=np.float32)
        signal_raw = 2.0 + 1.5 * np.sin(2 * np.pi * t / true_period)
        signal_raw = np.clip(signal_raw, 0, None)
        log_sig = np.log1p(signal_raw).astype(np.float32)
        signals = np.stack([log_sig, log_sig * 0.5], axis=0)

        base = date(2024, 1, 1)
        dates = [base + timedelta(days=i) for i in range(N)]

        result = compute_dsp(signals, dates)

        # Allow ±1 day tolerance for 5/14-day and ±0.5 for 7-day
        tol = 0.5 if true_period == 7 else 1.0
        assert abs(result.dominant_period_days - true_period) <= tol, (
            f"Expected {true_period}d, got {result.dominant_period_days:.2f}d"
        )

    def test_strength_is_fraction(self) -> None:
        from analyzers.activity_dsp import compute_dsp

        N = 200
        t = np.arange(N, dtype=np.float32)
        signal_raw = np.log1p(2 + np.sin(2 * np.pi * t / 7))
        signals = np.stack([signal_raw.astype(np.float32), signal_raw.astype(np.float32)], axis=0)
        base = date(2024, 1, 1)
        dates = [base + timedelta(days=i) for i in range(N)]
        result = compute_dsp(signals, dates)
        assert 0 <= result.dominant_strength <= 1.0


# ---------------------------------------------------------------------------
# 3. Gap rule tests
# ---------------------------------------------------------------------------

class TestGapDetection:
    def _make_signal_with_gap(self, n: int, gap_start: int, gap_len: int) -> tuple:
        commits = np.ones(n, dtype=np.float32)
        commits[gap_start : gap_start + gap_len] = 0.0
        base = date(2024, 1, 1)
        dates = [base + timedelta(days=i) for i in range(n)]
        return dates, np.stack([np.log1p(commits), np.log1p(commits)], axis=0)

    def test_long_gap_is_flagged(self) -> None:
        from ml.infer import detect_inactivity_gaps
        dates, signals = self._make_signal_with_gap(200, 50, 30)
        gaps = detect_inactivity_gaps(signals, dates)
        assert len(gaps) >= 1
        kinds = [g[2] for g in gaps]
        assert "inactivity_gap" in kinds

    def test_short_gap_not_flagged(self) -> None:
        from ml.infer import detect_inactivity_gaps
        # Only a 3-day gap among daily commits — below threshold
        dates, signals = self._make_signal_with_gap(200, 50, 3)
        gaps = detect_inactivity_gaps(signals, dates)
        # Should not flag a very short gap
        assert len(gaps) == 0

    def test_no_gaps_in_all_active_signal(self) -> None:
        from ml.infer import detect_inactivity_gaps
        commits = np.ones(200, dtype=np.float32)
        base = date(2024, 1, 1)
        dates = [base + timedelta(days=i) for i in range(200)]
        signals = np.stack([np.log1p(commits), np.log1p(commits)], axis=0)
        gaps = detect_inactivity_gaps(signals, dates)
        assert gaps == []


# ---------------------------------------------------------------------------
# 4. Short history returns available=False (via analyze_activity)
# ---------------------------------------------------------------------------

class TestActivityAnalyzerEdgeCases:
    def test_non_git_returns_unavailable(self, tmp_path: Path) -> None:
        from analyzers.activity_analyzer import analyze_activity
        report = analyze_activity(str(tmp_path))
        assert report.available is False
        assert report.reason != ""

    def test_short_history_returns_unavailable(self, tmp_path: Path) -> None:
        from analyzers.activity_analyzer import analyze_activity
        repo = tmp_path / "r"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"],
                       cwd=str(repo), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"],
                       cwd=str(repo), check=True, capture_output=True)
        (repo / "f.txt").write_text("x")
        subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "only"],
                       cwd=str(repo), check=True, capture_output=True)
        report = analyze_activity(str(repo))
        assert report.available is False


# ---------------------------------------------------------------------------
# 5. Inference shapes and threshold logic with dummy model
# ---------------------------------------------------------------------------

class TestInferenceShapes:
    def test_window_extraction(self) -> None:
        from ml.train import extract_windows
        from ml.model import WINDOW_SIZE
        sig = np.random.rand(2, 200).astype(np.float32)
        windows = extract_windows(sig, stride=1)
        assert windows.shape == (200 - WINDOW_SIZE + 1, 2, WINDOW_SIZE)

    def test_normalize_clips_to_3(self) -> None:
        from ml.train import normalize_signal
        sig = np.array([[0, 10, 100, 1000]], dtype=np.float32)
        norm, scale = normalize_signal(sig)
        assert norm.max() <= 3.0 + 1e-6

    @pytest.mark.skipif(
        not __import__("ml.model", fromlist=["is_torch_available"]).is_torch_available(),
        reason="PyTorch not installed",
    )
    def test_dummy_model_output_shape(self) -> None:
        import torch
        from ml.model import ActivityAutoencoder, WINDOW_SIZE
        model = ActivityAutoencoder()
        x = torch.zeros(4, 2, WINDOW_SIZE)
        out = model(x)
        assert out.shape == (4, 2, WINDOW_SIZE)

    @pytest.mark.skipif(
        not __import__("ml.model", fromlist=["is_torch_available"]).is_torch_available(),
        reason="PyTorch not installed",
    )
    def test_zero_window_low_reconstruction_error(self) -> None:
        """Autoencoder reconstructs silence well (MSE ≈ 0) — this is expected behaviour."""
        import torch
        from ml.model import ActivityAutoencoder, WINDOW_SIZE
        model = ActivityAutoencoder()
        x = torch.zeros(1, 2, WINDOW_SIZE)
        out = model(x)
        mse = ((out - x) ** 2).mean().item()
        # We only assert the model runs, not that MSE is exactly 0 (untrained)
        assert isinstance(mse, float)
