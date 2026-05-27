"""Runtime metadata for the local web dashboard process."""

from __future__ import annotations

import datetime as dt
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any


APP_NAME = "CANSLIM SEPA Dashboard"
APP_VERSION = "0.1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
STARTED_AT = dt.datetime.now(dt.timezone.utc)
STARTED_MONOTONIC = time.monotonic()
RUN_ID = secrets.token_hex(6)
SOURCE_METADATA = {
    "git_available": False,
    "git_commit": "",
    "git_branch": "",
    "git_dirty": False,
    "git_untracked": False,
}


def runtime_metadata() -> dict[str, Any]:
    """Return stable process metadata for health checks and support bundles."""
    return {
        "run_id": RUN_ID,
        "started_at": STARTED_AT.isoformat(),
        "uptime_seconds": round(max(0.0, time.monotonic() - STARTED_MONOTONIC), 1),
        "app": {
            "name": APP_NAME,
            "version": APP_VERSION,
        },
        "source": dict(SOURCE_METADATA),
    }


def _git_output(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _release_source_metadata() -> dict[str, Any]:
    commit = _git_output("rev-parse", "--short=12", "HEAD")
    branch = _git_output("rev-parse", "--abbrev-ref", "HEAD")
    status = _git_output("status", "--porcelain")
    status_lines = [line for line in status.splitlines() if line.strip()]
    return {
        "git_available": bool(commit),
        "git_commit": commit,
        "git_branch": "" if branch == "HEAD" else branch,
        "git_dirty": any(not line.startswith("??") for line in status_lines),
        "git_untracked": any(line.startswith("??") for line in status_lines),
    }


SOURCE_METADATA = _release_source_metadata()
