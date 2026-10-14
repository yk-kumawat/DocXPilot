"""Module to analyze source code files, extract functions, classes, imports, and compute metrics."""

import ast
import os
import re
from pathlib import Path
from typing import Optional

from analyzers.models import (
    FileInfo,
    FunctionInfo,
    ClassInfo,
    CodeMetrics,
    FileAnalysis
)

LANGUAGE_EXTENSIONS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JSX",
    ".tsx": "TSX",
    ".java": "Java",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cc": "C++",
    ".cs": "C#",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".dart": "Dart",
    ".scala": "Scala",
    ".r": "R",
    ".lua": "Lua",
    ".pl": "Perl",
    ".pm": "Perl",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".psm1": "PowerShell",
    ".hs": "Haskell",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hrl": "Erlang",
    ".clj": "Clojure",
    ".cljs": "Clojure",
    ".cljc": "Clojure",
    ".fs": "F#",
    ".fsi": "F#",
    ".fsx": "F#",
    ".ml": "OCaml",
    ".mli": "OCaml",
    ".jl": "Julia",
    ".zig": "Zig",
    ".nim": "Nim",
    ".v": "V",
    ".m": "Objective-C",
    ".mm": "Objective-C",
    ".mat": "MATLAB",
    ".groovy": "Groovy",
    ".asm": "Assembly",
    ".s": "Assembly",
    ".cbl": "COBOL",
    ".cob": "COBOL",
    ".f": "Fortran",
    ".f90": "Fortran",
    ".f95": "Fortran",
    ".sql": "SQL",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "SASS",
    ".less": "Less",
    ".xml": "XML",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".ini": "INI",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".tex": "LaTeX",
    ".dockerfile": "Dockerfile",
    "dockerfile": "Dockerfile",
    ".mk": "Makefile",
    "makefile": "Makefile",
    "cmakelists.txt": "CMake",
    ".cmake": "CMake",
    ".tf": "Terraform",
    ".tfvars": "Terraform",
    ".proto": "Protobuf",
    ".graphql": "GraphQL",
    ".gql": "GraphQL"
}

COMMENT_STYLES = {
    "Python": ("#", '"""', '"""'),
    "JavaScript": ("//", "/*", "*/"),
    "TypeScript": ("//", "/*", "*/"),
    "JSX": ("//", "/*", "*/"),
    "TSX": ("//", "/*", "*/"),
    "Java": ("//", "/*", "*/"),
    "C": ("//", "/*", "*/"),
    "C++": ("//", "/*", "*/"),
    "C#": ("//", "/*", "*/"),
    "Go": ("//", "/*", "*/"),
    "Rust": ("//", "/*", "*/"),
    "Ruby": ("#", "=begin", "=end"),
    "PHP": ("//", "/*", "*/"),
    "Swift": ("//", "/*", "*/"),
    "Kotlin": ("//", "/*", "*/"),
    "Dart": ("//", "/*", "*/"),
    "Scala": ("//", "/*", "*/"),
    "R": ("#", None, None),
    "Lua": ("--", "--[[", "]]"),
    "Perl": ("#", "=pod", "=cut"),
    "Shell": ("#", None, None),
    "PowerShell": ("#", "<#", "#>"),
    "Haskell": ("--", "{-", "-}"),
    "Elixir": ("#", None, None),
    "Erlang": ("%", None, None),
    "Clojure": (";;", None, None),
    "F#": ("//", "(*", "*)"),
    "OCaml": (None, "(*", "*)"),
    "Julia": ("#", "#=", "=#"),
    "Zig": ("//", None, None),
    "Nim": ("#", "#[", "]#"),
    "V": ("//", "/*", "*/"),
    "Objective-C": ("//", "/*", "*/"),
    "MATLAB": ("%", "%{", "%}"),
    "Groovy": ("//", "/*", "*/"),
    "Assembly": (";", None, None),
    "COBOL": ("*", None, None),
    "Fortran": ("!", None, None),
    "SQL": ("--", "/*", "*/"),
    "HTML": (None, "<!--", "-->"),
    "CSS": (None, "/*", "*/"),
    "SCSS": ("//", "/*", "*/"),
    "SASS": ("//", "/*", "*/"),
    "Less": ("//", "/*", "*/"),
    "XML": (None, "<!--", "-->"),
    "JSON": (None, None, None),
    "YAML": ("#", None, None),
    "TOML": ("#", None, None),
    "INI": (";", None, None),
    "Markdown": (None, "<!--", "-->"),
    "LaTeX": ("%", None, None),
    "Dockerfile": ("#", None, None),
    "Makefile": ("#", None, None),
    "CMake": ("#", "#[[", "]]"),
    "Terraform": ("#", "/*", "*/"),
    "Protobuf": ("//", "/*", "*/"),
    "GraphQL": ("#", '"""', '"""')
}

FUNCTION_PATTERNS = {
    "JavaScript": re.compile(r"^\s*(?:async\s+)?function\s+(\w+)\s*\("),
    "TypeScript": re.compile(r"^\s*(?:async\s+)?function\s+(\w+)\s*\("),
    "Java": re.compile(r"^\s*(?:public|protected|private|static|\s)+[\w<>\[\]]+\s+(\w+)\s*\("),
    "C++": re.compile(r"^\s*(?:[\w<>:]+\s+)?(\w+)\s*\([^)]*\)\s*(?:const\s*)?(?:\{|$)"),
    "C#": re.compile(r"^\s*(?:public|protected|private|internal|static|virtual|override|\s)+[\w<>\[\]]+\s+(\w+)\s*\("),
    "Go": re.compile(r"^\s*func\s+(?:\([^)]+\)\s+)?(\w+)\s*\("),
    "Rust": re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]+>)?\s*\("),
    "Ruby": re.compile(r"^\s*def\s+([\w!?=]+)"),
    "PHP": re.compile(r"^\s*(?:public|protected|private|static|\s)*function\s+(\w+)\s*\("),
    "Swift": re.compile(r"^\s*(?:(?:public|private|internal|fileprivate|open|static|class|mutating|nonmutating|override)\s+)*func\s+(\w+)\s*(?:<[^>]+>)?\s*\("),
    "Kotlin": re.compile(r"^\s*(?:(?:public|private|protected|internal|abstract|final|open|override|operator|inline|infix|suspend)\s+)*fun\s+(?:<[^>]+>\s+)?(?:\w+\.)?(\w+)\s*\(")
}

CLASS_PATTERNS = {
    "JavaScript": re.compile(r"^\s*class\s+(\w+)"),
    "TypeScript": re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"),
    "Java": re.compile(r"^\s*(?:public|protected|private|static|abstract|final|\s)*class\s+(\w+)"),
    "C++": re.compile(r"^\s*(?:class|struct)\s+(\w+)"),
    "C#": re.compile(r"^\s*(?:public|protected|private|internal|static|abstract|sealed|\s)*class\s+(\w+)"),
    "Go": re.compile(r"^\s*type\s+(\w+)\s+struct"),
    "Rust": re.compile(r"^\s*(?:pub\s+)?struct\s+(\w+)"),
    "Ruby": re.compile(r"^\s*class\s+(\w+)"),
    "PHP": re.compile(r"^\s*(?:abstract\s+|final\s+)?class\s+(\w+)"),
    "Swift": re.compile(r"^\s*(?:(?:public|private|internal|fileprivate|open|final)\s+)*class\s+(\w+)"),
    "Kotlin": re.compile(r"^\s*(?:(?:public|private|protected|internal|abstract|final|open|sealed|data|inner)\s+)*class\s+(\w+)")
}

IMPORT_PATTERNS = {
    "JavaScript": re.compile(r"^\s*(?:import|require)\s+.*"),
    "TypeScript": re.compile(r"^\s*(?:import|require)\s+.*"),
    "Java": re.compile(r"^\s*import\s+[\w.]+;"),
    "C++": re.compile(r"^\s*#include\s*[<\"][\w./\\]+[>\"]"),
    "C#": re.compile(r"^\s*using\s+[\w.]+;"),
    "Go": re.compile(r"^\s*import\s+(?:\(|(?:\"[^\"]+\"))"),
    "Rust": re.compile(r"^\s*use\s+[\w:]+;"),
    "Ruby": re.compile(r"^\s*(?:require|require_relative|load)\s+['\"].*['\"]"),
    "PHP": re.compile(r"^\s*(?:use|require|require_once|include|include_once)\s+.*"),
    "Swift": re.compile(r"^\s*import\s+\w+"),
    "Kotlin": re.compile(r"^\s*import\s+[\w.]+")
}


def detect_language(filepath: str) -> str:
    """Detect the programming language based on file extension or filename."""
    path = Path(filepath)
    ext = path.suffix.lower()
    name = path.name.lower()
    
    if ext in LANGUAGE_EXTENSIONS:
        return LANGUAGE_EXTENSIONS[ext]
    if name in LANGUAGE_EXTENSIONS:
        return LANGUAGE_EXTENSIONS[name]
    
    return "Unknown"


def is_binary_file(filepath: str) -> bool:
    """Check if a file is likely a binary file."""
    try:
        with open(filepath, "tr", encoding="utf-8") as f:
            f.read(1024)
            return False
    except UnicodeDecodeError:
        return True
    except Exception:
        return True


def compute_metrics(filepath: str, language: str) -> CodeMetrics:
    """Compute line count metrics for a file."""
    metrics = CodeMetrics(file_path=filepath, language=language)
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        metrics.total_lines = len(lines)
        
        styles = COMMENT_STYLES.get(language, (None, None, None))
        line_comment = styles[0]
        block_start = styles[1]
        block_end = styles[2]
        
        in_block = False
        
        for line in lines:
            s_line = line.strip()
            
            if not s_line:
                metrics.blank_lines += 1
                continue
                
            is_comment = False
            
            # Handle block comments
            if block_start and block_end:
                if in_block:
                    is_comment = True
                    if block_end in s_line:
                        in_block = False
                else:
                    if s_line.startswith(block_start):
                        is_comment = True
                        if block_end not in s_line[len(block_start):]:
                            in_block = True
            
            if not is_comment and line_comment and s_line.startswith(line_comment):
                is_comment = True
                
            if is_comment:
                metrics.comment_lines += 1
            else:
                metrics.code_lines += 1
                
    except Exception:
        pass
        
    return metrics


def extract_functions(content: str, language: str) -> list[FunctionInfo]:
    """Extract functions from code content."""
    functions = []
    if language == "Python":
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_info = FunctionInfo(
                        name=node.name,
                        line_number=node.lineno,
                        parameters=[arg.arg for arg in node.args.args],
                        docstring=ast.get_docstring(node) or "",
                        is_method=False  # Basic approximation
                    )
                    
                    if node.returns:
                        if isinstance(node.returns, ast.Name):
                            func_info.return_type = node.returns.id
                        elif isinstance(node.returns, ast.Constant):
                            func_info.return_type = str(node.returns.value)
                            
                    functions.append(func_info)
        except Exception:
            pass
    else:
        pattern = FUNCTION_PATTERNS.get(language)
        if pattern:
            lines = content.splitlines()
            for i, line in enumerate(lines):
                match = pattern.search(line)
                if match:
                    functions.append(FunctionInfo(
                        name=match.group(1),
                        line_number=i + 1
                    ))
                    
    return functions


def extract_classes(content: str, language: str) -> list[ClassInfo]:
    """Extract classes from code content."""
    classes = []
    if language == "Python":
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    methods = []
                    for child in node.body:
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            methods.append(child.name)
                            
                    class_info = ClassInfo(
                        name=node.name,
                        line_number=node.lineno,
                        methods=methods,
                        parent_classes=[base.id for base in node.bases if isinstance(base, ast.Name)],
                        docstring=ast.get_docstring(node) or ""
                    )
                    classes.append(class_info)
        except Exception:
            pass
    else:
        pattern = CLASS_PATTERNS.get(language)
        if pattern:
            lines = content.splitlines()
            for i, line in enumerate(lines):
                match = pattern.search(line)
                if match:
                    classes.append(ClassInfo(
                        name=match.group(1),
                        line_number=i + 1
                    ))
                    
    return classes


def extract_imports(content: str, language: str) -> list[str]:
    """Extract imports from code content."""
    imports = []
    if language == "Python":
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for alias in node.names:
                            imports.append(f"{node.module}.{alias.name}")
        except Exception:
            pass
    else:
        pattern = IMPORT_PATTERNS.get(language)
        if pattern:
            lines = content.splitlines()
            for line in lines:
                match = pattern.search(line)
                if match:
                    imports.append(line.strip())
                    
    return imports


def analyze_file(filepath: str, project_root: str) -> Optional[FileAnalysis]:
    """Perform a complete analysis of a single file."""
    if is_binary_file(filepath):
        return None
        
    language = detect_language(filepath)
    if language == "Unknown":
        # We might still want to count metrics for unknown text files
        pass
        
    path_obj = Path(filepath)
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None
        
    try:
        rel_path = str(path_obj.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        rel_path = path_obj.name
        
    info = FileInfo(
        path=filepath,
        relative_path=rel_path,
        language=language,
        size_bytes=os.path.getsize(filepath),
        extension=path_obj.suffix.lower()
    )
    
    metrics = compute_metrics(filepath, language)
    
    functions = extract_functions(content, language)
    classes = extract_classes(content, language)
    imports = extract_imports(content, language)
    
    return FileAnalysis(
        info=info,
        metrics=metrics,
        functions=functions,
        classes=classes,
        imports=imports
    )
