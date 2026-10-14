"""Data collection script for DocXPilot Activity Analyzer training.

Clones a curated list of public repositories into a temporary directory,
extracts their daily commit+churn signals using the same logic the analyzer
uses, and saves them as .npy files in src/ml/data/.

Run this script once before training:
    python src/ml/collect_data.py

Requirements: git must be installed and network access to GitHub is needed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

# Add src to path so we can import analyzers
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyzers.activity_signal import build_signals  # noqa: E402

# Curated list of repos with 1+ years of moderate history
REPOS = [
    "https://github.com/psf/requests",
    "https://github.com/pallets/flask",
    "https://github.com/pallets/click",
    "https://github.com/Textualize/rich",
    "https://github.com/tiangolo/typer",
    "https://github.com/psf/black",
    "https://github.com/encode/httpx",
    "https://github.com/tiangolo/fastapi",
    "https://github.com/encode/django-rest-framework",
    "https://github.com/celery/celery",
    "https://github.com/sqlalchemy/sqlalchemy",
    "https://github.com/pytest-dev/pytest",
    "https://github.com/aio-libs/aiohttp",
    "https://github.com/python-attrs/attrs",
    "https://github.com/pydantic/pydantic",
]

DATA_DIR = Path(__file__).resolve().parent / "data"


def clone_and_extract(repo_url: str, tmp_dir: str) -> np.ndarray | None:
    """Clone *repo_url* into *tmp_dir* and extract its activity signal.

    Returns:
        (2, N) float32 ndarray, or None if cloning/extraction fails.
    """
    repo_name = repo_url.rstrip("/").split("/")[-1]
    clone_path = os.path.join(tmp_dir, repo_name)
    print(f"  Cloning {repo_name}...", end=" ", flush=True)
    try:
        subprocess.run(
            ["git", "clone", "--depth=0", repo_url, clone_path],
            capture_output=True,
            timeout=300,
            check=True,
        )
    except Exception as exc:
        # depth=0 not supported everywhere — try without depth flag
        try:
            subprocess.run(
                ["git", "clone", repo_url, clone_path],
                capture_output=True,
                timeout=600,
                check=True,
            )
        except Exception as exc2:
            print(f"FAILED ({exc2})")
            return None

    try:
        _, signals = build_signals(clone_path)
        print(f"OK  shape={signals.shape}")
        return signals
    except ValueError as exc:
        print(f"SKIPPED ({exc})")
        return None
    except Exception as exc:
        print(f"ERROR ({exc})")
        return None
    finally:
        # Always clean up the clone to save disk space
        shutil.rmtree(clone_path, ignore_errors=True)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Saving signals to: {DATA_DIR}\n")

    with tempfile.TemporaryDirectory(prefix="docxpilot_train_") as tmp:
        for repo_url in REPOS:
            repo_name = repo_url.rstrip("/").split("/")[-1]
            out_path = DATA_DIR / f"{repo_name}.npy"
            if out_path.exists():
                print(f"  {repo_name}: already exists, skipping.")
                continue
            sig = clone_and_extract(repo_url, tmp)
            if sig is not None:
                np.save(str(out_path), sig)

    files = list(DATA_DIR.glob("*.npy"))
    print(f"\nDone. {len(files)} signal file(s) in {DATA_DIR}")


if __name__ == "__main__":
    main()
