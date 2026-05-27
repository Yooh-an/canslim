"""Persistent daily session journal for the local web dashboard."""

from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any, Mapping

from src.web import data_provider
from src.web.atomic_store import write_json_atomic


STORE_PATH = data_provider.PROJECT_ROOT / "data" / "web_workspace" / "session_journal.json"
NOTE_FIELDS = ("market_thesis", "watchlist_focus", "risk_notes", "post_session_review")
MAX_NOTE_LENGTH = 2000
MAX_ENTRIES_PER_PROFILE = 260

_LOCK = threading.RLock()


def get_session_journal(
    profile: str | None = None,
    *,
    session_date: str | None = None,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Return one profile/date journal entry, with empty fields when missing."""
    profile_name = data_provider.normalize_profile(profile or "")
    date_key = _clean_date(session_date)
    with _LOCK:
        store = _load_store(_path(store_path))
        entry = _profile_entries(store, profile_name).get(date_key, {})
    return _sanitize_entry(entry, profile_name=profile_name, session_date=date_key)


def save_session_journal(
    profile: str | None,
    payload: Mapping[str, Any],
    *,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Persist one profile/date journal entry."""
    profile_name = data_provider.normalize_profile(str(payload.get("profile") or profile or ""))
    date_key = _clean_date(payload.get("date"))
    entry = _sanitize_entry(payload, profile_name=profile_name, session_date=date_key)
    entry["updated_at"] = _now()
    with _LOCK:
        path = _path(store_path)
        store = _load_store(path)
        profiles = _profiles(store)
        entries = dict(profiles.get(profile_name) or {})
        entries[date_key] = entry
        profiles[profile_name] = _trim_entries(entries)
        store = {"profiles": profiles, "updated_at": entry["updated_at"]}
        _write_store(path, store)
    return entry


def get_journal_entries(
    profile: str | None = None,
    *,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Return all saved journal entries for a profile, newest first."""
    profile_name = data_provider.normalize_profile(profile or "")
    with _LOCK:
        store = _load_store(_path(store_path))
        entries = _profile_entries(store, profile_name)
    return {
        "profile": profile_name,
        "entries": [
            _sanitize_entry(entry, profile_name=profile_name, session_date=date_key)
            for date_key, entry in sorted(entries.items(), reverse=True)
        ],
    }


def replace_journal_entries(
    profile: str | None,
    entries_payload: Any,
    *,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Replace a profile's journal entries from a workspace snapshot payload."""
    if isinstance(entries_payload, Mapping):
        raw_entries = entries_payload.get("entries", [])
    else:
        raw_entries = entries_payload
    if not isinstance(raw_entries, list):
        raise ValueError("Workspace snapshot journal.entries must be a JSON array")

    profile_name = data_provider.normalize_profile(profile or "")
    entries: dict[str, dict[str, Any]] = {}
    for item in raw_entries:
        if not isinstance(item, Mapping):
            continue
        date_key = _clean_date(item.get("date"))
        entries[date_key] = _sanitize_entry(item, profile_name=profile_name, session_date=date_key)

    updated_at = _now()
    with _LOCK:
        path = _path(store_path)
        store = _load_store(path)
        profiles = _profiles(store)
        profiles[profile_name] = _trim_entries(entries)
        store = {"profiles": profiles, "updated_at": updated_at}
        _write_store(path, store)
    return get_journal_entries(profile_name, store_path=store_path)


def _sanitize_entry(entry: Mapping[str, Any], *, profile_name: str, session_date: str) -> dict[str, Any]:
    sanitized: dict[str, Any] = {
        "profile": profile_name,
        "date": session_date,
    }
    for field in NOTE_FIELDS:
        sanitized[field] = _clean_note(entry.get(field))
    sanitized["updated_at"] = _clean_text(entry.get("updated_at"), max_length=40) or ""
    return sanitized


def _load_store(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        payload = json.loads(path.read_text())
    except OSError as exc:
        raise ValueError("Session journal store could not be read") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Session journal store is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Session journal store root must be a JSON object")
    return payload


def _write_store(path: Path, store: Mapping[str, Any]) -> None:
    write_json_atomic(path, store)


def _profiles(store: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    profiles = store.get("profiles")
    return dict(profiles) if isinstance(profiles, Mapping) else {}


def _profile_entries(store: Mapping[str, Any], profile_name: str) -> dict[str, Any]:
    entries = _profiles(store).get(profile_name)
    return dict(entries) if isinstance(entries, Mapping) else {}


def _trim_entries(entries: Mapping[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return dict(sorted(entries.items(), reverse=True)[:MAX_ENTRIES_PER_PROFILE])


def _clean_date(value: Any) -> str:
    text = _clean_text(value, max_length=10) or _today()
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError:
        return _today()


def _clean_note(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").strip()
    return text[:MAX_NOTE_LENGTH]


def _clean_text(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text[:max_length] if text else None


def _path(store_path: Path | None) -> Path:
    return store_path or STORE_PATH


def _today() -> str:
    return dt.date.today().isoformat()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
