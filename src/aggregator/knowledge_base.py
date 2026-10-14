"""Knowledge aggregator for DocXPilot.

Runs all 6 analyzers in sequence and merges their outputs
into a single :class:`~analyzers.models.ProjectKnowledge` object
ready to be sent to the Gemini AI for document generation.
"""

from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from analyzers.models import ProjectKnowledge, LanguageSummary
from analyzers.code_analyzer import analyze_file
from analyzers.directory_analyzer import (
    build_directory_tree,
    count_file_types,
    detect_project_layout,
    get_all_source_files,
)
from analyzers.git_analyzer import analyze_git
from analyzers.dependency_analyzer import analyze_dependencies
from analyzers.config_analyzer import analyze_configs
from analyzers.docs_reader import read_existing_docs

console = Console()


class KnowledgeAggregator:
    """Orchestrates all analyzers and produces a :class:`ProjectKnowledge` object."""

    def __init__(self, no_activity: bool = False) -> None:
        self._no_activity = no_activity

    def aggregate(self, project_path: str) -> ProjectKnowledge:
        """Run all 6 analyzers and combine their results.

        Args:
            project_path: Absolute or relative path to the project root.

        Returns:
            A fully populated :class:`ProjectKnowledge` instance.
        """
        root = Path(project_path).resolve()
        knowledge = ProjectKnowledge(
            project_path=str(root),
            project_name=root.name,
        )

        steps = [
            ("Directory structure", self._run_directory_analyzer),
            ("Source code", self._run_code_analyzer),
            ("Git history", self._run_git_analyzer),
            ("Dependencies", self._run_dependency_analyzer),
            ("Configuration files", self._run_config_analyzer),
            ("Existing documentation", self._run_docs_reader),
        ]
        if not self._no_activity:
            steps.append(("Activity signal", self._run_activity_analyzer))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task("[cyan]Analyzing project...", total=len(steps))

            for label, fn in steps:
                progress.update(task, description=f"[cyan]Analyzing {label}...")
                try:
                    fn(str(root), knowledge)
                except Exception as exc:  # noqa: BLE001
                    console.print(f"[yellow]Warning ({label}): {exc}[/yellow]")
                finally:
                    progress.advance(task)

        return knowledge

    # -- Individual analyzer runners --

    @staticmethod
    def _run_directory_analyzer(project_path: str, knowledge: ProjectKnowledge) -> None:
        knowledge.directory_tree = build_directory_tree(project_path)
        knowledge.file_type_counts = count_file_types(project_path)
        knowledge.project_layout = detect_project_layout(project_path)

    @staticmethod
    def _run_code_analyzer(project_path: str, knowledge: ProjectKnowledge) -> None:
        source_files = get_all_source_files(project_path)
        lang_map: dict[str, LanguageSummary] = {}

        for filepath in source_files:
            analysis = analyze_file(filepath, project_path)
            if analysis is None:
                continue

            knowledge.file_analyses.append(analysis)
            knowledge.total_files += 1
            knowledge.total_lines += analysis.metrics.total_lines

            lang = analysis.info.language
            if lang not in lang_map:
                lang_map[lang] = LanguageSummary(language=lang)

            summary = lang_map[lang]
            summary.file_count += 1
            summary.total_lines += analysis.metrics.total_lines
            summary.code_lines += analysis.metrics.code_lines
            summary.comment_lines += analysis.metrics.comment_lines
            summary.blank_lines += analysis.metrics.blank_lines

        knowledge.language_summaries = lang_map

    @staticmethod
    def _run_git_analyzer(project_path: str, knowledge: ProjectKnowledge) -> None:
        knowledge.git_info = analyze_git(project_path)

    @staticmethod
    def _run_dependency_analyzer(project_path: str, knowledge: ProjectKnowledge) -> None:
        knowledge.dependency_report = analyze_dependencies(project_path)

    @staticmethod
    def _run_config_analyzer(project_path: str, knowledge: ProjectKnowledge) -> None:
        configs, env_vars, deploy_targets = analyze_configs(project_path)
        knowledge.configs = configs
        knowledge.env_variables = env_vars
        knowledge.deployment_targets = deploy_targets

    @staticmethod
    def _run_docs_reader(project_path: str, knowledge: ProjectKnowledge) -> None:
        knowledge.existing_docs = read_existing_docs(project_path)

    @staticmethod
    def _run_activity_analyzer(project_path: str, knowledge: ProjectKnowledge) -> None:
        """Run the activity signal analyzer (7th step).  Never raises."""
        from analyzers.activity_analyzer import analyze_activity
        # Plots are saved alongside the project for now;
        # the CLI/writer will copy them to output_dir when generating docs.
        report = analyze_activity(project_path, output_dir=None)
        knowledge.activity = report
