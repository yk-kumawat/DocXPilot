"""DSP pipeline for DocXPilot Activity Signal Analyzer.

Implements classical digital signal processing on the daily commit signal:

  1. Detrending     — remove slow drift so DC doesn't bias the spectrum
  2. Low-pass filter — 4th-order Butterworth, cutoff 0.25 cycles/day
  3. Hann window + FFT — find dominant frequency / period
  4. Autocorrelation  — cross-check dominant period
  5. STFT           — show how rhythm evolves over time
  6. Feature extraction — spectral entropy, flatness, burstiness

All steps are commented to justify DSP choices for the lab report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import matplotlib
matplotlib.use("Agg")          # headless — no display needed
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy import signal as sp_signal


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DspResult:
    """Outputs from the DSP pipeline."""

    dominant_period_days: float = 0.0   # 1/f_peak in days
    dominant_strength: float = 0.0      # peak_power / total_power
    autocorr_period_days: float = 0.0   # lag of strongest autocorr peak
    period_mismatch: bool = False        # True if FFT vs AC differ > 20%

    spectral_entropy: float = 0.0       # Shannon entropy of PSD (lower = more tonal)
    spectral_flatness: float = 0.0      # Wiener flatness (1 = noise, 0 = tonal)
    burstiness: float = 0.0             # (std-mean)/(std+mean) of raw commits
    active_day_ratio: float = 0.0       # fraction of days with >= 1 commit

    # For plots
    freqs: np.ndarray = field(default_factory=lambda: np.array([]))
    magnitude: np.ndarray = field(default_factory=lambda: np.array([]))
    filtered: np.ndarray = field(default_factory=lambda: np.array([]))
    moving_avg: np.ndarray = field(default_factory=lambda: np.array([]))
    stft_t: np.ndarray = field(default_factory=lambda: np.array([]))
    stft_f: np.ndarray = field(default_factory=lambda: np.array([]))
    stft_z: np.ndarray = field(default_factory=lambda: np.array([]))


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def compute_dsp(signals: np.ndarray, dates: list[date]) -> DspResult:
    """Run the full DSP pipeline on the commit channel of *signals*.

    Args:
        signals: Float32 array of shape (2, N).
                 Row 0 = log1p(commits/day), row 1 = log1p(churn/day).
        dates:   List of N :class:`datetime.date` objects (one per sample).

    Returns:
        A :class:`DspResult` with all computed metrics and arrays.
    """
    result = DspResult()
    N = signals.shape[1]
    commit_log = signals[0].copy()   # use log1p(commits) channel throughout

    # ------------------------------------------------------------------
    # Step 1: Detrend
    # Removing the linear trend prevents a slow upward/downward drift
    # from creating a large DC component that would swamp the spectrum.
    # scipy.signal.detrend fits and subtracts a least-squares line.
    # ------------------------------------------------------------------
    detrended = sp_signal.detrend(commit_log, type="linear")

    # ------------------------------------------------------------------
    # Step 2: Low-pass Butterworth filter
    # We want to suppress high-frequency noise (single-commit spikes on
    # random days) and keep rhythms longer than 4 days.
    # Cutoff = 0.25 cycles/day  ->  period > 4 days passes.
    # 4th-order gives 24 dB/oct roll-off without phase distortion.
    # filtfilt applies the filter twice (forward + backward) for zero
    # phase shift — critical so peaks align with the correct dates.
    # fs = 1 sample/day, so Nyquist = 0.5 cycles/day.
    # ------------------------------------------------------------------
    sos = sp_signal.butter(4, Wn=0.25, btype="low", fs=1.0, output="sos")
    filtered = sp_signal.sosfiltfilt(sos, detrended)
    result.filtered = filtered

    # 7-day moving average for visual reference in the time-domain plot
    kernel = np.ones(7) / 7
    result.moving_avg = np.convolve(commit_log, kernel, mode="same")

    # ------------------------------------------------------------------
    # Step 3: Hann window + FFT
    # Multiplying by a Hann window tapers the signal edges to zero so
    # the DFT doesn't see a discontinuity at the boundary (spectral
    # leakage reduction).  Zero-padding to next power of two gives
    # finer frequency resolution at no extra cost.
    # ------------------------------------------------------------------
    window = np.hanning(N)
    windowed = detrended * window

    nfft = int(2 ** np.ceil(np.log2(N)))           # next power of two
    spectrum = np.fft.rfft(windowed, n=nfft)
    freqs = np.fft.rfftfreq(nfft, d=1.0)           # cycles / day
    magnitude = np.abs(spectrum)
    power = magnitude ** 2

    result.freqs = freqs
    result.magnitude = magnitude

    # ------------------------------------------------------------------
    # Step 4: Dominant period
    # Ignore DC (f=0) and any frequency below 2/N (less than half the
    # observation window — too low to estimate reliably).
    # ------------------------------------------------------------------
    f_min = 2.0 / N
    valid_mask = (freqs > f_min) & (freqs > 0)

    if valid_mask.any():
        valid_power = power.copy()
        valid_power[~valid_mask] = 0.0
        peak_idx = int(np.argmax(valid_power))
        peak_freq = freqs[peak_idx]
        if peak_freq > 0:
            result.dominant_period_days = float(1.0 / peak_freq)
            total_power = float(power[valid_mask].sum())
            result.dominant_strength = float(valid_power[peak_idx] / total_power) if total_power > 0 else 0.0

    # ------------------------------------------------------------------
    # Step 5: Autocorrelation cross-check
    # The autocorrelation of the filtered signal should show a peak at
    # the same lag as the FFT period.  We look in the range 2–60 days.
    # A mismatch > 20% suggests the spectrum is multi-modal or noisy.
    # ------------------------------------------------------------------
    ac = np.correlate(filtered - filtered.mean(), filtered - filtered.mean(), mode="full")
    ac = ac[ac.size // 2:]   # keep non-negative lags only
    if ac.max() != 0:
        ac = ac / ac[0]       # normalise

    lag_min, lag_max = 2, min(60, N // 2)
    if lag_max > lag_min:
        ac_search = ac[lag_min:lag_max]
        best_lag = int(np.argmax(ac_search)) + lag_min
        result.autocorr_period_days = float(best_lag)

        if result.dominant_period_days > 0:
            ratio = abs(result.autocorr_period_days - result.dominant_period_days) / result.dominant_period_days
            result.period_mismatch = ratio > 0.20

    # ------------------------------------------------------------------
    # Step 6: STFT (Short-Time Fourier Transform)
    # Splitting the signal into overlapping frames lets us see how the
    # dominant frequency changes over time.  nperseg=64 gives ~64-day
    # analysis windows; noverlap=48 gives 75% overlap for smooth output.
    # ------------------------------------------------------------------
    stft_nperseg = min(64, N // 2)
    stft_noverlap = int(stft_nperseg * 0.75)
    if stft_nperseg > 4:
        f_stft, t_stft, Zxx = sp_signal.stft(
            commit_log,
            fs=1.0,
            window="hann",
            nperseg=stft_nperseg,
            noverlap=stft_noverlap,
        )
        result.stft_f = f_stft
        result.stft_t = t_stft
        result.stft_z = np.abs(Zxx)

    # ------------------------------------------------------------------
    # Step 7: Feature extraction
    # Spectral entropy: Shannon entropy of the normalised power spectrum.
    #   Low value  -> energy concentrated in few frequencies (tonal/rhythmic).
    #   High value -> energy spread evenly (noisy/irregular).
    # Spectral flatness: geometric mean / arithmetic mean of power.
    #   Close to 1 -> white noise.  Close to 0 -> tonal signal.
    # Burstiness: (σ-μ)/(σ+μ) on raw commit counts (before log1p).
    #   Positive and large -> highly bursty (sprint-driven).
    # ------------------------------------------------------------------
    if power[valid_mask].sum() > 0:
        p_norm = power[valid_mask] / power[valid_mask].sum()
        p_norm = p_norm[p_norm > 0]
        result.spectral_entropy = float(-np.sum(p_norm * np.log2(p_norm)))

        geom_mean = float(np.exp(np.mean(np.log(power[valid_mask] + 1e-10))))
        arith_mean = float(power[valid_mask].mean())
        result.spectral_flatness = geom_mean / arith_mean if arith_mean > 0 else 0.0

    raw_commits = np.expm1(commit_log)   # undo log1p to get raw counts
    mu, sigma = raw_commits.mean(), raw_commits.std()
    if mu + sigma > 0:
        result.burstiness = float((sigma - mu) / (sigma + mu))

    result.active_day_ratio = float((raw_commits > 0).mean())

    return result


# ---------------------------------------------------------------------------
# Plot generators
# ---------------------------------------------------------------------------

def _date_axis(ax, dates: list[date], x: np.ndarray) -> None:
    """Helper: set an x-axis of matplotlib dates."""
    import matplotlib.dates as mdates
    from datetime import datetime
    dt_dates = [datetime(d.year, d.month, d.day) for d in dates]
    ax.set_xlim(dt_dates[0], dt_dates[-1])
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")


def plot_activity(
    signals: np.ndarray,
    dates: list[date],
    dsp: DspResult,
    anomaly_ranges: list[tuple[date, date, str]],
    out_path: str,
) -> None:
    """Save the raw-vs-filtered signal plot with anomaly highlights.

    Args:
        signals:       (2, N) array from build_signals.
        dates:         List of N dates.
        dsp:           DspResult from compute_dsp.
        anomaly_ranges: List of (start_date, end_date, kind) for shading.
        out_path:      Absolute path for the output PNG.
    """
    from datetime import datetime
    raw = np.expm1(signals[0])
    dt_dates = [datetime(d.year, d.month, d.day) for d in dates]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    fig.suptitle("Repository Activity Signal", fontsize=14, fontweight="bold")

    # Top panel: raw commits + 7-day moving average
    ax1.bar(dt_dates, raw, color="#4c8eda", alpha=0.6, width=1, label="Commits/day")
    if len(dsp.moving_avg) == len(dt_dates):
        ax1.plot(dt_dates, np.expm1(dsp.moving_avg), color="#ff9f40",
                 linewidth=1.5, label="7-day avg")
    ax1.set_ylabel("Commits per day")
    ax1.legend(fontsize=8)

    # Shade anomaly windows
    colors = {"burst": "#ff4444", "rhythm_break": "#ffaa00", "inactivity_gap": "#888888"}
    for start_d, end_d, kind in anomaly_ranges:
        c = colors.get(kind, "#cccccc")
        ax1.axvspan(datetime(start_d.year, start_d.month, start_d.day),
                    datetime(end_d.year, end_d.month, end_d.day),
                    alpha=0.25, color=c, label=kind)

    # Bottom panel: Butterworth filtered (log-scale)
    if len(dsp.filtered) == len(dt_dates):
        ax2.plot(dt_dates, dsp.filtered, color="#2ecc71", linewidth=1.5)
    ax2.set_ylabel("Filtered signal (log1p, detrended)")
    ax2.set_xlabel("Date")

    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax2.get_xticklabels(), rotation=30, ha="right")

    # Deduplicate legend entries
    handles, labels = ax1.get_legend_handles_labels()
    seen: set[str] = set()
    unique = [(h, l) for h, l in zip(handles, labels) if not (l in seen or seen.add(l))]
    if unique:
        ax1.legend(*zip(*unique), fontsize=8)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_spectrum(dsp: DspResult, out_path: str) -> None:
    """Save the magnitude spectrum plot with the dominant peak marked.

    Args:
        dsp:      DspResult from compute_dsp.
        out_path: Absolute path for the output PNG.
    """
    if len(dsp.freqs) == 0:
        return

    fig, ax = plt.subplots(figsize=(10, 4))
    # Convert frequency axis to period in days for readability
    freqs = dsp.freqs
    mag = dsp.magnitude

    # Only plot f > 0 (skip DC)
    mask = freqs > 0
    periods = np.where(freqs[mask] > 0, 1.0 / freqs[mask], 0)
    ax.semilogy(periods, mag[mask], color="#4c8eda", linewidth=1.2, label="Magnitude")

    # Mark dominant period
    if dsp.dominant_period_days > 0:
        ax.axvline(dsp.dominant_period_days, color="#ff4444", linestyle="--",
                   linewidth=1.5,
                   label=f"Peak: {dsp.dominant_period_days:.1f} days "
                         f"(strength {dsp.dominant_strength:.2f})")

    # Mark weekly rhythm reference
    ax.axvline(7, color="#2ecc71", linestyle=":", linewidth=1,
               label="7-day reference")

    ax.set_xlabel("Period (days)")
    ax.set_ylabel("Magnitude (log scale)")
    ax.set_title("Frequency Spectrum of Commit Activity")
    ax.set_xlim(1, min(180, periods.max() if len(periods) else 180))
    ax.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_spectrogram(dsp: DspResult, dates: list[date], out_path: str) -> None:
    """Save the STFT spectrogram showing how the rhythm evolves over time.

    Args:
        dsp:      DspResult from compute_dsp.
        dates:    List of N dates (for x-axis labels).
        out_path: Absolute path for the output PNG.
    """
    if dsp.stft_z.size == 0:
        return

    from datetime import datetime, timedelta as td
    first_dt = datetime(dates[0].year, dates[0].month, dates[0].day)

    fig, ax = plt.subplots(figsize=(12, 5))
    # t_stft is in samples (days from start); convert to real dates for the label
    t_days = dsp.stft_t
    f_days = dsp.stft_f

    # Mask DC row (f=0)
    freq_mask = f_days > 0
    f_plot = f_days[freq_mask]
    z_plot = dsp.stft_z[freq_mask, :]

    # X-axis: approximate calendar dates from offset in days
    t_dates = np.array([first_dt + td(days=float(t)) for t in t_days])

    pcm = ax.pcolormesh(
        t_dates, 1.0 / f_plot[::-1], z_plot[::-1, :],
        shading="gouraud", cmap="magma",
    )
    plt.colorbar(pcm, ax=ax, label="Magnitude")
    ax.set_ylabel("Period (days)")
    ax.set_xlabel("Date")
    ax.set_title("Spectrogram — How Rhythm Changes Over Time")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
