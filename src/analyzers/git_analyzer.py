import subprocess
from pathlib import Path
from collections import Counter
from analyzers.models import GitCommit, GitInfo

def analyze_git(project_path: str) -> GitInfo:
    """
    Analyze a project's git history using subprocess calls to the `git` command.

    Args:
        project_path: The absolute or relative path to the project directory.

    Returns:
        GitInfo: A dataclass containing the git repository analysis results.
    """
    path = Path(project_path)
    
    def run_git_command(args: list[str]) -> str:
        """Run a git command and return its standard output as a string."""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    # 1. Check if the path is inside a git repo
    is_inside = run_git_command(["rev-parse", "--is-inside-work-tree"])
    if is_inside != "true":
        return GitInfo(is_git_repo=False)

    git_info = GitInfo(is_git_repo=True)

    # 2. Get total commit count
    count_str = run_git_command(["rev-list", "--count", "HEAD"])
    try:
        git_info.total_commits = int(count_str) if count_str else 0
    except ValueError:
        pass

    # 3. Get list of contributors
    authors_output = run_git_command(["log", "--format=%aN"])
    if authors_output:
        authors = set(author for author in authors_output.splitlines() if author.strip())
        git_info.contributors = sorted(list(authors))

    # 4. Get recent commits (last 20)
    recent_commits_output = run_git_command(["log", "-20", "--format=%H|||%aN|||%aI|||%s"])
    if recent_commits_output:
        for line in recent_commits_output.splitlines():
            parts = line.split("|||", 3)
            if len(parts) == 4:
                git_info.recent_commits.append(
                    GitCommit(
                        hash=parts[0].strip(),
                        author=parts[1].strip(),
                        date=parts[2].strip(),
                        message=parts[3].strip()
                    )
                )

    # 5. Get current branch
    git_info.current_branch = run_git_command(["branch", "--show-current"])

    # 6. Get remote URL
    git_info.remote_url = run_git_command(["remote", "get-url", "origin"])

    # 7. Get first commit date
    git_info.first_commit_date = run_git_command(["log", "--reverse", "--format=%aI", "-1"])

    # 8. Get last commit date
    git_info.last_commit_date = run_git_command(["log", "--format=%aI", "-1"])

    # 9. Get most changed files (top 10)
    changed_files_output = run_git_command(["log", "--pretty=format:", "--name-only"])
    if changed_files_output:
        files = [file.strip() for file in changed_files_output.splitlines() if file.strip()]
        if files:
            file_counts = Counter(files)
            most_common = file_counts.most_common(10)
            git_info.most_changed_files = [f for f, count in most_common]

    return git_info
