"""Audit trail for workspace-level dashboard operations."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Mapping

from src.web import data_provider
from src.web.atomic_store import write_json_atomic


STORE_PATH = data_provider.PROJECT_ROOT / "data" / "web_workspace" / "workspace_audit.json"
EVENT_LIMIT = 120


def get_workspace_audit(
    *,
    limit: int = 12,
    query: str = "",
    category: str = "",
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Return recent workspace operation audit events."""
    bounded_limit = max(1, min(EVENT_LIMIT, int(limit or 12)))
    cleaned_query = _clean_text(query, max_length=80).lower()
    cleaned_category = _clean_category(category)
    store = _load_store(_path(store_path))
    raw_events = store.get("events") if isinstance(store.get("events"), list) else []
    events = [_sanitize_event(event) for event in raw_events if isinstance(event, Mapping)]
    filtered_events = [
        event for event in events
        if _event_matches_category(event, cleaned_category)
        and _event_matches_query(event, cleaned_query)
    ]
    return {
        "limit": bounded_limit,
        "query": cleaned_query,
        "category": cleaned_category,
        "total_count": len(events),
        "filtered_count": len(filtered_events),
        "events": filtered_events[:bounded_limit],
        "updated_at": str(store.get("updated_at") or ""),
    }


def export_workspace_audit(
    *,
    limit: int = EVENT_LIMIT,
    query: str = "",
    category: str = "",
    store_path: Path | None = None,
) -> dict[str, str]:
    """Return a downloadable workspace operation audit JSON file."""
    audit = get_workspace_audit(limit=limit, query=query, category=category, store_path=store_path)
    payload = {
        "schema_version": 1,
        "exported_at": _now(),
        "event_count": len(audit["events"]),
        **audit,
    }
    return {
        "filename": "canslim-workspace-audit.json",
        "content_type": "application/json; charset=utf-8",
        "body": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    }


def repair_workspace_audit_store(*, store_path: Path | None = None) -> dict[str, Any]:
    """Quarantine a corrupt audit store and replace it with an empty readable store."""
    path = _path(store_path)
    try:
        _load_store(path)
    except ValueError as exc:
        if path.exists() and not path.is_file():
            raise ValueError("Workspace audit store path is not a file") from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        quarantine_path = _quarantine_path(path)
        if path.exists():
            path.replace(quarantine_path)
        updated_at = _now()
        write_json_atomic(path, {"events": [], "updated_at": updated_at})
        return {
            "repaired": True,
            "reason": str(exc),
            "store_path": _relative_path(path),
            "quarantine_path": _relative_path(quarantine_path),
            "updated_at": updated_at,
        }
    return {
        "repaired": False,
        "reason": "audit store is already readable",
        "store_path": _relative_path(path),
        "quarantine_path": "",
        "updated_at": "",
    }


def record_workspace_event(
    action: str,
    *,
    profile: str | None = None,
    summary: str = "",
    detail: Mapping[str, Any] | None = None,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Record a workspace operation event and return the stored event."""
    path = _path(store_path)
    store = _load_store(path)
    events = store.get("events") if isinstance(store.get("events"), list) else []
    event = {
        "at": _now(),
        "action": _clean_token(action, fallback="workspace_operation"),
        "profile": data_provider.normalize_profile(profile or "") if profile else "",
        "summary": _clean_text(summary, max_length=180),
        "detail": _json_safe(dict(detail or {})),
    }
    store = {
        "events": [event, *[item for item in events if isinstance(item, Mapping)]][:EVENT_LIMIT],
        "updated_at": event["at"],
    }
    write_json_atomic(path, store)
    return event


def _load_store(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {"events": []}
    try:
        payload = json.loads(path.read_text())
    except OSError as exc:
        raise ValueError("Workspace audit store could not be read") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Workspace audit store is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Workspace audit store root must be a JSON object")
    if payload.get("events") is not None and not isinstance(payload.get("events"), list):
        raise ValueError("Workspace audit store events must be a JSON array")
    return payload


def _sanitize_event(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "at": _clean_text(event.get("at"), max_length=60),
        "action": _clean_token(event.get("action"), fallback="workspace_operation"),
        "profile": data_provider.normalize_profile(event.get("profile") or "") if event.get("profile") else "",
        "summary": _clean_text(event.get("summary"), max_length=180),
        "detail": _json_safe(event.get("detail") if isinstance(event.get("detail"), Mapping) else {}),
    }


def _clean_category(value: Any) -> str:
    normalized = _clean_token(value, fallback="")
    return normalized if normalized in {"download", "workspace", "maintenance"} else ""


def _event_matches_category(event: Mapping[str, Any], category: str) -> bool:
    if not category:
        return True
    return _event_category(event.get("action")) == category


def _event_category(action: Any) -> str:
    normalized = _clean_token(action, fallback="")
    if normalized == "artifact_download" or "download" in normalized or normalized.endswith("_export"):
        return "download"
    if normalized in {"cleanup_temp_files", "repair_audit_store"}:
        return "maintenance"
    return "workspace"


def _event_matches_query(event: Mapping[str, Any], query: str) -> bool:
    if not query:
        return True
    return query in _event_search_text(event)


def _event_search_text(event: Mapping[str, Any]) -> str:
    detail = event.get("detail") if isinstance(event.get("detail"), Mapping) else {}
    detail_values = [str(key) for key in detail]
    detail_values.extend(str(value) for value in detail.values())
    return " ".join(
        str(value or "")
        for value in [
            event.get("at"),
            event.get("action"),
            event.get("profile"),
            event.get("summary"),
            *detail_values,
        ]
    ).lower()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value[:50]]
    return str(value)


def _clean_token(value: Any, *, fallback: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"_", "-"} else "_"
        for char in str(value or "").strip().lower()
    ).strip("_")
    return normalized[:48] or fallback


def _clean_text(value: Any, *, max_length: int) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").strip()[:max_length]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _path(store_path: Path | None) -> Path:
    return store_path or STORE_PATH


def _quarantine_path(path: Path) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"{path.stem}.corrupt-{stamp}{path.suffix}"
    candidate = path.with_name(base_name)
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}.corrupt-{stamp}-{counter}{path.suffix}")
        counter += 1
    return candidate


def _relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(data_provider.PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)
