"""Analyzer for extracting project dependencies."""

import json
import re
from pathlib import Path
from typing import List

from analyzers.models import DependencyInfo, DependencyReport


def analyze_dependencies(project_path: str) -> DependencyReport:
    """
    Detect package manager config files and extract dependency names.

    Args:
        project_path: Path to the project root.

    Returns:
        DependencyReport: Report containing found dependencies and config files.
    """
    report = DependencyReport()
    root = Path(project_path)

    if not root.is_dir():
        return report

    # Define managers set to keep track
    managers_set = set()

    def add_manager(manager: str, config_path: Path):
        managers_set.add(manager)
        try:
            rel_path = str(config_path.relative_to(root))
        except ValueError:
            rel_path = str(config_path)
        if rel_path not in report.config_files:
            report.config_files.append(rel_path)

    def parse_requirements_txt(file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            add_manager("pip", file_path)
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-e") or line.startswith("-r"):
                    continue
                
                # strip comments
                if " #" in line:
                    line = line.split(" #")[0].strip()
                
                # split version
                name = re.split(r'[=<>~]', line, 1)[0].strip()
                if name:
                    report.dependencies.append(DependencyInfo(name=name, manager="pip"))
        except Exception:
            pass

    def parse_pyproject_toml(file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            added_manager = False
            
            # Simple regex parsing
            in_dependencies = False
            is_dev = False
            manager_name = "pip"
            
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("["):
                    in_dependencies = False
                    is_dev = False
                    if "[project]" in line:
                        added_manager = True
                        manager_name = "pip"
                    elif "[tool.poetry.dependencies]" in line:
                        in_dependencies = True
                        added_manager = True
                        manager_name = "poetry"
                    elif "[tool.poetry.group.dev.dependencies]" in line or "[tool.poetry.dev-dependencies]" in line:
                        in_dependencies = True
                        added_manager = True
                        manager_name = "poetry"
                        is_dev = True
                    continue
                
                if "dependencies" in line and "=" in line and "[" in line and "]" in line:
                    # e.g., dependencies = ["flask", "requests>=2.0"]
                    if not added_manager:
                        added_manager = True
                        manager_name = "pip"
                    deps_str = line[line.find("[")+1:line.rfind("]")]
                    for dep in deps_str.split(","):
                        dep = dep.strip().strip("'\" ")
                        if dep:
                            name = re.split(r'[=<>~]', dep, 1)[0].strip()
                            if name:
                                report.dependencies.append(DependencyInfo(name=name, manager=manager_name))
                elif in_dependencies and "=" in line:
                    name = line.split("=")[0].strip().strip("'\" ")
                    if name:
                        report.dependencies.append(DependencyInfo(name=name, manager=manager_name, is_dev=is_dev))

            if added_manager:
                add_manager(manager_name, file_path)
        except Exception:
            pass

    def parse_pipfile(file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            add_manager("pipenv", file_path)
            in_packages = False
            is_dev = False
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("[packages]"):
                    in_packages = True
                    is_dev = False
                    continue
                elif line.startswith("[dev-packages]"):
                    in_packages = True
                    is_dev = True
                    continue
                elif line.startswith("["):
                    in_packages = False
                    continue
                
                if in_packages and "=" in line:
                    name = line.split("=")[0].strip().strip("'\" ")
                    if name:
                        report.dependencies.append(DependencyInfo(name=name, manager="pipenv", is_dev=is_dev))
        except Exception:
            pass

    def parse_setup_py(file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            match = re.search(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL)
            if match:
                add_manager("pip", file_path)
                deps_str = match.group(1)
                for dep in deps_str.split(","):
                    dep = dep.strip().strip("'\" \n\t")
                    if dep:
                        name = re.split(r'[=<>~]', dep, 1)[0].strip()
                        if name:
                            report.dependencies.append(DependencyInfo(name=name, manager="pip"))
        except Exception:
            pass

    def parse_package_json(file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)
            add_manager("npm/yarn", file_path)
            
            if "dependencies" in data:
                for name, version in data["dependencies"].items():
                    report.dependencies.append(DependencyInfo(name=name, version=str(version), manager="npm/yarn"))
            if "devDependencies" in data:
                for name, version in data["devDependencies"].items():
                    report.dependencies.append(DependencyInfo(name=name, version=str(version), manager="npm/yarn", is_dev=True))
        except Exception:
            pass

    def parse_pom_xml(file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            add_manager("Maven", file_path)
            deps = re.findall(r'<dependency>[\s\S]*?</dependency>', content)
            for dep in deps:
                group = re.search(r'<groupId>(.*?)</groupId>', dep)
                artifact = re.search(r'<artifactId>(.*?)</artifactId>', dep)
                scope = re.search(r'<scope>(.*?)</scope>', dep)
                
                if group and artifact:
                    is_dev = scope is not None and scope.group(1) == "test"
                    name = f"{group.group(1)}:{artifact.group(1)}"
                    report.dependencies.append(DependencyInfo(name=name, manager="Maven", is_dev=is_dev))
        except Exception:
            pass

    def parse_build_gradle(file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            add_manager("Gradle", file_path)
            for line in content.splitlines():
                line = line.strip()
                match = re.search(r'(implementation|compile|api|testImplementation|testCompile)\s+[\'"](.*?)[\'"]', line)
                if match:
                    scope = match.group(1)
                    dep = match.group(2)
                    is_dev = "test" in scope.lower()
                    report.dependencies.append(DependencyInfo(name=dep, manager="Gradle", is_dev=is_dev))
                else:
                    match = re.search(r'(implementation|compile|api|testImplementation|testCompile)\s*\([\'"](.*?)[\'"]\)', line)
                    if match:
                        scope = match.group(1)
                        dep = match.group(2)
                        is_dev = "test" in scope.lower()
                        report.dependencies.append(DependencyInfo(name=dep, manager="Gradle", is_dev=is_dev))
        except Exception:
            pass

    def parse_cargo_toml(file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            add_manager("Cargo/Rust", file_path)
            in_deps = False
            is_dev = False
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("[dependencies]"):
                    in_deps = True
                    is_dev = False
                    continue
                elif line.startswith("[dev-dependencies]"):
                    in_deps = True
                    is_dev = True
                    continue
                elif line.startswith("["):
                    in_deps = False
                    continue
                
                if in_deps and "=" in line:
                    name = line.split("=")[0].strip().strip("'\" ")
                    if name:
                        report.dependencies.append(DependencyInfo(name=name, manager="Cargo/Rust", is_dev=is_dev))
        except Exception:
            pass

    def parse_go_mod(file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            add_manager("Go", file_path)
            in_require = False
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("require ("):
                    in_require = True
                    continue
                elif line.startswith("require "):
                    name = line.split()[1]
                    report.dependencies.append(DependencyInfo(name=name, manager="Go"))
                    continue
                elif in_require and line.startswith(")"):
                    in_require = False
                    continue
                
                if in_require and line:
                    parts = line.split()
                    if len(parts) >= 1:
                        name = parts[0]
                        if name and not name.startswith("//"):
                            report.dependencies.append(DependencyInfo(name=name, manager="Go"))
        except Exception:
            pass

    def parse_gemfile(file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            add_manager("Bundler/Ruby", file_path)
            for line in content.splitlines():
                line = line.strip()
                match = re.search(r'^gem\s+[\'"](.*?)[\'"]', line)
                if match:
                    name = match.group(1)
                    is_dev = "group :test" in line or "group :development" in line
                    report.dependencies.append(DependencyInfo(name=name, manager="Bundler/Ruby", is_dev=is_dev))
        except Exception:
            pass

    def parse_composer_json(file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)
            add_manager("Composer/PHP", file_path)
            if "require" in data:
                for name, version in data["require"].items():
                    report.dependencies.append(DependencyInfo(name=name, version=str(version), manager="Composer/PHP"))
            if "require-dev" in data:
                for name, version in data["require-dev"].items():
                    report.dependencies.append(DependencyInfo(name=name, version=str(version), manager="Composer/PHP", is_dev=True))
        except Exception:
            pass

    def parse_pubspec_yaml(file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            add_manager("Dart", file_path)
            in_deps = False
            is_dev = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("dependencies:"):
                    in_deps = True
                    is_dev = False
                    continue
                elif stripped.startswith("dev_dependencies:"):
                    in_deps = True
                    is_dev = True
                    continue
                elif stripped and not line.startswith(" ") and stripped.endswith(":"):
                    in_deps = False
                    continue
                
                if in_deps and stripped and not stripped.startswith("#"):
                    if ":" in stripped:
                        name = stripped.split(":")[0].strip()
                        if name and name not in ("flutter", "sdk"):
                            report.dependencies.append(DependencyInfo(name=name, manager="Dart", is_dev=is_dev))
        except Exception:
            pass

    def parse_csproj(file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
            add_manager("NuGet/.NET", file_path)
            refs = re.findall(r'<PackageReference\s+Include="([^"]+)"', content)
            for ref in refs:
                report.dependencies.append(DependencyInfo(name=ref, manager="NuGet/.NET"))
        except Exception:
            pass

    # Find and parse files
    try:
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
                
            # Skip common ignored dirs
            if any(part.startswith(".") or part in ("node_modules", "venv", "env") for part in file_path.parts):
                continue
                
            name = file_path.name

            if name == "requirements.txt":
                parse_requirements_txt(file_path)
            elif name == "pyproject.toml":
                parse_pyproject_toml(file_path)
            elif name == "Pipfile":
                parse_pipfile(file_path)
            elif name == "setup.py":
                parse_setup_py(file_path)
            elif name == "package.json":
                parse_package_json(file_path)
            elif name == "pom.xml":
                parse_pom_xml(file_path)
            elif name in ("build.gradle", "build.gradle.kts"):
                parse_build_gradle(file_path)
            elif name == "Cargo.toml":
                parse_cargo_toml(file_path)
            elif name == "go.mod":
                parse_go_mod(file_path)
            elif name == "Gemfile":
                parse_gemfile(file_path)
            elif name == "composer.json":
                parse_composer_json(file_path)
            elif name == "pubspec.yaml":
                parse_pubspec_yaml(file_path)
            elif name.endswith(".csproj"):
                parse_csproj(file_path)
    except Exception:
        pass

    report.managers_found = sorted(list(managers_set))
    return report
