"""Finds and reads existing documentation files in a project.

Scans a project directory for well-known documentation files (README,
CONTRIBUTING, CHANGELOG, LICENSE, etc.) and any Markdown/RST files inside
``docs/`` or ``documentation/`` directories.  Each discovered file is
returned as an :class:`~analyzers.models.ExistingDoc` instance with its
content truncated to a manageable size for downstream AI consumption.
"""

from __future__ import annotations

import logging
from pathlib import Path

from analyzers.models import ExistingDoc

logger = logging.getLogger(__name__)

# Maximum characters kept per file (keeps AI context manageable).
_MAX_CONTENT_CHARS: int = 5_000

# License files only need the first N chars to identify the license type.
_LICENSE_PREVIEW_CHARS: int = 200

# How deep to recurse into docs directories.
_DOCS_MAX_DEPTH: int = 3

# ── File-name patterns grouped by doc type ──────────────────────────────
# All matching is done case-insensitively.

_README_NAMES: list[str] = [
    "readme.md",
    "readme.rst",
    "readme.txt",
    "readme",
]

_CONTRIBUTING_NAMES: list[str] = [
    "contributing.md",
    "contributing.rst",
    "contributing.txt",
]

_CHANGELOG_NAMES: list[str] = [
    "changelog.md",
    "changelog.rst",
    "changes.md",
    "history.md",
    "release_notes.md",
]

_LICENSE_NAMES: list[str] = [
    "license",
    "license.md",
    "license.txt",
    "licence",
    "copying",
]

_OTHER_DOC_NAMES: list[str] = [
    "security.md",
    "code_of_conduct.md",
    "architecture.md",
    "design.md",
    "todo.md",
]

_DOCS_DIR_NAMES: list[str] = [
    "docs",
    "documentation",
]

_DOCS_EXTENSIONS: set[str] = {".md", ".rst"}


# ── Helpers ─────────────────────────────────────────────────────────────


def _read_file(path: Path, max_chars: int = _MAX_CONTENT_CHARS) -> str:
    """Read a text file with UTF-8 and a latin-1 fallback.

    Args:
        path: Absolute path to the file.
        max_chars: Maximum number of characters to return.

    Returns:
        The (possibly truncated) file content, or an empty string on
        read errors.
    """
    for encoding in ("utf-8", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            return text[:max_chars]
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            logger.warning("Could not read %s: %s", path, exc)
            return ""
    return ""


def _find_files_case_insensitive(
    directory: Path,
    target_names: list[str],
) -> list[Path]:
    """Return paths in *directory* whose lower-cased name matches any target.

    Only immediate children of *directory* are checked (no recursion).

    Args:
        directory: The directory to scan.
        target_names: Lower-cased file names to look for.

    Returns:
        A list of matching :class:`~pathlib.Path` objects.
    """
    matches: list[Path] = []
    target_set = set(target_names)
    try:
        for child in directory.iterdir():
            if child.is_file() and child.name.lower() in target_set:
                matches.append(child)
    except OSError as exc:
        logger.warning("Could not scan directory %s: %s", directory, exc)
    return matches


def _collect_docs_directory(
    docs_dir: Path,
    project_root: Path,
) -> list[ExistingDoc]:
    """Recursively collect .md / .rst files from a documentation directory.

    Args:
        docs_dir: Path to the ``docs/`` or ``documentation/`` directory.
        project_root: Project root used to compute relative paths.

    Returns:
        A list of :class:`ExistingDoc` instances found under *docs_dir*.
    """
    results: list[ExistingDoc] = []
    try:
        for child in docs_dir.rglob("*"):
            # Enforce max depth relative to docs_dir.
            try:
                relative_to_docs = child.relative_to(docs_dir)
            except ValueError:
                continue
            if len(relative_to_docs.parts) > _DOCS_MAX_DEPTH:
                continue

            if not child.is_file():
                continue
            if child.suffix.lower() not in _DOCS_EXTENSIONS:
                continue

            content = _read_file(child)
            doc_type = "api" if "api" in child.stem.lower() else "other"
            rel_path = str(child.relative_to(project_root))
            results.append(
                ExistingDoc(
                    file_path=rel_path,
                    doc_type=doc_type,
                    content=content,
                )
            )
    except OSError as exc:
        logger.warning("Error scanning docs directory %s: %s", docs_dir, exc)
    return results


# ── Public API ──────────────────────────────────────────────────────────


def read_existing_docs(project_path: str) -> list[ExistingDoc]:
    """Find and read existing documentation files in a project.

    Scans *project_path* for well-known documentation files and
    directories, reads their content (with sensible truncation), and
    returns a list of :class:`ExistingDoc` dataclasses.

    Recognised categories:

    * **README** – ``README.md``, ``README.rst``, ``README.txt``, ``README``
    * **Contributing** – ``CONTRIBUTING.md``, ``CONTRIBUTING.rst``,
      ``CONTRIBUTING.txt``
    * **Changelog** – ``CHANGELOG.md``, ``CHANGELOG.rst``, ``CHANGES.md``,
      ``HISTORY.md``, ``RELEASE_NOTES.md``
    * **License** – ``LICENSE``, ``LICENSE.md``, ``LICENSE.txt``, ``LICENCE``,
      ``COPYING`` (content limited to 200 chars)
    * **Docs directory** – All ``.md`` / ``.rst`` files under ``docs/`` or
      ``documentation/`` (recursive, max depth 3)
    * **Other** – ``SECURITY.md``, ``CODE_OF_CONDUCT.md``,
      ``ARCHITECTURE.md``, ``DESIGN.md``, ``TODO.md``

    Args:
        project_path: Absolute or relative path to the project root.

    Returns:
        A list of :class:`ExistingDoc` instances for every documentation
        file found.  Files that cannot be read are silently skipped.
    """
    root = Path(project_path).resolve()
    if not root.is_dir():
        logger.error("Project path does not exist or is not a directory: %s", root)
        return []

    docs: list[ExistingDoc] = []
    # Track already-seen relative paths to avoid duplicates when a file
    # matches multiple categories (unlikely but defensive).
    seen_paths: set[str] = set()

    def _add(path: Path, doc_type: str, max_chars: int = _MAX_CONTENT_CHARS) -> None:
        rel = str(path.relative_to(root))
        if rel in seen_paths:
            return
        seen_paths.add(rel)
        content = _read_file(path, max_chars=max_chars)
        docs.append(ExistingDoc(file_path=rel, doc_type=doc_type, content=content))

    # 1. README files
    for path in _find_files_case_insensitive(root, _README_NAMES):
        _add(path, doc_type="readme")

    # 2. Contributing guides
    for path in _find_files_case_insensitive(root, _CONTRIBUTING_NAMES):
        _add(path, doc_type="contributing")

    # 3. Changelogs
    for path in _find_files_case_insensitive(root, _CHANGELOG_NAMES):
        _add(path, doc_type="changelog")

    # 4. License files (only first 200 chars)
    for path in _find_files_case_insensitive(root, _LICENSE_NAMES):
        _add(path, doc_type="license", max_chars=_LICENSE_PREVIEW_CHARS)

    # 5. Docs directories
    for dir_name in _DOCS_DIR_NAMES:
        for child in root.iterdir():
            if child.is_dir() and child.name.lower() == dir_name:
                for existing_doc in _collect_docs_directory(child, root):
                    if existing_doc.file_path not in seen_paths:
                        seen_paths.add(existing_doc.file_path)
                        docs.append(existing_doc)

    # 6. Other common docs
    for path in _find_files_case_insensitive(root, _OTHER_DOC_NAMES):
        _add(path, doc_type="other")

    logger.info(
        "Found %d existing documentation file(s) in %s", len(docs), root
    )
    return docs
