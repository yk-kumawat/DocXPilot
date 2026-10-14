"""Prompt templates for DocXPilot document generation.

Each public function accepts a :class:`~analyzers.models.ProjectKnowledge`
object and returns a fully-formatted prompt string ready to be sent to Gemini.
"""

from __future__ import annotations

from analyzers.models import ProjectKnowledge, ActivityReport


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_language_summary(knowledge: ProjectKnowledge) -> str:
    lines = []
    for lang, summary in sorted(
        knowledge.language_summaries.items(),
        key=lambda x: x[1].file_count,
        reverse=True,
    ):
        lines.append(
            f"  - {lang}: {summary.file_count} files, "
            f"{summary.total_lines} lines "
            f"({summary.code_lines} code, {summary.comment_lines} comments)"
        )
    return "\n".join(lines) if lines else "  (no source files detected)"


def _format_dependencies(knowledge: ProjectKnowledge) -> str:
    deps = knowledge.dependency_report.dependencies
    if not deps:
        return "  (no dependencies detected)"
    managers: dict[str, list[str]] = {}
    for dep in deps:
        managers.setdefault(dep.manager, []).append(dep.name)
    lines = []
    for manager, names in managers.items():
        lines.append(f"  [{manager}]: {', '.join(names[:20])}" + (" …" if len(names) > 20 else ""))
    return "\n".join(lines)


def _format_git_summary(knowledge: ProjectKnowledge) -> str:
    g = knowledge.git_info
    if not g.is_git_repo:
        return "  Not a git repository."
    lines = [
        f"  Branch: {g.current_branch}",
        f"  Total commits: {g.total_commits}",
        f"  Contributors: {', '.join(g.contributors[:10])}",
        f"  Activity: {g.first_commit_date[:10] if g.first_commit_date else 'unknown'} — "
        f"{g.last_commit_date[:10] if g.last_commit_date else 'unknown'}",
    ]
    if g.remote_url:
        lines.append(f"  Remote: {g.remote_url}")
    if g.recent_commits:
        lines.append("  Recent commits:")
        for c in g.recent_commits[:5]:
            lines.append(f"    - [{c.date[:10]}] {c.author}: {c.message}")
    return "\n".join(lines)


def _format_configs(knowledge: ProjectKnowledge) -> str:
    if not knowledge.configs:
        return "  (none detected)"
    lines = []
    for cfg in knowledge.configs:
        lines.append(f"  - {cfg.file_path} ({cfg.config_type}): {cfg.summary}")
    return "\n".join(lines)


def _format_existing_docs(knowledge: ProjectKnowledge) -> str:
    if not knowledge.existing_docs:
        return "  (none found)"
    return "\n".join(f"  - {d.file_path} ({d.doc_type})" for d in knowledge.existing_docs)


def _format_activity_findings(knowledge: ProjectKnowledge) -> str:
    """Format the ActivityReport for inclusion in Gemini prompts.

    IMPORTANT: Gemini is explicitly told not to invent numbers — it must
    use only the values provided here.
    """
    act = knowledge.activity
    if act is None or not act.available:
        reason = act.reason if act else "analyzer did not run"
        return f"  Activity analysis not available: {reason}"

    lines = [
        f"  Span: {act.span_days} days | Active days: {act.active_days} | "
        f"Total commits: {act.total_commits}",
        f"  Active day ratio: {act.active_day_ratio:.1%}",
        f"  Burstiness index: {act.burstiness:.3f} "
        "(positive = bursty/sprint-driven, negative = steady)",
    ]

    if act.dominant_period_days > 0:
        lines.append(
            f"  Dominant rhythm: {act.dominant_period_days:.1f} days "
            f"(strength {act.dominant_strength:.2f}, "
            f"autocorr cross-check: {act.autocorr_period_days:.1f} days"
            + (", MISMATCH — spectrum is noisy" if act.period_mismatch else ")")
        )

    lines.append(f"  Spectral entropy: {act.spectral_entropy:.3f} "
                 "(low = tonal/rhythmic, high = noisy/irregular)")

    bursts    = [a for a in act.anomalies if a.kind == "burst"]
    rhythmbs  = [a for a in act.anomalies if a.kind == "rhythm_break"]
    inactives = [a for a in act.anomalies if a.kind == "inactivity_gap"]

    if bursts:
        lines.append(f"  Burst windows ({len(bursts)}):")
        for a in bursts[:5]:
            lines.append(f"    - {a.start_date} to {a.end_date}: {a.description}")
    if rhythmbs:
        lines.append(f"  Rhythm breaks ({len(rhythmbs)}):")
        for a in rhythmbs[:5]:
            lines.append(f"    - {a.start_date} to {a.end_date}: {a.description}")
    if inactives:
        lines.append(f"  Inactivity gaps ({len(inactives)}):")
        for a in inactives[:5]:
            lines.append(f"    - {a.start_date} to {a.end_date}: {int(a.score)} days")
    if not act.anomalies:
        lines.append("  Anomalies: none detected")

    lines.append(
        f"  Model used: {'yes (1D Conv Autoencoder)' if act.model_used else 'no (DSP only)'}"
    )
    if act.plot_paths:
        lines.append("  Plots generated: activity.png, spectrum.png, spectrogram.png")

    lines.append("")
    lines.append("  NOTE TO GEMINI: Use ONLY the numbers above. Do not invent or estimate activity metrics.")
    return "\n".join(lines)


def _format_functions(knowledge: ProjectKnowledge, limit: int = 60) -> str:
    lines = []
    count = 0
    for fa in knowledge.file_analyses:
        for func in fa.functions:
            if count >= limit:
                lines.append("  ... (truncated for brevity)")
                return "\n".join(lines)
            params = ", ".join(func.parameters)
            ret = f" -> {func.return_type}" if func.return_type else ""
            doc = f"\n      Docstring: {func.docstring[:120]}" if func.docstring else ""
            lines.append(
                f"  - {fa.info.relative_path}:{func.line_number}  "
                f"`{func.name}({params}){ret}`{doc}"
            )
            count += 1
    return "\n".join(lines) if lines else "  (none detected)"


def _format_classes(knowledge: ProjectKnowledge, limit: int = 40) -> str:
    lines = []
    count = 0
    for fa in knowledge.file_analyses:
        for cls in fa.classes:
            if count >= limit:
                lines.append("  ... (truncated for brevity)")
                return "\n".join(lines)
            parents = f"({', '.join(cls.parent_classes)})" if cls.parent_classes else ""
            methods = ", ".join(cls.methods[:10])
            lines.append(
                f"  - {fa.info.relative_path}:{cls.line_number}  "
                f"`{cls.name}{parents}` — methods: {methods}"
            )
            count += 1
    return "\n".join(lines) if lines else "  (none detected)"


def _base_context(knowledge: ProjectKnowledge) -> str:
    """Return a shared project-context block used by all prompts."""
    return f"""
PROJECT ANALYSIS CONTEXT
========================
Project Name  : {knowledge.project_name}
Project Path  : {knowledge.project_path}
Layout        : {knowledge.project_layout}
Total Files   : {knowledge.total_files}
Total Lines   : {knowledge.total_lines:,}

DIRECTORY STRUCTURE
-------------------
{knowledge.directory_tree}

LANGUAGES DETECTED
------------------
{_format_language_summary(knowledge)}

DEPENDENCIES
------------
{_format_dependencies(knowledge)}

GIT HISTORY
-----------
{_format_git_summary(knowledge)}

CONFIGURATION FILES
-------------------
{_format_configs(knowledge)}

ENVIRONMENT VARIABLES
---------------------
{', '.join(knowledge.env_variables) if knowledge.env_variables else '(none detected)'}

DEPLOYMENT TARGETS
------------------
{', '.join(knowledge.deployment_targets) if knowledge.deployment_targets else '(none detected)'}

EXISTING DOCUMENTATION
----------------------
{_format_existing_docs(knowledge)}

PROJECT ACTIVITY & HEALTH (from signal analysis)
-------------------------------------------------
{_format_activity_findings(knowledge)}
""".strip()


# ---------------------------------------------------------------------------
# Public prompt builders — one per document type
# ---------------------------------------------------------------------------

DOC_TYPES = [
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


def build_readme_prompt(knowledge: ProjectKnowledge) -> str:
    return f"""You are a technical documentation expert. Generate a professional, complete README.md for the project described below.

{_base_context(knowledge)}

REQUIREMENTS FOR THE README:
- Start with a compelling project title and one-line description
- Add relevant badges (build status, license, Python version, etc.) — use placeholder URLs if unknown
- Write a clear "What is this?" section explaining the project purpose
- List key features as bullet points
- Provide Prerequisites section
- Provide a detailed Installation section with code blocks
- Provide a Usage section with real examples from the codebase
- Add a Contributing section
- Add a License section
- Use emojis sparingly for visual appeal
- Format all code blocks with the correct language tag
- If activity analysis data is available above, add a "Project Activity & Health" section
  using ONLY the numbers provided — do not invent or estimate any metric.

Output ONLY the Markdown content for README.md, nothing else."""


def build_project_report_prompt(knowledge: ProjectKnowledge) -> str:
    lang_detail = _format_language_summary(knowledge)
    return f"""You are a senior software engineering consultant. Generate a comprehensive Project Report for the project described below.

{_base_context(knowledge)}

LANGUAGES (detailed):
{lang_detail}

REQUIREMENTS FOR THE PROJECT REPORT:
- Executive Summary (2-3 paragraphs)
- Project Overview & Purpose
- Technology Stack with justification for each choice
- Codebase Statistics table (files, LOC, languages, etc.)
- Module / Package Descriptions — explain what each top-level folder does
- Key Features & Capabilities
- Architecture Overview (high-level description)
- Dependencies Analysis
- Git Activity & Contributors
- Project Activity & Health (MANDATORY section): write this section using ONLY the
  metrics from the "PROJECT ACTIVITY & HEALTH" block above. Include dominant rhythm,
  burstiness, anomalies, and spectral character. Do NOT invent numbers.
- Project Health Assessment
- Conclusion & Recommendations

Output ONLY the Markdown content for PROJECT_REPORT.md, nothing else."""


def build_installation_guide_prompt(knowledge: ProjectKnowledge) -> str:
    readme_content = ""
    for doc in knowledge.existing_docs:
        if doc.doc_type == "readme":
            readme_content = doc.content[:2000]
            break

    return f"""You are a DevOps and developer-experience expert. Generate a detailed Installation Guide for the project described below.

{_base_context(knowledge)}

EXISTING README CONTENT (for reference):
{readme_content or '(none)'}

REQUIREMENTS FOR THE INSTALLATION GUIDE:
- Prerequisites section: OS, runtime versions, tools needed
- Step-by-step installation instructions with numbered steps
- Code blocks for every command
- Environment setup: describe all environment variables from the project
- Configuration after install
- Verifying the installation works
- Troubleshooting: at least 5 common issues and their fixes
- Uninstallation instructions

Output ONLY the Markdown content for INSTALLATION_GUIDE.md, nothing else."""


def build_architecture_doc_prompt(knowledge: ProjectKnowledge) -> str:
    classes = _format_classes(knowledge)
    return f"""You are a software architect. Generate a Software Architecture Document (SAD) for the project described below.

{_base_context(knowledge)}

CLASSES DETECTED:
{classes}

REQUIREMENTS FOR THE ARCHITECTURE DOCUMENT:
- Introduction & Scope
- Architectural Goals & Constraints
- System Context Diagram (described in text/ASCII)
- High-Level Architecture Overview
- Component / Module Breakdown — one section per top-level directory
- Data Flow description
- Design Patterns identified in the codebase
- Technology & Framework Decisions
- Deployment Architecture
- Security Considerations
- Scalability & Performance Notes
- Appendix: Directory Structure

Output ONLY the Markdown content for SOFTWARE_ARCHITECTURE.md, nothing else."""


def build_api_docs_prompt(knowledge: ProjectKnowledge) -> str:
    functions = _format_functions(knowledge)
    classes = _format_classes(knowledge)

    return f"""You are a technical writer specializing in API documentation. Generate complete API Documentation for the project described below.

{_base_context(knowledge)}

FUNCTIONS DETECTED:
{functions}

CLASSES DETECTED:
{classes}

REQUIREMENTS FOR THE API DOCUMENTATION:
- Overview of the public API surface
- For each module/file with exported functions or classes:
  - Module description
  - Each function: signature, parameters table, return value, description, example
  - Each class: description, constructor, attributes table, methods
- Code examples for the most important APIs
- Error handling and exceptions
- Index of all public symbols at the end

Output ONLY the Markdown content for API_DOCUMENTATION.md, nothing else."""


def build_onboarding_guide_prompt(knowledge: ProjectKnowledge) -> str:
    contributing_content = ""
    for doc in knowledge.existing_docs:
        if doc.doc_type == "contributing":
            contributing_content = doc.content[:2000]
            break

    return f"""You are an engineering manager and developer advocate. Generate a Developer Onboarding Guide for the project described below.

{_base_context(knowledge)}

EXISTING CONTRIBUTING GUIDE (if any):
{contributing_content or '(none)'}

REQUIREMENTS FOR THE DEVELOPER ONBOARDING GUIDE:
- Welcome message
- Quick Start: get the project running in under 10 minutes
- Repository Tour: explain each top-level folder and its purpose
- Development Environment Setup (editor plugins, linter config, etc.)
- Code Conventions & Style Guide (based on what's detected in the project)
- Key Files & Entry Points explained
- Making your first contribution: step-by-step
- Running Tests
- Git workflow (branching, PR process)
- Who to ask for help (contributors)
- Glossary of project-specific terms

Output ONLY the Markdown content for DEVELOPER_ONBOARDING.md, nothing else."""


def build_deployment_guide_prompt(knowledge: ProjectKnowledge) -> str:
    return f"""You are a DevOps engineer and deployment specialist. Generate a comprehensive Deployment Guide for the project described below.

{_base_context(knowledge)}

REQUIREMENTS FOR THE DEPLOYMENT GUIDE:
- Introduction & Deployment Options overview
- Prerequisites & Server Requirements
- Environment Variables reference table (all detected env vars with description placeholders)
- Standard Deployment (manual/direct)
- Docker Deployment (if Docker detected; otherwise a template)
- CI/CD Pipeline explanation (based on detected CI configs)
- Database Setup & Migrations (if applicable)
- Reverse Proxy / Load Balancer configuration example
- SSL/TLS Setup
- Health Checks & Monitoring
- Rollback Procedure
- Troubleshooting Deployment Issues

Output ONLY the Markdown content for DEPLOYMENT_GUIDE.md, nothing else."""


def build_code_quality_report_prompt(knowledge: ProjectKnowledge) -> str:
    # Compute some basic stats
    total_functions = sum(len(fa.functions) for fa in knowledge.file_analyses)
    total_classes = sum(len(fa.classes) for fa in knowledge.file_analyses)
    total_comments = sum(fa.metrics.comment_lines for fa in knowledge.file_analyses)
    total_code = sum(fa.metrics.code_lines for fa in knowledge.file_analyses)
    comment_ratio = (total_comments / total_code * 100) if total_code > 0 else 0

    # Find largest files
    large_files = sorted(
        knowledge.file_analyses,
        key=lambda fa: fa.metrics.total_lines,
        reverse=True,
    )[:10]
    large_files_str = "\n".join(
        f"  - {fa.info.relative_path}: {fa.metrics.total_lines} lines"
        for fa in large_files
    )

    return f"""You are a senior code reviewer and quality engineer. Generate a Code Quality Report for the project described below.

{_base_context(knowledge)}

COMPUTED METRICS:
  Total functions  : {total_functions}
  Total classes    : {total_classes}
  Comment ratio    : {comment_ratio:.1f}%
  Code lines       : {total_code:,}
  Comment lines    : {total_comments:,}

LARGEST FILES (potential hotspots):
{large_files_str or '  (none)'}

REQUIREMENTS FOR THE CODE QUALITY REPORT:
- Executive Summary with overall quality score (1-10) and brief rationale
- Metrics Dashboard table
- Language-by-language breakdown
- Code Complexity Analysis (identify hotspots from the largest files)
- Documentation Coverage Assessment (docstring coverage, comment ratio)
- Dependency Health (outdated, dev vs runtime, potential risks)
- Code Smells & Anti-patterns identified (be specific about filenames)
- Security Observations
- Maintainability Score & Rationale
- Top 10 Actionable Improvement Suggestions (prioritized)
- Conclusion

Output ONLY the Markdown content for CODE_QUALITY_REPORT.md, nothing else."""


def build_changelog_prompt(knowledge: ProjectKnowledge) -> str:
    g = knowledge.git_info
    commits_str = ""
    if g.recent_commits:
        commits_str = "\n".join(
            f"  [{c.date[:10]}] {c.author}: {c.message}"
            for c in g.recent_commits
        )
    else:
        commits_str = "  (no git history available)"

    existing_changelog = ""
    for doc in knowledge.existing_docs:
        if doc.doc_type == "changelog":
            existing_changelog = doc.content[:3000]
            break

    return f"""You are a release manager. Generate a CHANGELOG for the project described below, following the Keep a Changelog format (https://keepachangelog.com).

{_base_context(knowledge)}

GIT COMMIT HISTORY:
{commits_str}

EXISTING CHANGELOG (if any):
{existing_changelog or '(none)'}

REQUIREMENTS FOR THE CHANGELOG:
- Follow https://keepachangelog.com/en/1.0.0/ format
- Group commits by approximate date/version
- Categorize each change as: Added, Changed, Deprecated, Removed, Fixed, Security
- Infer version numbers from commit messages or dates if no tags exist
- Include an [Unreleased] section at the top
- Keep entries concise but informative
- If no git history: create a template CHANGELOG with placeholder entries

Output ONLY the Markdown content for CHANGELOG.md, nothing else."""


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

PROMPT_BUILDERS: dict[str, callable] = {
    "README": build_readme_prompt,
    "Project Report": build_project_report_prompt,
    "Installation Guide": build_installation_guide_prompt,
    "Software Architecture Document": build_architecture_doc_prompt,
    "API Documentation": build_api_docs_prompt,
    "Developer Onboarding Guide": build_onboarding_guide_prompt,
    "Deployment Guide": build_deployment_guide_prompt,
    "Code Quality Report": build_code_quality_report_prompt,
    "CHANGELOG": build_changelog_prompt,
}
