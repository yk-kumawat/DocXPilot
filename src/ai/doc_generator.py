"""Document generator orchestrator for DocXPilot.

Takes a :class:`~analyzers.models.ProjectKnowledge` object and a list of
document types, calls the appropriate Gemini prompt builder for each,
and returns a mapping of ``{doc_type: markdown_content}``.
"""

from __future__ import annotations

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from analyzers.models import ProjectKnowledge
from ai.gemini_client import GeminiClient
from ai.prompts import PROMPT_BUILDERS

console = Console()


class DocGenerator:
    """Orchestrates AI-powered document generation for selected doc types."""

    def __init__(self, client: GeminiClient) -> None:
        self._client = client

    def generate(
        self,
        knowledge: ProjectKnowledge,
        doc_types: list[str],
    ) -> dict[str, str]:
        """Generate one Markdown document per requested doc type.

        Args:
            knowledge: The aggregated project knowledge.
            doc_types: List of document type names (must be keys in
                :data:`~ai.prompts.PROMPT_BUILDERS`).

        Returns:
            A dict mapping each doc type to its generated Markdown string.
            Failed generations map to an error-placeholder string.
        """
        results: dict[str, str] = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task(
                "[magenta]Generating documents...", total=len(doc_types)
            )

            for doc_type in doc_types:
                progress.update(
                    task, description=f"[magenta]Generating {doc_type}..."
                )

                builder = PROMPT_BUILDERS.get(doc_type)
                if builder is None:
                    console.print(
                        f"[yellow]  Warning: no prompt builder for '{doc_type}', skipping.[/yellow]"
                    )
                    progress.advance(task)
                    continue

                try:
                    prompt = builder(knowledge)
                    markdown = self._client.generate(prompt)
                    results[doc_type] = markdown
                    console.print(f"  [green]Done:[/green] {doc_type}")
                except Exception as exc:  # noqa: BLE001
                    error_md = (
                        f"# {doc_type}\n\n"
                        f"> **Generation failed:** {exc}\n\n"
                        "Please retry or check your Gemini API key and quota."
                    )
                    results[doc_type] = error_md
                    console.print(f"  [red]Failed:[/red] {doc_type} — {exc}")
                finally:
                    progress.advance(task)

        return results
