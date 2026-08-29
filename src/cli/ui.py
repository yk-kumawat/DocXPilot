from rich.console import Console
from rich.panel import Panel

console = Console()


def title(text: str):
    console.print(Panel.fit(text, style="bold blue"))


def success(text: str):
    console.print(f"[bold green]✓ {text}[/bold green]")


def error(text: str):
    console.print(f"[bold red]✗ {text}[/bold red]")