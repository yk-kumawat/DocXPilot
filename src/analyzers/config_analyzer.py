"""Module to analyze configuration files in a project."""

from pathlib import Path

from analyzers.models import ConfigInfo


def analyze_configs(project_path: str) -> tuple[list[ConfigInfo], list[str], list[str]]:
    """
    Find and read configuration files in a project.

    Args:
        project_path: The root directory of the project.

    Returns:
        A tuple containing:
        - List of ConfigInfo objects for found configs
        - List of extracted environment variables
        - List of deployment targets detected
    """
    configs: list[ConfigInfo] = []
    env_variables: list[str] = []
    deployment_targets: list[str] = []

    root_path = Path(project_path)
    if not root_path.is_dir():
        return configs, env_variables, deployment_targets

    def safe_read_preview(path: Path) -> str:
        try:
            with path.open("r", encoding="utf-8") as f:
                return f.read(500)
        except Exception:
            return ""

    def add_config(path: Path, config_type: str, summary: str) -> None:
        try:
            rel_path = path.relative_to(root_path).as_posix()
        except ValueError:
            return
        
        # Avoid duplicate configs
        if any(c.file_path == rel_path for c in configs):
            return

        configs.append(ConfigInfo(
            file_path=rel_path,
            config_type=config_type,
            summary=summary,
            content_preview=safe_read_preview(path)
        ))

    def process_glob(pattern: str, config_type: str, summary: str, deploy_target: str | None = None) -> None:
        for path in root_path.rglob(pattern):
            if not path.is_file():
                continue
            # Skip common ignore directories
            if any(part in [".git", "node_modules", "venv", ".venv", "__pycache__"] for part in path.parts):
                continue
            
            add_config(path, config_type, summary)
            
            if deploy_target and deploy_target not in deployment_targets:
                deployment_targets.append(deploy_target)

    # 1. Environment files
    for env_name in [".env", ".env.example", ".env.sample", ".env.local"]:
        for path in root_path.rglob(env_name):
            if not path.is_file():
                continue
            if any(part in [".git", "node_modules", "venv", ".venv", "__pycache__"] for part in path.parts):
                continue
            
            add_config(path, "env", "Environment Variables")
            try:
                with path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key = line.split("=", 1)[0].strip()
                            if key.startswith("export "):
                                key = key[7:].strip()
                            if key and key not in env_variables:
                                env_variables.append(key)
            except Exception:
                pass

    # 2. Docker files
    for docker_name in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"]:
        process_glob(docker_name, "docker", "Docker Configuration", deploy_target="Docker")

    # 3. CI/CD configs
    process_glob(".github/workflows/*.yml", "ci_cd", "GitHub Actions")
    process_glob(".gitlab-ci.yml", "ci_cd", "GitLab CI")
    process_glob("Jenkinsfile", "ci_cd", "Jenkins")
    process_glob(".travis.yml", "ci_cd", "Travis CI")
    process_glob(".circleci/config.yml", "ci_cd", "CircleCI")
    process_glob("azure-pipelines.yml", "ci_cd", "Azure DevOps")

    # 4. Build configs
    process_glob("Makefile", "build", "Make")
    process_glob("CMakeLists.txt", "build", "CMake")
    process_glob("webpack.config.js", "build", "Webpack")
    process_glob("vite.config.*", "build", "Vite")
    process_glob("tsconfig.json", "build", "TypeScript")
    process_glob("babel.config.*", "build", "Babel")

    # 5. Linter/Formatter configs
    process_glob(".eslintrc*", "lint", "Linter/Formatter")
    process_glob(".prettierrc*", "lint", "Linter/Formatter")
    process_glob(".flake8", "lint", "Linter/Formatter")
    process_glob(".pylintrc", "lint", "Linter/Formatter")
    process_glob("ruff.toml", "lint", "Linter/Formatter")
    process_glob(".editorconfig", "lint", "Linter/Formatter")

    # 6. Cloud/Deploy configs
    process_glob("vercel.json", "deploy", "Vercel", deploy_target="Vercel")
    process_glob("netlify.toml", "deploy", "Netlify", deploy_target="Netlify")
    process_glob("fly.toml", "deploy", "Fly.io", deploy_target="Fly.io")
    process_glob("app.yaml", "deploy", "Google Cloud", deploy_target="Google Cloud")
    process_glob("serverless.yml", "deploy", "Serverless", deploy_target="Serverless")
    process_glob("terraform/*.tf", "deploy", "Terraform", deploy_target="Terraform")
    process_glob("kubernetes/*.yaml", "deploy", "Kubernetes", deploy_target="Kubernetes")
    process_glob("k8s/*.yaml", "deploy", "Kubernetes", deploy_target="Kubernetes")

    return configs, env_variables, deployment_targets
