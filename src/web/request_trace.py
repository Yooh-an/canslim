"""In-memory request trace for support diagnostics."""

from __future__ import annotations

import datetime as dt
import threading
import time
from collections import deque
from urllib.parse import urlparse
from typing import Any

from src.web import redaction, runtime_info


TRACE_LIMIT = 120
CLIENT_EVENT_LIMIT = 80
CLIENT_EVENT_RATE_LIMIT = 30
CLIENT_EVENT_RATE_WINDOW_SECONDS = 60
DEFAULT_EXPORT_LIMIT = 25
MAX_ERROR_LENGTH = 180
MAX_CLIENT_MESSAGE_LENGTH = 220
ALLOWED_CLIENT_EVENT_KINDS = {"error", "unhandledrejection", "resource_error"}

_LOCK = threading.RLock()
_TRACE: deque[dict[str, Any]] = deque(maxlen=TRACE_LIMIT)
_CLIENT_EVENTS: deque[dict[str, Any]] = deque(maxlen=CLIENT_EVENT_LIMIT)
_CLIENT_EVENT_TIMESTAMPS: deque[float] = deque()


class RateLimitExceeded(RuntimeError):
    """Raised when diagnostic intake is temporarily throttled."""

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def record_request(
    *,
    request_id: str,
    method: str,
    path: str,
    status: int,
    duration_ms: float,
    error_code: str = "",
    error: str = "",
) -> None:
    """Record non-body request metadata for recent support diagnostics."""
    entry = {
        "at": _now(),
        "request_id": str(request_id or ""),
        "method": str(method or "").upper(),
        "path": str(path or ""),
        "status": int(status),
        "duration_ms": round(max(0.0, float(duration_ms)), 1),
        "outcome": "error" if int(status) >= 400 else "ok",
        "run_id": runtime_info.RUN_ID,
    }
    if error_code:
        entry["error_code"] = str(error_code)
    if error:
        entry["error"] = _truncate_error(error)
    with _LOCK:
        _TRACE.append(entry)


def recent_request_trace(*, limit: int = DEFAULT_EXPORT_LIMIT) -> dict[str, Any]:
    """Return the newest request metadata first."""
    bounded_limit = max(1, min(int(limit or DEFAULT_EXPORT_LIMIT), TRACE_LIMIT))
    with _LOCK:
        entries = list(_TRACE)[-bounded_limit:]
    return {
        "requests": list(reversed(entries)),
        "returned": len(entries),
        "limit": TRACE_LIMIT,
    }


def record_client_event(event: dict[str, Any], *, profile: str = "") -> dict[str, Any]:
    """Record redacted browser runtime event metadata."""
    if not isinstance(event, dict):
        raise ValueError("Client event must be a JSON object")
    monotonic_now = time.monotonic()
    kind = _client_event_kind(event.get("kind", event.get("type")))
    entry: dict[str, Any] = {
        "at": _now(),
        "profile": _safe_text(profile, max_length=60),
        "kind": kind,
        "message": _safe_text(event.get("message"), max_length=MAX_CLIENT_MESSAGE_LENGTH) or "Client event",
        "page_path": _safe_path(event.get("page_path")),
        "source": _safe_source(event.get("source")),
        "run_id": runtime_info.RUN_ID,
    }
    line = _bounded_int(event.get("line", event.get("lineno")), low=0, high=1_000_000)
    column = _bounded_int(event.get("column", event.get("colno")), low=0, high=1_000_000)
    if line is not None:
        entry["line"] = line
    if column is not None:
        entry["column"] = column
    with _LOCK:
        _enforce_client_event_rate_limit(monotonic_now)
        _CLIENT_EVENTS.append(entry)
    return dict(entry)


def recent_client_events(*, limit: int = DEFAULT_EXPORT_LIMIT) -> dict[str, Any]:
    """Return newest redacted browser runtime events first."""
    bounded_limit = max(1, min(int(limit or DEFAULT_EXPORT_LIMIT), CLIENT_EVENT_LIMIT))
    with _LOCK:
        entries = list(_CLIENT_EVENTS)[-bounded_limit:]
    return {
        "events": list(reversed(entries)),
        "returned": len(entries),
        "limit": CLIENT_EVENT_LIMIT,
    }


def clear_request_trace() -> None:
    """Clear trace state for tests."""
    with _LOCK:
        _TRACE.clear()
        _CLIENT_EVENTS.clear()
        _CLIENT_EVENT_TIMESTAMPS.clear()


def _enforce_client_event_rate_limit(monotonic_now: float) -> None:
    cutoff = monotonic_now - CLIENT_EVENT_RATE_WINDOW_SECONDS
    while _CLIENT_EVENT_TIMESTAMPS and _CLIENT_EVENT_TIMESTAMPS[0] <= cutoff:
        _CLIENT_EVENT_TIMESTAMPS.popleft()
    if len(_CLIENT_EVENT_TIMESTAMPS) >= CLIENT_EVENT_RATE_LIMIT:
        oldest = _CLIENT_EVENT_TIMESTAMPS[0]
        retry_after = max(1, int(round(CLIENT_EVENT_RATE_WINDOW_SECONDS - (monotonic_now - oldest))))
        raise RateLimitExceeded("Client event intake is rate limited", retry_after_seconds=retry_after)
    _CLIENT_EVENT_TIMESTAMPS.append(monotonic_now)


def _client_event_kind(value: Any) -> str:
    kind = str(value or "").strip().lower().replace("-", "_")
    return kind if kind in ALLOWED_CLIENT_EVENT_KINDS else "error"


def _safe_source(value: Any) -> str:
    text = _safe_text(value, max_length=200)
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        return parsed.path[:160] or parsed.netloc[:80]
    return text.split("?", 1)[0].split("#", 1)[0][:160]


def _safe_path(value: Any) -> str:
    text = _safe_text(value, max_length=160)
    if not text:
        return ""
    parsed = urlparse(text)
    path = parsed.path or text.split("?", 1)[0].split("#", 1)[0]
    return path[:160]


def _safe_text(value: Any, *, max_length: int) -> str:
    return " ".join(str(value or "").split())[:max_length]


def _bounded_int(value: Any, *, low: int, high: int) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return min(high, max(low, number))


def _truncate_error(error: str) -> str:
    text = " ".join(str(error or "").split())
    return redaction.redact_local_paths(text)[:MAX_ERROR_LENGTH]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
