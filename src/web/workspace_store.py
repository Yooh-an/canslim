"""Persistent workspace preferences for the local web dashboard."""

from __future__ import annotations

import datetime as dt
import json
import math
import threading
from pathlib import Path
from typing import Any, Mapping

from src.web import data_provider
from src.web.atomic_store import write_json_atomic


STORE_PATH = data_provider.PROJECT_ROOT / "data" / "web_workspace" / "preferences.json"
DEFAULT_MIN_SCORE = 70
DEFAULT_SORT_BY = "score"
DEFAULT_SORT_DIR = "desc"
DEFAULT_ACCOUNT_EQUITY = 100_000
DEFAULT_RISK_PCT = 0.5
DEFAULT_MAX_CAPITAL_PCT = 80
DEFAULT_MAX_QUEUE_RISK_PCT = 5
DEFAULT_MAX_OPEN_POSITION_RISK_PCT = 6
DEFAULT_MAX_CONCENTRATION_PCT = 60
DEFAULT_MAX_OPEN_CONCENTRATION_PCT = 60
DEFAULT_REVIEW_SORT_BY = "added_at"
DEFAULT_REVIEW_SORT_DIR = "desc"
DEFAULT_REVIEW_STATUS_FILTER = ""
DEFAULT_REVIEW_PRIORITY_FILTER = ""
DEFAULT_REVIEW_TAG_FILTER = ""
DEFAULT_REVIEW_QUERY = ""
DEFAULT_SCREENER_VIEWS: list[dict[str, Any]] = []
DEFAULT_REVIEW_VIEWS: list[dict[str, Any]] = []
MAX_SCREENER_VIEWS = 12
MAX_REVIEW_VIEWS = 12
ALLOWED_SORT_FIELDS = {"ticker", "name", "score", "setup", "rs", "eps", "revenue", "pivot", "market_cap"}
ALLOWED_SORT_DIRS = {"asc", "desc"}
ALLOWED_REVIEW_SORT_FIELDS = {"added_at", "ticker", "status", "priority", "score", "risk", "capital", "shares"}
ALLOWED_REVIEW_STATUS_FILTERS = {"", "watch", "ready", "pass", "bought", "sold"}
ALLOWED_REVIEW_PRIORITY_FILTERS = {"", "high", "normal", "low"}
ALLOWED_SETUP_FILTERS = {
    "",
    "near_pivot",
    "forming_base",
    "extended",
    "breakout_confirmed",
    "breakout_unconfirmed",
    "below_pivot_not_actionable",
}

_LOCK = threading.RLock()


def get_preferences(*, store_path: Path | None = None) -> dict[str, Any]:
    """Return dashboard workspace preferences."""
    with _LOCK:
        preferences = _load_preferences(_path(store_path))
        return _sanitize_preferences(preferences)


def save_preferences(
    preferences: Mapping[str, Any],
    *,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Persist dashboard workspace preferences."""
    sanitized = _sanitize_preferences(preferences)
    sanitized["updated_at"] = _now()
    with _LOCK:
        path = _path(store_path)
        _load_preferences(path)
        write_json_atomic(path, sanitized)
    return sanitized


def _sanitize_preferences(preferences: Mapping[str, Any] | None) -> dict[str, Any]:
    preferences = preferences or {}
    screener = preferences.get("screener") if isinstance(preferences.get("screener"), Mapping) else {}
    risk = preferences.get("risk") if isinstance(preferences.get("risk"), Mapping) else {}
    review = preferences.get("review") if isinstance(preferences.get("review"), Mapping) else {}
    return {
        "profile": data_provider.normalize_profile(str(preferences.get("profile") or "")),
        "screener": {
            "query": _clean_text(screener.get("query"), max_length=80) or "",
            "min_score": _bounded_number(screener.get("min_score"), default=DEFAULT_MIN_SCORE, low=0, high=100),
            "setup": _clean_setup(screener.get("setup")),
            "sort_by": _clean_sort_by(screener.get("sort_by")),
            "sort_dir": _clean_sort_dir(screener.get("sort_dir")),
        },
        "screener_views": _clean_screener_views(preferences.get("screener_views")),
        "review_views": _clean_review_views(preferences.get("review_views")),
        "review": {
            "query": _clean_text(review.get("query"), max_length=80) or DEFAULT_REVIEW_QUERY,
            "sort_by": _clean_review_sort_by(review.get("sort_by")),
            "sort_dir": _clean_review_sort_dir(review.get("sort_dir")),
            "status": _clean_review_status(review.get("status")),
            "priority": _clean_review_priority(review.get("priority")),
            "tag": _clean_review_tag(review.get("tag")),
        },
        "risk": {
            "account_equity": _bounded_number(
                risk.get("account_equity"),
                default=DEFAULT_ACCOUNT_EQUITY,
                low=0,
                high=1_000_000_000,
            ),
            "risk_pct": _bounded_number(risk.get("risk_pct"), default=DEFAULT_RISK_PCT, low=0, high=5),
            "max_capital_pct": _bounded_number(
                risk.get("max_capital_pct"),
                default=DEFAULT_MAX_CAPITAL_PCT,
                low=0,
                high=100,
            ),
            "max_queue_risk_pct": _bounded_number(
                risk.get("max_queue_risk_pct"),
                default=DEFAULT_MAX_QUEUE_RISK_PCT,
                low=0,
                high=25,
            ),
            "max_open_position_risk_pct": _bounded_number(
                risk.get("max_open_position_risk_pct"),
                default=DEFAULT_MAX_OPEN_POSITION_RISK_PCT,
                low=0,
                high=25,
            ),
            "max_concentration_pct": _bounded_number(
                risk.get("max_concentration_pct"),
                default=DEFAULT_MAX_CONCENTRATION_PCT,
                low=0,
                high=100,
            ),
            "max_open_concentration_pct": _bounded_number(
                risk.get("max_open_concentration_pct"),
                default=DEFAULT_MAX_OPEN_CONCENTRATION_PCT,
                low=0,
                high=100,
            ),
        },
        "updated_at": _clean_text(preferences.get("updated_at"), max_length=40),
    }


def _load_preferences(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        payload = json.loads(path.read_text())
    except OSError as exc:
        raise ValueError("Workspace preferences store could not be read") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Workspace preferences store is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Workspace preferences store root must be a JSON object")
    return payload


def _clean_screener_views(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return list(DEFAULT_SCREENER_VIEWS)
    views: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        name = _clean_text(item.get("name"), max_length=40)
        if not name:
            continue
        view_id = _clean_view_id(item.get("id")) or _view_id_from_name(name, len(views))
        view_id = _dedupe_view_id(view_id, seen_ids)
        seen_ids.add(view_id)
        views.append(
            {
                "id": view_id,
                "name": name,
                "query": _clean_text(item.get("query"), max_length=80) or "",
                "min_score": _bounded_number(
                    item.get("min_score"),
                    default=DEFAULT_MIN_SCORE,
                    low=0,
                    high=100,
                ),
                "setup": _clean_setup(item.get("setup")),
                "sort_by": _clean_sort_by(item.get("sort_by")),
                "sort_dir": _clean_sort_dir(item.get("sort_dir")),
            }
        )
        if len(views) >= MAX_SCREENER_VIEWS:
            break
    return views


def _clean_review_views(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return list(DEFAULT_REVIEW_VIEWS)
    views: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        name = _clean_text(item.get("name"), max_length=40)
        if not name:
            continue
        view_id = _clean_view_id(item.get("id")) or _view_id_from_name(name, len(views))
        view_id = _dedupe_view_id(view_id, seen_ids)
        seen_ids.add(view_id)
        views.append(
            {
                "id": view_id,
                "name": name,
                "query": _clean_text(item.get("query"), max_length=80) or "",
                "sort_by": _clean_review_sort_by(item.get("sort_by")),
                "sort_dir": _clean_review_sort_dir(item.get("sort_dir")),
                "status": _clean_review_status(item.get("status")),
                "priority": _clean_review_priority(item.get("priority")),
                "tag": _clean_review_tag(item.get("tag")),
            }
        )
        if len(views) >= MAX_REVIEW_VIEWS:
            break
    return views


def _clean_view_id(value: Any) -> str | None:
    text = _clean_text(value, max_length=48)
    if not text:
        return None
    safe = "".join(char for char in text if char.isalnum() or char in {"-", "_"})
    return safe[:48] if safe else None


def _view_id_from_name(name: str, index: int) -> str:
    slug = "-".join(name.lower().split())
    safe = "".join(char for char in slug if char.isalnum() or char == "-").strip("-")
    return (safe or f"view-{index + 1}")[:48]


def _dedupe_view_id(view_id: str, seen_ids: set[str]) -> str:
    candidate = view_id
    suffix = 2
    while candidate in seen_ids:
        suffix_text = f"-{suffix}"
        candidate = f"{view_id[: 48 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def _bounded_number(value: Any, *, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return min(high, max(low, number))


def _clean_setup(value: Any) -> str:
    text = _clean_text(value, max_length=60) or ""
    return text if text in ALLOWED_SETUP_FILTERS else ""


def _clean_sort_by(value: Any) -> str:
    text = _clean_text(value, max_length=40) or DEFAULT_SORT_BY
    return text if text in ALLOWED_SORT_FIELDS else DEFAULT_SORT_BY


def _clean_sort_dir(value: Any) -> str:
    text = (_clean_text(value, max_length=10) or DEFAULT_SORT_DIR).lower()
    return text if text in ALLOWED_SORT_DIRS else DEFAULT_SORT_DIR


def _clean_review_sort_by(value: Any) -> str:
    text = _clean_text(value, max_length=40) or DEFAULT_REVIEW_SORT_BY
    return text if text in ALLOWED_REVIEW_SORT_FIELDS else DEFAULT_REVIEW_SORT_BY


def _clean_review_sort_dir(value: Any) -> str:
    text = (_clean_text(value, max_length=10) or DEFAULT_REVIEW_SORT_DIR).lower()
    return text if text in ALLOWED_SORT_DIRS else DEFAULT_REVIEW_SORT_DIR


def _clean_review_status(value: Any) -> str:
    text = (_clean_text(value, max_length=20) or DEFAULT_REVIEW_STATUS_FILTER).lower()
    return text if text in ALLOWED_REVIEW_STATUS_FILTERS else DEFAULT_REVIEW_STATUS_FILTER


def _clean_review_priority(value: Any) -> str:
    text = (_clean_text(value, max_length=20) or DEFAULT_REVIEW_PRIORITY_FILTER).lower()
    return text if text in ALLOWED_REVIEW_PRIORITY_FILTERS else DEFAULT_REVIEW_PRIORITY_FILTER


def _clean_review_tag(value: Any) -> str:
    text = (_clean_text(value, max_length=24) or DEFAULT_REVIEW_TAG_FILTER).lower()
    text = "-".join(text.split())
    safe = "".join(char for char in text if char.isalnum() or char in {"-", "_"}).strip("-_")
    return safe[:24]


def _clean_text(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text[:max_length] if text else None


def _path(store_path: Path | None) -> Path:
    return store_path or STORE_PATH


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
