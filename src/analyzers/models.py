"""Data models for DocXPilot analyzers."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FileInfo:
    """Basic information about a source file."""

    path: str
    relative_path: str
    language: str
    size_bytes: int
    extension: str


@dataclass
class FunctionInfo:
    """Information about a function/method found in code."""

    name: str
    line_number: int
    parameters: list[str] = field(default_factory=list)
    return_type: str = ""
    docstring: str = ""
    is_method: bool = False


@dataclass
class ClassInfo:
    """Information about a class found in code."""

    name: str
    line_number: int
    methods: list[str] = field(default_factory=list)
    parent_classes: list[str] = field(default_factory=list)
    docstring: str = ""


@dataclass
class CodeMetrics:
    """Line-count metrics for a single file."""

    file_path: str
    language: str
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0


@dataclass
class FileAnalysis:
    """Complete analysis of a single source file."""

    info: FileInfo
    metrics: CodeMetrics
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


@dataclass
class LanguageSummary:
    """Aggregated metrics for a single language."""

    language: str
    file_count: int = 0
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0


@dataclass
class GitCommit:
    """A single git commit."""

    hash: str
    author: str
    date: str
    message: str


@dataclass
class GitInfo:
    """Git repository analysis results."""

    is_git_repo: bool = False
    total_commits: int = 0
    contributors: list[str] = field(default_factory=list)
    recent_commits: list[GitCommit] = field(default_factory=list)
    current_branch: str = ""
    remote_url: str = ""
    first_commit_date: str = ""
    last_commit_date: str = ""
    most_changed_files: list[str] = field(default_factory=list)


@dataclass
class DependencyInfo:
    """A detected dependency."""

    name: str
    version: str = ""
    manager: str = ""  # pip, npm, maven, etc.
    is_dev: bool = False


@dataclass
class DependencyReport:
    """All dependencies found in the project."""

    managers_found: list[str] = field(default_factory=list)
    dependencies: list[DependencyInfo] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)


@dataclass
class ConfigInfo:
    """A detected configuration file."""

    file_path: str
    config_type: str  # "docker", "ci_cd", "env", "build", "lint", etc.
    summary: str = ""
    content_preview: str = ""


@dataclass
class ExistingDoc:
    """An existing documentation file found in the project."""

    file_path: str
    doc_type: str  # "readme", "contributing", "changelog", "license", "api", "other"
    content: str = ""


@dataclass
class ProjectKnowledge:
    """
    Aggregated knowledge from all analyzers.
    This is the single object sent to Gemini for document generation.
    """

    # Project basics
    project_path: str = ""
    project_name: str = ""

    # From Code Analyzer
    file_analyses: list[FileAnalysis] = field(default_factory=list)
    language_summaries: dict[str, LanguageSummary] = field(default_factory=dict)
    total_files: int = 0
    total_lines: int = 0

    # From Directory Analyzer
    directory_tree: str = ""
    file_type_counts: dict[str, int] = field(default_factory=dict)
    project_layout: str = ""  # "src", "flat", "monorepo", etc.

    # From Git Analyzer
    git_info: GitInfo = field(default_factory=GitInfo)

    # From Dependency Analyzer
    dependency_report: DependencyReport = field(default_factory=DependencyReport)

    # From Config Analyzer
    configs: list[ConfigInfo] = field(default_factory=list)
    env_variables: list[str] = field(default_factory=list)
    deployment_targets: list[str] = field(default_factory=list)

    # From Docs Reader
    existing_docs: list[ExistingDoc] = field(default_factory=list)

    # From Activity Analyzer (optional — present only when git history is available)
    activity: Optional["ActivityReport"] = field(default=None)


# ---------------------------------------------------------------------------
# Activity Signal Analyzer data models
# ---------------------------------------------------------------------------

@dataclass
class ActivityAnomaly:
    """A detected anomaly in the project's activity signal."""

    start_date: str          # ISO date string, e.g. '2024-01-15'
    end_date: str            # ISO date string
    kind: str                # 'burst' | 'rhythm_break' | 'inactivity_gap'
    score: float             # reconstruction error ratio, or gap length in days
    description: str = ''


@dataclass
class ActivityReport:
    """Full report produced by the Activity Signal Analyzer."""

    available: bool = False
    reason: str = ''               # why unavailable if available=False
    span_days: int = 0
    active_days: int = 0
    total_commits: int = 0
    dominant_period_days: float = 0.0
    dominant_strength: float = 0.0
    autocorr_period_days: float = 0.0
    period_mismatch: bool = False  # True if FFT vs autocorr differ > 20%
    spectral_entropy: float = 0.0
    spectral_flatness: float = 0.0
    burstiness: float = 0.0
    active_day_ratio: float = 0.0
    anomalies: list[ActivityAnomaly] = field(default_factory=list)
    model_used: bool = False       # False if torch or weights missing
    plot_paths: list[str] = field(default_factory=list)
    summary_lines: list[str] = field(default_factory=list)
