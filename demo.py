"""One-command demo for DocXPilot Activity Signal Analyzer.

Creates a realistic sample repository with 150 days of history:
  - Weekly seasonality (peak commits on weekdays, quiet weekends)
  - An inactivity lull / vacation gap (21 days of zero commits)
  - A crunch / burst window (high commit volume for 3 days)
Then runs `docxpilot activity` to demonstrate the DSP + DL pipeline.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

# Add src to sys.path
SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))


def create_demo_repo(target_dir: Path) -> Path:
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Initializing sample git repository at: {target_dir}")
    subprocess.run(["git", "init"], cwd=str(target_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "demo@docxpilot.io"], cwd=str(target_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "DocXPilot Demo"], cwd=str(target_dir), check=True, capture_output=True)

    start_date = date.today() - timedelta(days=150)
    current_date = start_date

    commit_idx = 0
    while current_date < date.today():
        day_offset = (current_date - start_date).days
        weekday = current_date.weekday()

        # Inactivity gap between day 50 and 72 (22 days)
        if 50 <= day_offset <= 72:
            current_date += timedelta(days=1)
            continue

        # Burst window between day 105 and 108
        if 105 <= day_offset <= 108:
            n_commits = 8
        elif weekday in (5, 6):
            # Weekend lull
            n_commits = 1 if (commit_idx % 3 == 0) else 0
        else:
            # Normal weekday: 2 to 4 commits
            n_commits = 2 + (commit_idx % 3)

        for c in range(n_commits):
            iso_time = f"{current_date.isoformat()}T{10 + c:02d}:00:00+00:00"
            code_file = target_dir / f"module_{commit_idx % 5}.py"
            code_file.write_text(f"# Commit {commit_idx}\ndef func_{commit_idx}():\n    return {c * 10}\n")
            subprocess.run(["git", "add", "."], cwd=str(target_dir), check=True, capture_output=True)
            env = os.environ.copy()
            env["GIT_AUTHOR_DATE"] = iso_time
            env["GIT_COMMITTER_DATE"] = iso_time
            subprocess.run(
                ["git", "commit", "-m", f"feat: update module (commit {commit_idx})"],
                cwd=str(target_dir),
                env=env,
                check=True,
                capture_output=True,
            )
            commit_idx += 1

        current_date += timedelta(days=1)

    print(f"[*] Created {commit_idx} commits across 150 days.")
    return target_dir


def main():
    repo_dir = Path(__file__).resolve().parent / "demo_repo"
    create_demo_repo(repo_dir)

    print("\n" + "=" * 60)
    print("RUNNING DOCXPILOT ACTIVITY SIGNAL ANALYZER")
    print("=" * 60 + "\n")

    from analyzers.activity_analyzer import analyze_activity, print_activity_summary

    report = analyze_activity(str(repo_dir), output_dir=str(repo_dir))
    print_activity_summary(report)

    print("\n" + "=" * 60)
    print("GENERATED ARTIFACTS:")
    print("=" * 60)
    for p in report.plot_paths:
        print(f"  - {p} (exists: {Path(p).exists()})")


if __name__ == "__main__":
    main()
