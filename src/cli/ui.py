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