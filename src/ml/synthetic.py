"""Synthetic training data generator for DocXPilot Activity Analyzer.

Produces artificial daily commit signals that look like real open-source
projects: weekly seasonality, slow trend, Poisson noise, vacation gaps,
and occasional burst events.

These signals supplement the real repo signals during training so the
autoencoder sees a wider variety of *normal* activity patterns.
"""

from __future__ import annotations

import numpy as np


RNG = np.random.default_rng(42)   # fixed seed for reproducibility


def _weekly_season(n: int, amplitude: float = 0.5) -> np.ndarray:
    """Return a 7-day sinusoidal pattern scaled to [0, amplitude]."""
    t = np.arange(n)
    # Phase randomly shifted so not every repo starts on the same weekday
    phase = RNG.uniform(0, 2 * np.pi)
    s = amplitude * (0.5 + 0.5 * np.sin(2 * np.pi * t / 7 + phase))
    return s.astype(np.float32)


def _slow_trend(n: int) -> np.ndarray:
    """Return a slow sigmoid-like growth trend."""
    t = np.linspace(-3, 3, n)
    return (1 / (1 + np.exp(-t)) * RNG.uniform(0.3, 1.2)).astype(np.float32)


def _poisson_noise(n: int, mu: float = 1.5) -> np.ndarray:
    """Return Poisson-distributed commit counts (integer)."""
    return RNG.poisson(mu, size=n).astype(np.float32)


def generate_normal_signal(
    n_days: int = 365,
    add_trend: bool = True,
) -> np.ndarray:
    """Generate one synthetic *normal* activity signal of shape (2, n_days).

    Args:
        n_days:    Length of the signal in days.
        add_trend: Whether to include a slow growth trend.

    Returns:
        Float32 array of shape (2, n_days), log1p-compressed.
    """
    base_mu = RNG.uniform(0.5, 2.5)
    commits = _poisson_noise(n_days, mu=base_mu)
    commits += _weekly_season(n_days, amplitude=RNG.uniform(0.3, 1.5))
    if add_trend:
        commits *= _slow_trend(n_days)

    # Inject 1–3 vacation gaps (runs of 5–20 zero days)
    n_gaps = RNG.integers(1, 4)
    for _ in range(n_gaps):
        gap_len = int(RNG.integers(5, 20))
        start = int(RNG.integers(0, max(1, n_days - gap_len)))
        commits[start : start + gap_len] = 0.0

    # Churn tracks commits with extra noise
    churn_mult = RNG.uniform(5, 50)
    churn = commits * churn_mult * RNG.uniform(0.5, 2.0, size=n_days).astype(np.float32)

    commits = np.clip(commits, 0, None)
    churn = np.clip(churn, 0, None)

    return np.stack([np.log1p(commits), np.log1p(churn)], axis=0)


def generate_dataset(
    n_repos: int = 50,
    min_days: int = 180,
    max_days: int = 730,
) -> list[np.ndarray]:
    """Generate *n_repos* synthetic signals of varying lengths.

    Args:
        n_repos:  Number of synthetic "repositories" to generate.
        min_days: Minimum signal length in days.
        max_days: Maximum signal length in days.

    Returns:
        List of (2, N) float32 arrays, one per synthetic repo.
    """
    signals = []
    for _ in range(n_repos):
        n_days = int(RNG.integers(min_days, max_days))
        sig = generate_normal_signal(n_days)
        signals.append(sig)
    return signals
