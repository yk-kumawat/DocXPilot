"""Output writer for DocXPilot.

Saves generated Markdown documents to a user-specified directory,
creating the directory if it does not yet exist.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

# Maps human-readable doc type names to output filenames
_FILENAME_MAP: dict[str, str] = {
    "README": "README.md",
    "Project Report": "PROJECT_REPORT.md",
    "Installation Guide": "INSTALLATION_GUIDE.md",
    "Software Architecture Document": "SOFTWARE_ARCHITECTURE.md",
    "API Documentation": "API_DOCUMENTATION.md",
    "Developer Onboarding Guide": "DEVELOPER_ONBOARDING.md",
    "Deployment Guide": "DEPLOYMENT_GUIDE.md",
    "Code Quality Report": "CODE_QUALITY_REPORT.md",
    "CHANGELOG": "CHANGELOG.md",
}


class DocWriter:
    """Saves generated Markdown documents to disk."""

    def save(
        self,
        documents: dict[str, str],
        output_dir: str,
        knowledge=None,
    ) -> list[str]:
        """Write each document to *output_dir*.

        Creates the directory (and any parents) if it does not exist.

        Args:
            documents:  Mapping of ``{doc_type: markdown_content}``.
            output_dir: Path to the output directory.
            knowledge:  Optional ProjectKnowledge object. If provided,
                        activity PNG plots are copied next to the docs.

        Returns:
            A list of absolute file paths that were written.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        written: list[str] = []

        for doc_type, content in documents.items():
            filename = _FILENAME_MAP.get(doc_type, f"{doc_type.upper().replace(' ', '_')}.md")
            filepath = out / filename

            try:
                filepath.write_text(content, encoding="utf-8")
                written.append(str(filepath))
            except OSError as exc:
                console.print(f"[red]Failed to write {filename}: {exc}[/red]")

        # Copy activity plots if available
        if knowledge is not None:
            act = getattr(knowledge, "activity", None)
            if act is not None and act.available and act.plot_paths:
                for src in act.plot_paths:
                    src_path = Path(src)
                    if src_path.exists():
                        dst = out / src_path.name
                        try:
                            shutil.copy2(str(src_path), str(dst))
                            written.append(str(dst))
                        except OSError as exc:
                            console.print(f"[red]Failed to copy plot {src_path.name}: {exc}[/red]")

        return written

    def print_summary(self, written: list[str], output_dir: str) -> None:
        """Print a Rich table summarising what was saved.

        Args:
            written: List of absolute paths that were successfully written.
            output_dir: The output directory path (for display).
        """
        console.print()
        console.print(
            f"[bold green]Documentation saved to:[/bold green] [cyan]{output_dir}[/cyan]"
        )
        console.print()

        table = Table(
            title="Generated Documents",
            show_header=True,
            header_style="bold blue",
            border_style="bright_black",
        )
        table.add_column("#", style="dim", width=4)
        table.add_column("File", style="bold white")
        table.add_column("Size", justify="right", style="cyan")

        for i, filepath in enumerate(written, start=1):
            p = Path(filepath)
            size_kb = p.stat().st_size / 1024 if p.exists() else 0
            table.add_row(str(i), p.name, f"{size_kb:.1f} KB")

        console.print(table)
        console.print()
