"""CLI UI helpers for DocXPilot.

Provides Rich-powered display helpers and questionary-based menus.
"""

import io
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
import questionary

# Force UTF-8 output on Windows so that Rich's Unicode characters
# (spinner glyphs, box-drawing chars, etc.) don't raise UnicodeEncodeError.
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

console = Console(force_terminal=True, highlight=False)

# All 9 document types supported by DocXPilot
ALL_DOC_TYPES = [
    "README",
    "Project Report",
    "Installation Guide",
    "Software Architecture Document",
    "API Documentation",
    "Developer Onboarding Guide",
    "Deployment Guide",
    "Code Quality Report",
    "CHANGELOG",
]


def title(text: str) -> None:
    console.print(Panel.fit(text, style="bold blue"))


def success(text: str) -> None:
    console.print(f"[bold green]>> {text}[/bold green]")


def error(text: str) -> None:
    console.print(f"[bold red]!! {text}[/bold red]")


def info(text: str) -> None:
    console.print(f"[cyan]{text}[/cyan]")


def section(text: str) -> None:
    console.print()
    console.print(Rule(f"[bold]{text}[/bold]", style="blue"))
    console.print()


def main_menu() -> str | None:
    console.print()
    console.print("Main Menu", style="bold underline")
    console.print()

    choices = [
        "Generate Documentation",
        "Select Documents to Generate",
        "Exit",
    ]

    choice = questionary.select(
        "",
        choices=choices,
        pointer="❯",
        qmark="",
        instruction="",
    ).ask()

    return choice


def select_documents_menu(pre_selected: list[str] | None = None) -> list[str] | None:
    """Show a checkbox menu for selecting which documents to generate.

    Args:
        pre_selected: Doc type names that should be pre-checked.
                      Defaults to all doc types checked.

    Returns:
        The list of selected doc type strings, or None if cancelled.
    """
    console.print()
    console.print("Select Documents to Generate", style="bold underline")
    console.print("[dim]Space to toggle · Enter to confirm[/dim]")
    console.print()

    checked_set = set(pre_selected) if pre_selected is not None else set(ALL_DOC_TYPES)

    choices = [
        questionary.Choice(doc_type, checked=(doc_type in checked_set))
        for doc_type in ALL_DOC_TYPES
    ]

    custom_style = questionary.Style(
        [
            ("selected", "noreverse"),
            ("highlighted", "noreverse"),
        ]
    )

    selected = questionary.checkbox(
        "",
        choices=choices,
        pointer="❯",
        qmark="",
        instruction="(Use <space> to select, <enter> to confirm)",
        style=custom_style,
    ).ask()

    return selected


def confirm_generation(output_dir: str = "DocXPilot") -> str | None:
    """Prompt the user to confirm or customise the output directory.

    Args:
        output_dir: Default sub-directory name relative to cwd.

    Returns:
        Resolved absolute path string, or None if the user cancelled.
    """
    cwd = Path.cwd().resolve()
    default_path = (cwd / output_dir).resolve()

    console.print()
    console.print(f"Output directory: [bold cyan]{default_path}[/bold cyan]")
    console.print("[dim]Press Enter to confirm or paste a custom path[/dim]")

    while True:
        try:
            user_input = input().strip().strip("\"'")
            if not user_input:
                return str(default_path)

            try:
                chosen_path = Path(user_input).resolve()
            except (OSError, ValueError):
                error("Invalid path format. Please enter a valid path.")
                console.print("[dim]Please enter a valid path or press Enter for default:[/dim]")
                continue

            if not chosen_path.is_relative_to(cwd):
                error(
                    f"Path must be inside the current working directory ({cwd})"
                )
                console.print("[dim]Please enter a valid path or press Enter for default:[/dim]")
                continue

            console.print(f"Custom output directory: [bold cyan]{chosen_path}[/bold cyan]")
            return str(chosen_path)
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled by user.[/yellow]")
            return None


def ask_project_path() -> str | None:
    """Ask the user for the project path to analyze.

    Returns:
        Resolved absolute path string, or None if cancelled.
    """
    console.print()
    cwd = str(Path.cwd().resolve())
    console.print(
        f"Project path to analyze: [bold cyan]{cwd}[/bold cyan]"
    )
    console.print("[dim]Press Enter to use the current directory, or paste a custom path[/dim]")

    while True:
        try:
            user_input = input().strip().strip("\"'")
            if not user_input:
                return cwd

            try:
                chosen = Path(user_input).resolve()
            except (OSError, ValueError):
                error("Invalid path. Please enter a valid directory path.")
                continue

            if not chosen.is_dir():
                error(f"'{chosen}' is not a directory. Please enter a valid directory path.")
                continue

            return str(chosen)
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled by user.[/yellow]")
            return None


def display_metrics_summary(knowledge) -> None:
    """Print a brief summary of analysis results before AI generation.

    Args:
        knowledge: A :class:`~analyzers.models.ProjectKnowledge` instance.
    """
    from rich.table import Table

    console.print()
    console.print(Rule("[bold green]Analysis Complete[/bold green]", style="green"))
    console.print()

    table = Table(
        show_header=False,
        border_style="bright_black",
        padding=(0, 2),
    )
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold white")

    table.add_row("Project", knowledge.project_name)
    table.add_row("Layout", knowledge.project_layout)
    table.add_row("Total files", str(knowledge.total_files))
    table.add_row("Total lines", f"{knowledge.total_lines:,}")

    langs = sorted(
        knowledge.language_summaries.values(),
        key=lambda s: s.file_count,
        reverse=True,
    )
    if langs:
        top_langs = ", ".join(f"{s.language} ({s.file_count})" for s in langs[:5])
        table.add_row("Languages", top_langs)

    if knowledge.dependency_report.managers_found:
        table.add_row(
            "Package managers",
            ", ".join(knowledge.dependency_report.managers_found),
        )

    if knowledge.git_info.is_git_repo:
        table.add_row("Git commits", str(knowledge.git_info.total_commits))
        table.add_row(
            "Contributors",
            str(len(knowledge.git_info.contributors)),
        )

    console.print(table)
    console.print()
