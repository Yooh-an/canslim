"""Background pipeline job runner for the local web dashboard."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from src.web import data_provider
from src.web.atomic_store import write_json_atomic


JOB_HISTORY_PATH = data_provider.PROJECT_ROOT / "data" / "web_workspace" / "job_history.json"
ALLOWED_MODES = {"status", "download", "parse", "enrich", "screen", "update", "tv-export", "profile-sweep"}
NEXT_ACTION_MODE = {
    "download": "download",
    "parse": "parse",
    "enrich": "enrich",
    "institutional-data": "enrich",
    "screen": "screen",
    "screen-profiles": "profile-sweep",
    "profile-outputs": "profile-sweep",
}
MAX_LOG_LINES = 240
HISTORY_LIMIT = 20
HISTORY_LOG_LINES = 12

_LOCK = threading.RLock()
_CURRENT_JOB: dict[str, Any] | None = None
_CURRENT_PROCESS: subprocess.Popen[str] | None = None
_JOB_COUNTER = 0


def current_job() -> dict[str, Any]:
    """Return the current or most recent pipeline job."""
    with _LOCK:
        if _CURRENT_JOB is None:
            return {"status": "idle", "running": False}
        return _copy_job(_CURRENT_JOB)


def job_history(*, limit: int = 10, store_path: Path | None = None) -> dict[str, Any]:
    """Return recent pipeline job history."""
    bounded_limit = max(1, min(int(limit or 10), HISTORY_LIMIT))
    with _LOCK:
        history = _load_history(_history_path(store_path))
        return {"jobs": history[:bounded_limit], "limit": HISTORY_LIMIT}


def start_job(mode: str, profile: str | None = None) -> dict[str, Any]:
    """Start a background pipeline job for an allowed mode."""
    normalized_mode = normalize_mode(mode)
    profile_name = data_provider.normalize_profile(profile)
    command = build_command(normalized_mode, profile_name)

    global _CURRENT_JOB, _JOB_COUNTER
    with _LOCK:
        if _CURRENT_JOB and _CURRENT_JOB.get("running"):
            raise RuntimeError("A pipeline job is already running")
        _JOB_COUNTER += 1
        job = {
            "id": _JOB_COUNTER,
            "mode": normalized_mode,
            "profile": profile_name,
            "status": "running",
            "running": True,
            "command": " ".join(command),
            "started_at": _now(),
            "finished_at": None,
            "returncode": None,
            "log": [],
        }
        _CURRENT_JOB = job
        _record_history_unlocked(job)

    thread = threading.Thread(target=_run_job, args=(job, command), daemon=True)
    thread.start()
    return current_job()


def cancel_job() -> dict[str, Any]:
    """Request cancellation of the currently running pipeline job."""
    with _LOCK:
        if not _CURRENT_JOB or not _CURRENT_JOB.get("running"):
            return current_job()
        job = _CURRENT_JOB
        process = _CURRENT_PROCESS
        job["cancel_requested"] = True
        _append_log(job, "Cancellation requested.")
        if process is None or process.poll() is not None:
            _update_job(job, status="cancelled", running=False, returncode=-15, finished_at=_now())
            return current_job()
        _update_job(job, status="cancelling", running=True)
    try:
        process.terminate()
    except Exception as exc:  # pragma: no cover - depends on local process state
        _append_log(job, f"Unable to cancel job: {exc}")
        _update_job(job, status="failed", running=False, returncode=-1, finished_at=_now())
    return current_job()


def normalize_mode(mode: str) -> str:
    """Normalize and validate a user-facing pipeline mode."""
    normalized = str(mode or "").strip().lower().replace("_", "-")
    normalized = NEXT_ACTION_MODE.get(normalized, normalized)
    if normalized not in ALLOWED_MODES:
        raise ValueError(f"Unsupported pipeline mode: {mode}")
    return normalized


def build_command(mode: str, profile: str) -> list[str]:
    """Build the subprocess command for a pipeline mode."""
    normalized_mode = normalize_mode(mode)
    profile_name = data_provider.normalize_profile(profile)
    command = [
        sys.executable,
        "run_screener.py",
        "--mode",
        normalized_mode,
        "--config",
        str(data_provider.CONFIG_PATH.relative_to(data_provider.PROJECT_ROOT)),
    ]
    if profile_name and normalized_mode != "profile-sweep":
        command.extend(["--profile", profile_name])
    return command


def _run_job(job: dict[str, Any], command: list[str]) -> None:
    global _CURRENT_PROCESS
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=data_provider.PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        with _LOCK:
            _CURRENT_PROCESS = process
        _update_job(job, pid=process.pid)
        assert process.stdout is not None
        for line in process.stdout:
            _append_log(job, line.rstrip())
        returncode = process.wait()
        _update_job(
            job,
            status=_finish_status(job, returncode),
            running=False,
            returncode=returncode,
            finished_at=_now(),
        )
    except Exception as exc:  # pragma: no cover - depends on local process state
        if process and process.poll() is None:
            process.kill()
        _append_log(job, f"Job runner error: {exc}")
        _update_job(job, status=_finish_status(job, -1), running=False, returncode=-1, finished_at=_now())
    finally:
        with _LOCK:
            if process is not None and _CURRENT_PROCESS is process:
                _CURRENT_PROCESS = None


def _append_log(job: dict[str, Any], line: str) -> None:
    with _LOCK:
        log = job.setdefault("log", [])
        log.append(line)
        del log[:-MAX_LOG_LINES]


def _update_job(job: dict[str, Any], **updates: Any) -> None:
    with _LOCK:
        job.update(updates)
        _record_history_unlocked(job)


def _copy_job(job: dict[str, Any]) -> dict[str, Any]:
    copied = dict(job)
    copied["log"] = list(job.get("log") or [])
    return copied


def _record_history(job: dict[str, Any], *, store_path: Path | None = None) -> None:
    with _LOCK:
        _record_history_unlocked(job, store_path=store_path)


def _record_history_unlocked(job: dict[str, Any], *, store_path: Path | None = None) -> None:
    path = _history_path(store_path)
    history = _load_history(path)
    entry = _history_entry(job)
    history = [existing for existing in history if existing.get("id") != entry["id"]]
    history.insert(0, entry)
    _write_history(path, history[:HISTORY_LIMIT])


def _history_entry(job: dict[str, Any]) -> dict[str, Any]:
    log = [str(line) for line in job.get("log") or [] if str(line)]
    return {
        "id": job.get("id"),
        "mode": job.get("mode"),
        "profile": job.get("profile"),
        "status": job.get("status"),
        "running": bool(job.get("running")),
        "command": job.get("command"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "returncode": job.get("returncode"),
        "pid": job.get("pid"),
        "cancel_requested": bool(job.get("cancel_requested")),
        "log_tail": log[-HISTORY_LOG_LINES:],
    }


def _load_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        return []
    return [job for job in payload["jobs"] if isinstance(job, dict)]


def _write_history(path: Path, jobs: list[dict[str, Any]]) -> None:
    write_json_atomic(path, {"jobs": jobs})


def _history_path(store_path: Path | None) -> Path:
    return store_path or JOB_HISTORY_PATH


def _finish_status(job: dict[str, Any], returncode: int) -> str:
    if job.get("cancel_requested"):
        return "cancelled"
    return "succeeded" if returncode == 0 else "failed"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
