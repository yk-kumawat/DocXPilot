"""Directory analyzer for DocXPilot.

Provides utilities for analyzing project directory structures, including building
visual tree representations, counting file types, detecting project layouts,
and discovering source files.
"""

import fnmatch
from pathlib import Path

IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", "venv", ".venv", "env", ".env",
    "dist", "build", ".idea", ".vscode", ".vs", "bin", "obj", ".tox",
    ".mypy_cache", ".pytest_cache", "target", ".next", ".nuxt", "vendor",
    "bower_components", ".gradle", ".dart_tool", ".pub-cache", "coverage",
    "htmlcov", ".eggs", "*.egg-info"
}

IGNORED_FILES = {
    ".DS_Store", "Thumbs.db", "*.pyc", "*.pyo", "*.class", "*.o", "*.so",
    "*.dll", "*.exe"
}


def _is_ignored(path: Path) -> bool:
    """Check if a path should be ignored based on IGNORED_DIRS and IGNORED_FILES.
    
    Args:
        path: Path to check.
        
    Returns:
        True if the path should be ignored, False otherwise.
    """
    if path.is_dir():
        for pattern in IGNORED_DIRS:
            if fnmatch.fnmatch(path.name, pattern):
                return True
    else:
        for pattern in IGNORED_FILES:
            if fnmatch.fnmatch(path.name, pattern):
                return True
    return False


def build_directory_tree(root_path: str, max_depth: int = 4) -> str:
    """Build a visual tree string of the directory structure.

    Args:
        root_path: The root directory path to start from.
        max_depth: Maximum depth to traverse. Defaults to 4.

    Returns:
        A visual tree string representation.
    """
    root = Path(root_path)
    if not root.is_dir():
        return f"{root.name} [Error: Not a directory]"

    tree_str = [f"{root.name}/"]

    def _walk(current_path: Path, current_depth: int, prefix: str = "") -> None:
        if current_depth > max_depth:
            return

        try:
            entries = list(current_path.iterdir())
        except PermissionError:
            tree_str.append(f"{prefix}└── [Permission Denied]")
            return
        
        # Filter and sort entries: directories first, then files
        filtered_entries = []
        for entry in entries:
            if not _is_ignored(entry):
                filtered_entries.append(entry)
                
        # Sort directories first, then by name
        filtered_entries.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

        count = len(filtered_entries)
        for i, entry in enumerate(filtered_entries):
            is_last = i == (count - 1)
            connector = "└── " if is_last else "├── "
            
            if entry.is_dir():
                tree_str.append(f"{prefix}{connector}{entry.name}/")
                extension_prefix = "    " if is_last else "│   "
                _walk(entry, current_depth + 1, prefix + extension_prefix)
            else:
                tree_str.append(f"{prefix}{connector}{entry.name}")

    _walk(root, 1)
    return "\n".join(tree_str)


def count_file_types(root_path: str) -> dict[str, int]:
    """Walk the tree and count files by extension.

    Args:
        root_path: The root directory path to analyze.

    Returns:
        A dictionary mapping file extensions to their count.
    """
    root = Path(root_path)
    counts: dict[str, int] = {}

    if not root.is_dir():
        return counts

    def _walk(current_path: Path) -> None:
        try:
            entries = list(current_path.iterdir())
        except PermissionError:
            return

        for entry in entries:
            if _is_ignored(entry):
                continue
                
            if entry.is_dir():
                _walk(entry)
            else:
                ext = entry.suffix.lower()
                if ext:
                    counts[ext] = counts.get(ext, 0) + 1

    _walk(root)
    return counts


def detect_project_layout(root_path: str) -> str:
    """Detect the project structure pattern.

    Args:
        root_path: The root directory path to analyze.

    Returns:
        The detected project layout ('src', 'monorepo', 'flat', or 'standard').
    """
    root = Path(root_path)
    if not root.is_dir():
        return "standard"

    try:
        entries = list(root.iterdir())
    except PermissionError:
        return "standard"
        
    dirs = [entry for entry in entries if entry.is_dir() and not _is_ignored(entry)]
    dir_names = {d.name.lower() for d in dirs}
    
    # Check for monorepo
    if "packages" in dir_names or "apps" in dir_names:
        return "monorepo"
        
    # Check for src layout
    if "src" in dir_names:
        return "src"
        
    # Check for flat layout (source files in root)
    files = [entry for entry in entries if entry.is_file() and not _is_ignored(entry)]
    # Set of common source file extensions
    source_extensions = {".py", ".js", ".ts", ".java", ".cpp", ".c", ".cs", ".go", ".rs", ".rb"}
    has_source_files = any(f.suffix.lower() in source_extensions for f in files)
    
    if has_source_files:
        return "flat"
        
    return "standard"


def get_all_source_files(root_path: str) -> list[str]:
    """Get a list of all source file absolute paths.
    
    Excludes ignored directories and files.

    Args:
        root_path: The root directory path to search.

    Returns:
        A list of absolute file paths as strings.
    """
    root = Path(root_path)
    source_files: list[str] = []

    if not root.is_dir():
        return source_files

    def _walk(current_path: Path) -> None:
        try:
            entries = list(current_path.iterdir())
        except PermissionError:
            return

        for entry in entries:
            if _is_ignored(entry):
                continue
                
            if entry.is_dir():
                _walk(entry)
            else:
                source_files.append(str(entry.absolute()))

    _walk(root)
    return source_files
