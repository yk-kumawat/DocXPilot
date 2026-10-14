"""Activity Signal Extractor for DocXPilot.

Parses `git log --numstat` output for a repository and returns a pair of
daily discrete-time signals:

  commits[n]  — number of commits on calendar day n
  churn[n]    — lines added + lines deleted on calendar day n

Both signals are indexed from the first commit day to the last commit day
(one sample per day, fs = 1 sample/day). Days with no activity are 0.

After building the raw integer signals, log1p compression is applied to
reduce the dynamic range before DSP and modeling.
"""

from __future__ import annotations

import subprocess
from datetime import date, timedelta, timezone
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: str, timeout: int = 120) -> str:
    """Run a git command and return stdout. Returns '' on any error."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            # Use utf-8 with replacement so binary file paths don't crash
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=True,
        )
        return result.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def is_git_repo(project_path: str) -> bool:
    """Return True if *project_path* is inside a git repository."""
    result = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=project_path)
    return result.strip() == "true"


def build_signals(project_path: str) -> tuple[list[date], np.ndarray]:
    """Build daily commit and churn signals from the full git history.

    The git log is fetched with `--numstat` so we get per-file add/delete
    counts. A custom separator `@@<hash>|<ISO-date>` is used to distinguish
    commit headers from numstat lines.

    Args:
        project_path: Absolute path to the repository root.

    Returns:
        A tuple ``(dates, signals)`` where
          * ``dates`` is a list of :class:`datetime.date` objects, one per
            calendar day from the first commit to the last commit.
          * ``signals`` is a float32 ndarray of shape ``(2, N)`` with:
              - row 0: log1p(commits per day)
              - row 1: log1p(churn per day)

    Raises:
        ValueError: If the repository has fewer than 60 days of history or
                    fewer than 30 non-merge commits, or is not a git repo.
    """
    if not is_git_repo(project_path):
        raise ValueError("Not a git repository or git is not installed.")

    # ------------------------------------------------------------------
    # 1.  Fetch full history.  Limit to 3 years so huge repos stay fast.
    # ------------------------------------------------------------------
    raw = _run_git(
        [
            "log",
            "--no-merges",
            "--numstat",
            "--format=@@%H|%aI",   # custom separator + ISO author date
            "--after=3 years ago",
        ],
        cwd=project_path,
        timeout=120,
    )

    if not raw.strip():
        raise ValueError("No git history found (empty log or shallow clone).")

    # ------------------------------------------------------------------
    # 2.  Parse: group numstat lines by commit date
    # ------------------------------------------------------------------
    # Maps date -> (commit_count, churn_total)
    daily: dict[date, list[int]] = {}
    current_date: date | None = None

    for line in raw.splitlines():
        line = line.rstrip()
        if line.startswith("@@"):
            # Header line: @@<hash>|<ISO date>
            _, _, rest = line.partition("|")
            iso = rest.strip()
            try:
                # Parse ISO 8601 with timezone, convert to UTC date
                from datetime import datetime
                dt = datetime.fromisoformat(iso)
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc)
                current_date = dt.date()
            except ValueError:
                current_date = None
            if current_date is not None:
                if current_date not in daily:
                    daily[current_date] = [0, 0]   # [commit_count, churn]
                daily[current_date][0] += 1         # count this commit
            continue

        if current_date is None or not line.strip():
            continue

        # numstat line: "<added>\t<deleted>\t<filename>"
        # Binary files show "-" for add/del counts — treat as 0
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        try:
            added = int(parts[0]) if parts[0] != "-" else 0
            deleted = int(parts[1]) if parts[1] != "-" else 0
            daily[current_date][1] += added + deleted
        except ValueError:
            continue

    if not daily:
        raise ValueError("Could not parse any commits from git log.")

    # ------------------------------------------------------------------
    # 3.  Validate minimum history requirements
    # ------------------------------------------------------------------
    first_day = min(daily)
    last_day = max(daily)
    span = (last_day - first_day).days + 1
    total_commits = sum(v[0] for v in daily.values())

    if span < 60:
        raise ValueError(
            f"History too short: only {span} days. "
            "Need at least 60 days for meaningful signal analysis."
        )
    if total_commits < 30:
        raise ValueError(
            f"Too few commits: {total_commits}. "
            "Need at least 30 non-merge commits for analysis."
        )

    # ------------------------------------------------------------------
    # 4.  Build dense daily arrays (zeros for inactive days)
    # ------------------------------------------------------------------
    dates = [first_day + timedelta(days=i) for i in range(span)]
    commits_raw = np.array([daily.get(d, [0, 0])[0] for d in dates], dtype=np.float32)
    churn_raw   = np.array([daily.get(d, [0, 0])[1] for d in dates], dtype=np.float32)

    # ------------------------------------------------------------------
    # 5.  Log1p compression to reduce burst dominance
    # ------------------------------------------------------------------
    signals = np.stack([np.log1p(commits_raw), np.log1p(churn_raw)], axis=0)  # (2, N)

    return dates, signals
