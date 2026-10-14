"""Activity Signal Analyzer orchestrator for DocXPilot.

Ties together signal extraction, DSP processing, plot generation, and
model inference into a single `analyze_activity()` function that returns
an :class:`~analyzers.models.ActivityReport`.

This is the 7th analyzer in the pipeline.  It is intentionally separate
from the six existing analyzers so those are never modified.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from analyzers.models import ActivityAnomaly, ActivityReport

console = Console()


def analyze_activity(
    project_path: str,
    output_dir: str | None = None,
) -> ActivityReport:
    """Run the full activity analysis pipeline.

    Args:
        project_path: Absolute path to the project / git repository root.
        output_dir:   Directory where PNG plots will be saved.
                      If None, plots go to a ``.docxpilot_plots`` folder
                      inside *project_path*.

    Returns:
        An :class:`~analyzers.models.ActivityReport`.
        If analysis cannot run (short history, not a git repo, etc.) the
        report will have ``available=False`` with an explanation in
        ``reason``.  It will never raise an exception.
    """
    report = ActivityReport()

    # ------------------------------------------------------------------
    # 1. Signal extraction
    # ------------------------------------------------------------------
    try:
        from analyzers.activity_signal import build_signals
        dates, signals = build_signals(project_path)
    except ValueError as exc:
        report.available = False
        report.reason = str(exc)
        return report
    except Exception as exc:
        report.available = False
        report.reason = f"Unexpected error during signal extraction: {exc}"
        return report

    # ------------------------------------------------------------------
    # 2. Basic stats
    # ------------------------------------------------------------------
    N = signals.shape[1]
    raw_commits = np.expm1(signals[0])

    report.available = True
    report.span_days     = N
    report.active_days   = int((raw_commits > 0).sum())
    report.total_commits = int(raw_commits.sum())

    # ------------------------------------------------------------------
    # 3. DSP
    # ------------------------------------------------------------------
    try:
        from analyzers.activity_dsp import compute_dsp
        dsp = compute_dsp(signals, dates)

        report.dominant_period_days   = round(dsp.dominant_period_days, 1)
        report.dominant_strength      = round(dsp.dominant_strength, 4)
        report.autocorr_period_days   = round(dsp.autocorr_period_days, 1)
        report.period_mismatch        = dsp.period_mismatch
        report.spectral_entropy       = round(dsp.spectral_entropy, 4)
        report.spectral_flatness      = round(dsp.spectral_flatness, 4)
        report.burstiness             = round(dsp.burstiness, 4)
        report.active_day_ratio       = round(dsp.active_day_ratio, 4)
    except Exception as exc:
        dsp = None
        console.print(f"[yellow]  DSP warning: {exc}[/yellow]")

    # ------------------------------------------------------------------
    # 4. Plots
    # ------------------------------------------------------------------
    if output_dir is None:
        plot_dir = Path(project_path) / ".docxpilot_plots"
    else:
        plot_dir = Path(output_dir)
    plot_dir.mkdir(parents=True, exist_ok=True)

    plot_paths: list[str] = []
    anomaly_date_ranges: list[tuple[date, date, str]] = []  # populated later

    # ------------------------------------------------------------------
    # 5. Anomaly detection
    # ------------------------------------------------------------------
    # 5a. Inactivity gaps (rule-based — model cannot detect these)
    try:
        from ml.infer import detect_inactivity_gaps
        gap_anomalies = detect_inactivity_gaps(signals, dates)
        for start_d, end_d, kind, score in gap_anomalies:
            report.anomalies.append(ActivityAnomaly(
                start_date=start_d.isoformat(),
                end_date=end_d.isoformat(),
                kind=kind,
                score=score,
                description=f"Inactivity gap of {int(score)} days",
            ))
            anomaly_date_ranges.append((start_d, end_d, kind))
    except Exception as exc:
        console.print(f"[yellow]  Gap detection warning: {exc}[/yellow]")

    # 5b. Model-based (bursts + rhythm breaks)
    try:
        from ml.infer import detect_anomalies_with_model
        model_anomalies, model_used = detect_anomalies_with_model(signals, dates)
        report.model_used = model_used
        for start_d, end_d, kind, score in model_anomalies:
            report.anomalies.append(ActivityAnomaly(
                start_date=start_d.isoformat(),
                end_date=end_d.isoformat(),
                kind=kind,
                score=score,
                description=f"Autoencoder-detected {kind} (score {score:.2f}×threshold)",
            ))
            anomaly_date_ranges.append((start_d, end_d, kind))
    except Exception as exc:
        console.print(f"[yellow]  Model inference warning: {exc}[/yellow]")

    # ------------------------------------------------------------------
    # 6. Save plots
    # ------------------------------------------------------------------
    if dsp is not None:
        try:
            from analyzers.activity_dsp import plot_activity, plot_spectrum, plot_spectrogram

            act_path = str(plot_dir / "activity.png")
            plot_activity(signals, dates, dsp, anomaly_date_ranges, act_path)
            plot_paths.append(act_path)

            spec_path = str(plot_dir / "spectrum.png")
            plot_spectrum(dsp, spec_path)
            plot_paths.append(spec_path)

            sg_path = str(plot_dir / "spectrogram.png")
            plot_spectrogram(dsp, dates, sg_path)
            plot_paths.append(sg_path)
        except Exception as exc:
            console.print(f"[yellow]  Plot warning: {exc}[/yellow]")

    report.plot_paths = plot_paths

    # ------------------------------------------------------------------
    # 7. Build human-readable summary lines
    # ------------------------------------------------------------------
    report.summary_lines = _build_summary(report)

    return report


def _rhythm_label(period_days: float) -> str:
    """Return a human label for a dominant period."""
    if period_days <= 0:
        return "unknown"
    if abs(period_days - 7) <= 1.5:
        return "weekly rhythm"
    if abs(period_days - 14) <= 2:
        return "biweekly rhythm"
    if abs(period_days - 30) <= 5:
        return "monthly rhythm"
    return f"{period_days:.0f}-day rhythm"


def _build_summary(report: ActivityReport) -> list[str]:
    lines = [
        f"Span: {report.span_days} days | "
        f"Active days: {report.active_days} | "
        f"Commits: {report.total_commits}",
    ]
    if report.dominant_period_days > 0:
        label = _rhythm_label(report.dominant_period_days)
        lines.append(
            f"Dominant period: {report.dominant_period_days:.1f} days "
            f"({label}), strength {report.dominant_strength:.2f}"
        )
    if report.period_mismatch:
        lines.append(
            f"  [!] FFT period ({report.dominant_period_days:.1f}d) vs "
            f"autocorr ({report.autocorr_period_days:.1f}d) mismatch"
        )

    bursts    = [a for a in report.anomalies if a.kind == "burst"]
    rhythmbs  = [a for a in report.anomalies if a.kind == "rhythm_break"]
    inactives = [a for a in report.anomalies if a.kind == "inactivity_gap"]

    parts = []
    if bursts:
        parts.append(f"{len(bursts)} burst window(s)")
    if rhythmbs:
        parts.append(f"{len(rhythmbs)} rhythm break(s)")
    if inactives:
        longest = max(int(a.score) for a in inactives)
        parts.append(f"{len(inactives)} inactivity gap(s) (longest {longest} days)")
    if parts:
        lines.append("Anomalies: " + ", ".join(parts))
    else:
        lines.append("Anomalies: none detected")

    if not report.model_used:
        lines.append("  (deep learning model not available — DSP only)")

    return lines


# ---------------------------------------------------------------------------
# Rich terminal print
# ---------------------------------------------------------------------------

def print_activity_summary(report: ActivityReport) -> None:
    """Print a formatted Rich summary of the activity report."""
    if not report.available:
        console.print(
            Panel(
                f"[yellow]Activity analysis skipped:[/yellow] {report.reason}",
                title="[bold]Activity Signal Analysis[/bold]",
                border_style="yellow",
            )
        )
        return

    table = Table(
        show_header=False,
        border_style="bright_black",
        padding=(0, 2),
    )
    table.add_column("Key", style="dim")
    table.add_column("Value", style="bold white")

    for line in report.summary_lines:
        if line.startswith("  "):
            table.add_row("", f"[yellow]{line.strip()}[/yellow]")
        elif line.startswith("Anomalies"):
            key, _, val = line.partition(": ")
            color = "green" if "none" in val else "red"
            table.add_row(key, f"[{color}]{val}[/{color}]")
        else:
            key, _, val = line.partition(": ")
            if key and val:
                table.add_row(key, val)
            else:
                table.add_row("", line)

    if report.plot_paths:
        table.add_row("Plots saved", "\n".join(report.plot_paths))

    console.print()
    console.print(
        Panel(
            table,
            title="[bold cyan]Activity Signal Analysis[/bold cyan]",
            border_style="cyan",
        )
    )
