import os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
import questionary

console = Console()


def title(text: str):
    console.print(Panel.fit(text, style="bold blue"))


def success(text: str):
    console.print(f"[bold green]✓ {text}[/bold green]")


def error(text: str):
    console.print(f"[bold red]✗ {text}[/bold red]")


def main_menu():

    console.print()
    console.print("Main Menu", style="bold underline")
    console.print()

    choices = [
        "Generate Documentation",
        "Select Documents to Generate",
        "Set Document Formats",
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


def select_documents_menu():

    console.print()
    console.print("Select Documents to Generate", style="bold underline")
    console.print()

    choices = [
        questionary.Choice("Project Report", checked=True),
        "Installation guide",
        "Software Architecture Document",
        "Developer Onboarding Guide",
        "Deployment Guide",
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

    cwd = Path.cwd().resolve()
    default_path = (cwd / output_dir).resolve()
    console.print()
    console.print(f"Output directory: [bold cyan]{default_path}[/bold cyan]")
    console.print("[dim]Note: Press Enter to confirm or paste custom path[/dim]")

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
                error(f"Path must be inside the directory where the CLI is currently running ({cwd})")
                console.print("[dim]Please enter a valid path or press Enter for default:[/dim]")
                continue

            console.print(f"Custom output directory: [bold cyan]{chosen_path}[/bold cyan]")
            return str(chosen_path)
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled by user.[/yellow]")
            return None
