"""Workspace snapshot import/export helpers for the local web dashboard."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from src.web.atomic_store import write_json_atomic
from src.web import data_provider, review_store, session_journal, workspace_store
from src.web.disclosure import research_disclosure


SCHEMA_VERSION = 1
BACKUP_DIR = data_provider.PROJECT_ROOT / "data" / "web_workspace" / "backups"
BACKUP_LIMIT = 20


def export_workspace_snapshot(
    profile: str | None = None,
    *,
    risk: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Return a downloadable JSON snapshot of the active workspace."""
    snapshot = build_workspace_snapshot(profile, risk=risk)
    body = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return {
        "profile": str(snapshot["profile"]),
        "filename": f"canslim-workspace-{snapshot['profile']}.json",
        "content_type": "application/json; charset=utf-8",
        "body": body,
    }


def import_workspace_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Restore persisted workspace preferences and review queue from a snapshot."""
    normalized = _normalize_snapshot_payload(snapshot)
    preferences_payload = normalized["preferences"]
    profile_name = normalized["profile"]
    review_items = normalized["review_items"]
    review_store.validate_review_import_items(profile_name, review_items)
    backup = save_pre_import_backup(profile_name)
    quarantined_stores = _quarantine_unreadable_workspace_stores()
    saved_preferences = workspace_store.save_preferences({**preferences_payload, "profile": profile_name})
    restored_review = review_store.replace_review_queue(profile_name, review_items)
    restored_journal = (
        session_journal.replace_journal_entries(profile_name, normalized["journal"])
        if normalized["has_journal"]
        else session_journal.get_journal_entries(profile_name)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "imported_at": _now(),
        "profile": profile_name,
        "preferences": saved_preferences,
        "journal": restored_journal,
        "review": restored_review,
        "review_summary": review_store.get_review_summary(profile_name, risk=saved_preferences.get("risk")),
        "backup": backup,
        "quarantined_stores": quarantined_stores,
    }


def save_pre_import_backup(profile: str) -> dict[str, Any]:
    """Persist the current workspace state before a destructive import."""
    profile_name = data_provider.normalize_profile(profile)
    created_at = _now()
    recovery_only = False
    backup_error = ""
    try:
        snapshot = build_workspace_snapshot(profile_name)
        filename = f"canslim-workspace-backup-{profile_name}-{_filename_timestamp(created_at)}.json"
    except ValueError as exc:
        recovery_only = True
        backup_error = str(exc)
        snapshot = _build_raw_store_recovery_snapshot(profile_name, backup_error, exported_at=created_at)
        filename = f"canslim-workspace-recovery-{profile_name}-{_filename_timestamp(created_at)}.json"
    snapshot["backup_reason"] = "pre_workspace_import"
    snapshot["backup_created_at"] = created_at
    path = (BACKUP_DIR / filename).resolve()
    try:
        path.relative_to(BACKUP_DIR.resolve())
    except ValueError as exc:  # pragma: no cover - defensive path guard
        raise ValueError("Invalid workspace backup path") from exc
    write_json_atomic(path, snapshot, trailing_newline=True)
    _prune_workspace_backups(profile_name)
    return {
        "created_at": created_at,
        "profile": profile_name,
        "filename": filename,
        "path": _display_path(path),
        "restorable": not recovery_only,
        "recovery_only": recovery_only,
        "reason": backup_error,
    }


def list_workspace_backups(profile: str | None = None, *, limit: int = 12) -> dict[str, Any]:
    """Return recent pre-import backups for a profile."""
    profile_name = data_provider.normalize_profile(profile)
    bounded_limit = max(1, min(BACKUP_LIMIT, int(limit or 12)))
    backups: list[dict[str, Any]] = []
    if BACKUP_DIR.exists():
        candidates = sorted(
            (
                path
                for path in BACKUP_DIR.glob("*.json")
                if path.is_file() and path.name.startswith("canslim-workspace-backup-")
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in candidates:
            metadata = _backup_metadata(path)
            if not metadata or metadata["profile"] != profile_name:
                continue
            backups.append(metadata)
            if len(backups) >= bounded_limit:
                break
    return {
        "profile": profile_name,
        "limit": bounded_limit,
        "backups": backups,
    }


def restore_workspace_backup(filename: str, *, expected_sha256_12: str | None = None) -> dict[str, Any]:
    """Restore a workspace from a saved backup file."""
    path = _backup_path(filename)
    _validate_backup_fingerprint(path, expected_sha256_12)
    payload = json.loads(path.read_text())
    if not isinstance(payload, Mapping):
        raise ValueError("Workspace backup must be a JSON object")
    restored = import_workspace_snapshot(payload)
    restored["restored_from_backup"] = _backup_metadata(path)
    return restored


def export_workspace_backup(filename: str) -> dict[str, str]:
    """Return a saved workspace backup as a downloadable JSON file."""
    path = _backup_path(filename)
    return {
        "filename": path.name,
        "content_type": "application/json; charset=utf-8",
        "body": path.read_text(),
    }


def delete_workspace_backup(filename: str, *, expected_sha256_12: str | None = None) -> dict[str, Any]:
    """Delete a saved workspace backup file after optional fingerprint validation."""
    path = _backup_path(filename)
    _validate_backup_fingerprint(path, expected_sha256_12)
    metadata = _backup_metadata(path) or {
        "filename": path.name,
        "path": _display_path(path),
        "size_bytes": path.stat().st_size,
        "sha256_12": _sha256_prefix(path),
    }
    path.unlink()
    return {
        "deleted": True,
        "backup": metadata,
    }


def preview_workspace_backup_restore(filename: str) -> dict[str, Any]:
    """Return restore impact for a saved workspace backup without mutating storage."""
    path = _backup_path(filename)
    payload = json.loads(path.read_text())
    if not isinstance(payload, Mapping):
        raise ValueError("Workspace backup must be a JSON object")
    preview = preview_workspace_import(payload)
    preview["backup"] = _backup_metadata(path)
    return preview


def preview_workspace_import(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return the import impact for a workspace snapshot without mutating storage."""
    normalized = _normalize_snapshot_payload(snapshot)
    profile_name = normalized["profile"]
    preferences_payload = normalized["preferences"]
    current_preferences, recovery_errors = _safe_current_preferences()
    journal_preview, journal_error = _safe_preview_journal(profile_name, snapshot.get("journal"), "journal" in snapshot)
    if journal_error:
        recovery_errors.append(journal_error)
    review_preview, review_error = _safe_preview_review_queue(profile_name, normalized["review_items"])
    if review_error:
        recovery_errors.append(review_error)
    return {
        "schema_version": SCHEMA_VERSION,
        "previewed_at": _now(),
        "profile": profile_name,
        "requires_confirmation": True,
        "preferences": _preview_preferences(current_preferences, preferences_payload, profile_name),
        "journal": journal_preview,
        "review": review_preview,
        "recovery": {
            "quarantine_required": bool(recovery_errors),
            "current_store_errors": recovery_errors,
        },
    }


def build_workspace_snapshot(
    profile: str | None = None,
    *,
    risk: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a shareable workspace snapshot from persisted local state."""
    preferences = workspace_store.get_preferences()
    profile_name = data_provider.normalize_profile(profile or str(preferences.get("profile") or ""))
    risk_settings = _merged_risk_settings(preferences, risk)
    preferences_snapshot = {
        **preferences,
        "profile": profile_name,
        "risk": risk_settings,
    }
    review_queue = review_store.get_review_queue(profile_name)
    review_activity = review_store.get_review_activity(profile_name)
    review_snapshot = {
        **review_queue,
        "activity": review_activity.get("activity", []),
        "activity_limit": review_activity.get("limit"),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": _now(),
        "profile": profile_name,
        "research_disclosure": research_disclosure(),
        "preferences": preferences_snapshot,
        "journal": session_journal.get_journal_entries(profile_name),
        "review": review_snapshot,
        "review_summary": review_store.get_review_summary(profile_name, risk=risk_settings),
        "provenance": data_provider.get_data_provenance(profile_name),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _normalize_snapshot_payload(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        raise ValueError("Workspace snapshot must be a JSON object")
    schema_version = snapshot.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported workspace snapshot schema: {schema_version}")

    preferences_payload = _mapping(snapshot.get("preferences"))
    review_payload = _mapping(snapshot.get("review"))
    profile_name = data_provider.normalize_profile(
        str(snapshot.get("profile") or preferences_payload.get("profile") or review_payload.get("profile") or "")
    )
    review_items = review_payload.get("items")
    if not isinstance(review_items, list):
        raise ValueError("Workspace snapshot review.items must be a JSON array")
    has_journal = "journal" in snapshot
    journal_payload = snapshot.get("journal") if has_journal else None
    if has_journal:
        _validate_journal_payload(journal_payload)
    return {
        "profile": profile_name,
        "preferences": preferences_payload,
        "review_items": review_items,
        "has_journal": has_journal,
        "journal": journal_payload,
    }


def _validate_journal_payload(journal_payload: Any) -> None:
    raw_entries = journal_payload.get("entries", []) if isinstance(journal_payload, Mapping) else journal_payload
    if not isinstance(raw_entries, list):
        raise ValueError("Workspace snapshot journal.entries must be a JSON array")


def _preview_preferences(
    current_preferences: Mapping[str, Any],
    preferences_payload: Mapping[str, Any],
    profile_name: str,
) -> dict[str, Any]:
    screener_views = preferences_payload.get("screener_views")
    review_views = preferences_payload.get("review_views")
    risk_payload = preferences_payload.get("risk")
    return {
        "will_replace": True,
        "current_profile": data_provider.normalize_profile(str(current_preferences.get("profile") or "")),
        "incoming_profile": profile_name,
        "incoming_screener_view_count": len(screener_views) if isinstance(screener_views, list) else 0,
        "incoming_review_view_count": len(review_views) if isinstance(review_views, list) else 0,
        "incoming_risk_keys": sorted(str(key) for key in risk_payload.keys()) if isinstance(risk_payload, Mapping) else [],
    }


def _preview_journal(profile_name: str, journal_payload: Any) -> dict[str, Any]:
    raw_entries = journal_payload.get("entries", []) if isinstance(journal_payload, Mapping) else journal_payload
    _validate_journal_payload(journal_payload)
    current_entries = session_journal.get_journal_entries(profile_name).get("entries", [])
    incoming_count = sum(1 for item in raw_entries if isinstance(item, Mapping))
    return {
        "will_replace": True,
        "existing_count": len(current_entries) if isinstance(current_entries, list) else 0,
        "incoming_count": incoming_count,
        "removed_count": max(0, (len(current_entries) if isinstance(current_entries, list) else 0) - incoming_count),
    }


def _safe_current_preferences() -> tuple[Mapping[str, Any], list[dict[str, str]]]:
    try:
        return workspace_store.get_preferences(), []
    except ValueError as exc:
        return {}, [_store_error("preferences", workspace_store.STORE_PATH, str(exc))]


def _safe_preview_review_queue(profile_name: str, review_items: list[Any]) -> tuple[dict[str, Any], dict[str, str] | None]:
    try:
        return review_store.preview_replace_review_queue(profile_name, review_items), None
    except ValueError as exc:
        incoming_tickers = _incoming_review_tickers(review_items)
        return (
            {
                "profile": profile_name,
                "limit": review_store.QUEUE_LIMIT,
                "requested_count": len(review_items),
                "imported_count": len(incoming_tickers),
                "duplicate_count": 0,
                "truncated_count": max(0, len(incoming_tickers) - review_store.QUEUE_LIMIT),
                "existing_count": 0,
                "new_count": len(incoming_tickers),
                "updated_count": 0,
                "removed_count": 0,
                "will_replace": True,
                "current_unavailable": True,
                "current_error": str(exc),
                "incoming_tickers": incoming_tickers[:12],
                "new_tickers": incoming_tickers[:12],
                "updated_tickers": [],
                "removed_tickers": [],
            },
            _store_error("review queue", review_store.STORE_PATH, str(exc)),
        )


def _safe_preview_journal(
    profile_name: str,
    journal_payload: Any,
    has_journal: bool,
) -> tuple[dict[str, Any], dict[str, str] | None]:
    if not has_journal:
        return {"will_replace": False}, None
    try:
        return _preview_journal(profile_name, journal_payload), None
    except ValueError as exc:
        raw_entries = journal_payload.get("entries", []) if isinstance(journal_payload, Mapping) else journal_payload
        incoming_count = sum(1 for item in raw_entries if isinstance(item, Mapping)) if isinstance(raw_entries, list) else 0
        return (
            {
                "will_replace": True,
                "existing_count": 0,
                "incoming_count": incoming_count,
                "removed_count": 0,
                "current_unavailable": True,
                "current_error": str(exc),
            },
            _store_error("session journal", session_journal.STORE_PATH, str(exc)),
        )


def _incoming_review_tickers(items: list[Any]) -> list[str]:
    tickers: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
        if len(tickers) >= review_store.QUEUE_LIMIT:
            break
    return tickers


def _build_raw_store_recovery_snapshot(profile_name: str, reason: str, *, exported_at: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": exported_at,
        "profile": profile_name,
        "research_disclosure": research_disclosure(),
        "preferences": {"profile": profile_name},
        "journal": {"profile": profile_name, "entries": []},
        "review": {"profile": profile_name, "items": [], "activity": [], "activity_limit": review_store.ACTIVITY_LIMIT},
        "review_summary": {},
        "provenance": {},
        "recovery_only": True,
        "backup_recovery": {
            "reason": reason,
            "stores": _raw_workspace_store_backup(),
        },
    }


def _raw_workspace_store_backup() -> list[dict[str, Any]]:
    stores: list[dict[str, Any]] = []
    for label, path, _validator in _workspace_store_definitions():
        record: dict[str, Any] = {"label": label, "path": _display_path(path), "exists": path.exists()}
        if path.exists() and path.is_file():
            try:
                content = path.read_text()
                record["content"] = content
                record["sha256_12"] = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
            except (OSError, UnicodeDecodeError) as exc:
                record["error"] = str(exc)
        elif path.exists():
            record["error"] = "store path is not a file"
        stores.append(record)
    return stores


def _quarantine_unreadable_workspace_stores() -> list[dict[str, str]]:
    quarantined: list[dict[str, str]] = []
    for label, path, validator in _workspace_store_definitions():
        error = validator(path)
        if not error:
            continue
        if path.exists() and not path.is_file():
            raise ValueError(f"{label} store path is not a file")
        if not path.exists():
            continue
        quarantine_path = _quarantine_path(path)
        path.replace(quarantine_path)
        quarantined.append(
            {
                "label": label,
                "path": _display_path(path),
                "quarantine_path": _display_path(quarantine_path),
                "reason": error,
            }
        )
    return quarantined


def _workspace_store_definitions() -> tuple[tuple[str, Path, Any], ...]:
    return (
        ("preferences", workspace_store.STORE_PATH, _validate_preferences_store),
        ("review queue", review_store.STORE_PATH, _validate_profile_store),
        ("session journal", session_journal.STORE_PATH, _validate_profile_store),
    )


def _validate_preferences_store(path: Path) -> str:
    return _validate_json_store(path)


def _validate_profile_store(path: Path) -> str:
    error = _validate_json_store(path)
    if error:
        return error
    if not path.exists() or path.stat().st_size == 0:
        return ""
    payload = json.loads(path.read_text())
    profiles = payload.get("profiles") if isinstance(payload, Mapping) else None
    if profiles is not None and not isinstance(profiles, dict):
        return "profiles must be a JSON object"
    return ""


def _validate_json_store(path: Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        return ""
    if not path.is_file():
        return "store path is not a file"
    try:
        payload = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError) as exc:
        return str(exc)
    except json.JSONDecodeError:
        return "store is not valid JSON"
    if not isinstance(payload, dict):
        return "store root must be a JSON object"
    return ""


def _quarantine_path(path: Path) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = path.with_name(f"{path.stem}.corrupt-{stamp}{path.suffix}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}.corrupt-{stamp}-{counter}{path.suffix}")
        counter += 1
    return candidate


def _store_error(label: str, path: Path, error: str) -> dict[str, str]:
    return {
        "label": label,
        "path": _display_path(path),
        "error": error,
    }


def _merged_risk_settings(
    preferences: Mapping[str, Any],
    risk: Mapping[str, Any] | None,
) -> dict[str, float | None]:
    preference_risk = preferences.get("risk") if isinstance(preferences.get("risk"), Mapping) else {}
    merged = {
        "account_equity": _non_negative_float(preference_risk.get("account_equity")),
        "risk_pct": _non_negative_float(preference_risk.get("risk_pct")),
        "max_capital_pct": _non_negative_float(preference_risk.get("max_capital_pct")),
        "max_queue_risk_pct": _non_negative_float(preference_risk.get("max_queue_risk_pct")),
        "max_open_position_risk_pct": _non_negative_float(preference_risk.get("max_open_position_risk_pct")),
        "max_concentration_pct": _non_negative_float(preference_risk.get("max_concentration_pct")),
        "max_open_concentration_pct": _non_negative_float(preference_risk.get("max_open_concentration_pct")),
    }
    for key in (
        "account_equity",
        "risk_pct",
        "max_capital_pct",
        "max_queue_risk_pct",
        "max_open_position_risk_pct",
        "max_concentration_pct",
        "max_open_concentration_pct",
    ):
        override = _non_negative_float((risk or {}).get(key))
        if override is not None:
            merged[key] = override
    return merged


def _non_negative_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _filename_timestamp(value: str) -> str:
    return (
        value.replace("+00:00", "Z")
        .replace(":", "")
        .replace("-", "")
        .replace(".", "")
    )


def _display_path(path: Any) -> str:
    try:
        return str(path.relative_to(data_provider.PROJECT_ROOT))
    except ValueError:
        return str(path)


def _backup_path(filename: str) -> Any:
    clean_name = str(filename or "").strip()
    if (
        not clean_name
        or "/" in clean_name
        or "\\" in clean_name
        or not clean_name.startswith("canslim-workspace-backup-")
        or not clean_name.endswith(".json")
    ):
        raise ValueError("Invalid workspace backup filename")
    path = (BACKUP_DIR / clean_name).resolve()
    try:
        path.relative_to(BACKUP_DIR.resolve())
    except ValueError as exc:
        raise ValueError("Invalid workspace backup filename") from exc
    if not path.is_file():
        raise FileNotFoundError(f"Workspace backup not found: {clean_name}")
    return path


def _backup_metadata(path: Any) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    profile_name = data_provider.normalize_profile(str(payload.get("profile") or ""))
    review_payload = payload.get("review") if isinstance(payload.get("review"), Mapping) else {}
    journal_payload = payload.get("journal") if isinstance(payload.get("journal"), Mapping) else {}
    review_items = review_payload.get("items") if isinstance(review_payload.get("items"), list) else []
    journal_entries = journal_payload.get("entries") if isinstance(journal_payload.get("entries"), list) else []
    created_at = (
        str(payload.get("backup_created_at") or payload.get("exported_at") or "").strip()
        or dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()
    )
    return {
        "created_at": created_at,
        "profile": profile_name,
        "filename": path.name,
        "path": _display_path(path),
        "size_bytes": path.stat().st_size,
        "sha256_12": _sha256_prefix(path),
        "review_item_count": len(review_items),
        "journal_entry_count": len(journal_entries),
    }


def _sha256_prefix(path: Any) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()[:12]
    except OSError:
        return None


def _validate_backup_fingerprint(path: Any, expected_sha256_12: str | None) -> None:
    expected = str(expected_sha256_12 or "").strip().lower()
    if not expected:
        return
    if len(expected) != 12 or any(char not in "0123456789abcdef" for char in expected):
        raise ValueError("Workspace backup fingerprint must be a 12-character SHA-256 prefix")
    actual = _sha256_prefix(path)
    if actual != expected:
        raise ValueError("Workspace backup fingerprint changed; refresh backups and try again")


def _prune_workspace_backups(profile_name: str) -> None:
    if not BACKUP_DIR.exists():
        return
    matching: list[Any] = []
    for path in BACKUP_DIR.glob("*.json"):
        if not path.is_file() or not path.name.startswith("canslim-workspace-backup-"):
            continue
        metadata = _backup_metadata(path)
        if metadata and metadata["profile"] == profile_name:
            matching.append(path)
    matching.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for path in matching[BACKUP_LIMIT:]:
        try:
            path.unlink()
        except OSError:
            continue
