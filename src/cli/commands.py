"""CLI commands for DocXPilot.

Entry point registered as the ``docxpilot`` console script.
Wires the full pipeline: analyze -> aggregate -> AI generate -> save.
"""

from __future__ import annotations

import os
from typing import Optional

import typer
from rich.console import Console

from cli.ui import (
    title,
    success,
    error,
    info,
    section,
    main_menu,
    select_documents_menu,
    confirm_generation,
    ask_project_path,
    display_metrics_summary,
    ALL_DOC_TYPES,
)

app = typer.Typer(
    name="docxpilot",
    help="DocXPilot — AI-enhanced documentation generator.",
    add_completion=False,
)

console = Console()


# ---------------------------------------------------------------------------
# Shared pipeline helper
# ---------------------------------------------------------------------------

def _run_pipeline(
    project_path: str,
    selected_docs: list[str],
    output_dir: str,
    api_key: str | None = None,
    model: str | None = None,
    no_ai: bool = False,
    no_activity: bool = False,
) -> None:
    """Run the full DocXPilot pipeline.

    Args:
        project_path:  Path to the project to analyze.
        selected_docs: List of document type names to generate.
        output_dir:    Directory where documents will be saved.
        api_key:       Gemini API key (overrides env variable).
        no_ai:         If True, skip AI generation and only print metrics.
        no_activity:   If True, skip the activity signal analyzer step.
    """
    from aggregator.knowledge_base import KnowledgeAggregator
    from output.writer import DocWriter

    section("Step 1 / 3 — Analyzing project")
    info(f"Project: {project_path}")

    aggregator = KnowledgeAggregator(no_activity=no_activity)
    knowledge = aggregator.aggregate(project_path)

    display_metrics_summary(knowledge)

    # Print activity summary if available
    if not no_activity and knowledge.activity is not None:
        from analyzers.activity_analyzer import print_activity_summary
        print_activity_summary(knowledge.activity)

    if no_ai:
        success("Metrics-only mode (--no-ai): skipping AI generation.")
        return

    section("Step 2 / 3 — Generating documents with Gemini AI")

    try:
        from ai.gemini_client import GeminiClient
        from ai.doc_generator import DocGenerator

        client = GeminiClient(model=model, api_key=api_key)
        generator = DocGenerator(client)
        documents = generator.generate(knowledge, selected_docs)
    except EnvironmentError as exc:
        error(str(exc))
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # noqa: BLE001
        error(f"AI generation error: {exc}")
        raise typer.Exit(code=1) from exc

    section("Step 3 / 3 — Saving documents")

    writer = DocWriter()
    written = writer.save(documents, output_dir, knowledge=knowledge)
    writer.print_summary(written, output_dir)

    success(f"Done! {len(written)} document(s) saved to {output_dir}")


# ---------------------------------------------------------------------------
# Interactive entry point (no subcommand)
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="Gemini API key (overrides GEMINI_API_KEY env variable).",
        envvar="GEMINI_API_KEY",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help="Gemini model to use (default: gemini-3.6-flash).",
        envvar="GEMINI_MODEL",
    ),
    no_ai: bool = typer.Option(
        False,
        "--no-ai",
        help="Analyze the project and display metrics without calling Gemini.",
    ),
    no_activity: bool = typer.Option(
        False,
        "--no-activity",
        help="Skip the activity signal analyzer (faster, no numpy/scipy needed).",
    ),
) -> None:
    """DocXPilot — AI-enhanced documentation generator."""

    if ctx.invoked_subcommand is not None:
        return

    title("DocXPilot — AI-enhanced documentation generator")
    console.print("[dim]Use arrow keys to navigate, Enter to select.[/dim]")

    # Keep track of selected docs between menu visits (start with all checked)
    selected_docs: list[str] = list(ALL_DOC_TYPES)

    while True:
        choice = main_menu()

        if choice is None or choice == "Exit":
            console.print("[dim]Goodbye![/dim]")
            raise typer.Exit()

        elif choice == "Select Documents to Generate":
            result = select_documents_menu(pre_selected=selected_docs)
            if result is not None:
                selected_docs = result
                if selected_docs:
                    success(f"Selected {len(selected_docs)} document(s).")
                else:
                    console.print("[yellow]No documents selected — nothing will be generated.[/yellow]")

        elif choice == "Generate Documentation":
            if not selected_docs:
                console.print("[yellow]No documents selected. Choose 'Select Documents to Generate' first.[/yellow]")
                continue

            # Ask for project path
            project_path = ask_project_path()
            if project_path is None:
                continue

            # Ask for output directory
            output_dir = confirm_generation("DocXPilot")
            if output_dir is None:
                continue

            console.print()

            try:
                _run_pipeline(
                    project_path=project_path,
                    selected_docs=selected_docs,
                    output_dir=output_dir,
                    api_key=api_key,
                    model=model,
                    no_ai=no_ai,
                    no_activity=no_activity,
                )
            except SystemExit:
                pass

            break  # Exit after generation


# ---------------------------------------------------------------------------
# Subcommand: generate (non-interactive / scriptable)
# ---------------------------------------------------------------------------

@app.command()
def generate(
    project_path: str = typer.Argument(
        ".",
        help="Path to the project to analyze.",
    ),
    output_dir: str = typer.Option(
        "DocXPilot",
        "--output", "-o",
        help="Directory to save generated documents.",
    ),
    docs: Optional[str] = typer.Option(
        None,
        "--docs", "-d",
        help=(
            "Comma-separated list of documents to generate. "
            "Defaults to all. "
            "Options: README, 'Project Report', 'Installation Guide', "
            "'Software Architecture Document', 'API Documentation', "
            "'Developer Onboarding Guide', 'Deployment Guide', "
            "'Code Quality Report', CHANGELOG"
        ),
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="Gemini API key (overrides GEMINI_API_KEY env variable).",
        envvar="GEMINI_API_KEY",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help="Gemini model to use (default: gemini-3.6-flash).",
        envvar="GEMINI_MODEL",
    ),
    no_ai: bool = typer.Option(
        False,
        "--no-ai",
        help="Analyze only — do not call Gemini.",
    ),
    no_activity: bool = typer.Option(
        False,
        "--no-activity",
        help="Skip the activity signal analyzer.",
    ),
) -> None:
    """Generate documentation for a project (non-interactive)."""

    title("DocXPilot — AI-enhanced documentation generator")

    # Resolve selected docs
    if docs:
        selected_docs = [d.strip() for d in docs.split(",")]
        # Validate
        invalid = [d for d in selected_docs if d not in ALL_DOC_TYPES]
        if invalid:
            error(f"Unknown document types: {', '.join(invalid)}")
            console.print(f"Valid options: {', '.join(ALL_DOC_TYPES)}")
            raise typer.Exit(code=1)
    else:
        selected_docs = list(ALL_DOC_TYPES)

    from pathlib import Path as _Path
    resolved_project = str(_Path(project_path).resolve())

    _run_pipeline(
        project_path=resolved_project,
        selected_docs=selected_docs,
        output_dir=output_dir,
        api_key=api_key,
        model=model,
        no_ai=no_ai,
        no_activity=no_activity,
    )


# ---------------------------------------------------------------------------
# Subcommand: activity (standalone, no Gemini key needed)
# ---------------------------------------------------------------------------

@app.command()
def activity(
    project_path: str = typer.Argument(
        ".",
        help="Path to the git repository to analyze.",
    ),
    out: str = typer.Option(
        "",
        "--out", "-o",
        help="Directory to save plots (default: <project>/.docxpilot_plots).",
    ),
) -> None:
    """Analyze repository activity signals without generating documentation.

    Does NOT require a Gemini API key. Ideal for lab demos and quick checks.
    """
    from pathlib import Path as _Path
    from analyzers.activity_analyzer import analyze_activity, print_activity_summary

    title("DocXPilot — Activity Signal Analyzer")

    resolved = str(_Path(project_path).resolve())
    info(f"Analyzing: {resolved}")

    output_dir = out.strip() if out.strip() else None

    section("Running activity signal analysis...")
    report = analyze_activity(resolved, output_dir=output_dir)
    print_activity_summary(report)

    if report.available and report.plot_paths:
        success(f"{len(report.plot_paths)} plot(s) saved.")
        for p in report.plot_paths:
            info(f"  {p}")
    elif not report.available:
        console.print(f"[yellow]Analysis skipped: {report.reason}[/yellow]")