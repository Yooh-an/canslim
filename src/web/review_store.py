"""Persistent review queue storage for the local web dashboard."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import re
import threading
from pathlib import Path
from typing import Any, Mapping

from src.web import data_provider
from src.web.atomic_store import write_json_atomic
from src.web.disclosure import research_disclosure


STORE_PATH = data_provider.PROJECT_ROOT / "data" / "web_workspace" / "review_queue.json"
QUEUE_LIMIT = 50
ACTIVITY_LIMIT = 120
DEFAULT_MAX_CAPITAL_PCT = 80
DEFAULT_MAX_QUEUE_RISK_PCT = 5
DEFAULT_MAX_OPEN_POSITION_RISK_PCT = 6
DEFAULT_MAX_CONCENTRATION_PCT = 60
DEFAULT_MAX_OPEN_CONCENTRATION_PCT = 60
POSITION_NEAR_STOP_DISTANCE_PCT = 3.0
REVIEW_STALE_DAYS = 5
READY_STALE_DAYS = 2
CONCENTRATION_TOP_LIMIT = 5
DECISION_STATUSES = {"watch", "ready", "pass", "bought", "sold"}
REVIEW_PRIORITIES = {"high", "normal", "low"}
MAX_REVIEW_TAGS = 8
MAX_REVIEW_TAG_LENGTH = 24
INACTIVE_DECISION_STATUSES = {"pass", "sold"}
SUMMARY_STATUS_ORDER = ("ready", "watch", "bought", "sold", "pass")
POSITION_ALERT_STATUSES = (
    "ok",
    "stop_breached",
    "near_stop",
    "missing_current_price",
    "missing_stop_loss",
)
POSITION_ALERT_ATTENTION_ORDER = {
    "stop_breached": 0,
    "near_stop": 1,
    "missing_current_price": 2,
    "missing_stop_loss": 3,
}
REVIEW_CHECK_KEYS = (
    "weekly_chart",
    "daily_chart",
    "volume_confirmed",
    "market_aligned",
    "risk_defined",
)
READINESS_BLOCKER_CHECKLIST = "checklist_incomplete"
READINESS_BLOCKER_SIZING = "missing_position_size"
EXECUTION_BLOCKER_PRICE = "missing_execution_price"
EXECUTION_BLOCKER_SHARES = "missing_execution_shares"
EXIT_BLOCKER_PRICE = "missing_exit_price"
EXIT_BLOCKER_SHARES = "missing_exit_shares"
EXIT_BLOCKER_ENTRY = "missing_execution_price"
EXPORT_FIELDS = [
    "ticker",
    "name",
    "sector",
    "industry",
    "decision_status",
    "review_priority",
    "review_tags",
    "review_note",
    "checklist_complete",
    "checklist_complete_count",
    "checklist_total_count",
    "readiness_status",
    "readiness_blockers",
    "canslim_score",
    "score_band",
    "setup_status",
    "current_price",
    "pivot_price",
    "pivot_distance_pct",
    "buy_zone_low",
    "buy_zone_high",
    "stop_loss_price",
    "profit_target_low",
    "profit_target_high",
    "risk_amount",
    "risk_per_share",
    "planned_shares",
    "planned_capital",
    "execution_status",
    "execution_blockers",
    "execution_price",
    "execution_shares",
    "execution_value",
    "position_last_price",
    "position_pnl",
    "position_pnl_pct",
    "position_r_multiple",
    "stop_distance_pct",
    "position_alert_status",
    "position_alert_reason",
    "position_alert_signature",
    "position_alert_ack_signature",
    "position_alert_acknowledged",
    "position_alert_acknowledged_at",
    "exit_status",
    "exit_blockers",
    "exit_price",
    "exit_shares",
    "exit_value",
    "realized_pnl",
    "realized_pnl_pct",
    "realized_r_multiple",
    "exit_reason",
    "exited_at",
    "executed_at",
    "added_at",
    "updated_at",
]
EXPORT_FORMATS = {"csv", "json", "tradingview", "txt"}
TRADINGVIEW_SUGGESTED_MCP_ACTIONS = [
    "chart_set_symbol",
    "chart_set_timeframe",
    "chart_manage_indicator",
    "capture_screenshot",
    "alert_create",
]
TRADINGVIEW_TRADE_PLAN_FIELDS = [
    "pivot_price",
    "buy_zone_low",
    "buy_zone_high",
    "stop_loss_price",
    "profit_target_low",
    "profit_target_high",
]
TRADINGVIEW_CONTEXT_FIELDS = [
    "canslim_score",
    "score_band",
    "setup_status",
    "current_price",
    "pivot_distance_pct",
    "risk_amount",
    "risk_per_share",
    "planned_shares",
    "planned_capital",
    "execution_price",
    "execution_shares",
    "execution_value",
    "position_last_price",
    "position_pnl",
    "position_pnl_pct",
    "position_r_multiple",
    "stop_distance_pct",
    "position_alert_status",
    "position_alert_reason",
    "position_alert_signature",
    "position_alert_acknowledged",
    "position_alert_acknowledged_at",
    "exit_price",
    "exit_shares",
    "exit_value",
    "realized_pnl",
    "realized_pnl_pct",
    "realized_r_multiple",
    "exit_reason",
    "exited_at",
    "executed_at",
]
CSV_FORMULA_TEXT_FIELDS = {
    "added_at",
    "decision_status",
    "executed_at",
    "execution_blockers",
    "execution_status",
    "exit_blockers",
    "exit_reason",
    "exit_status",
    "exited_at",
    "industry",
    "name",
    "review_note",
    "review_priority",
    "review_tags",
    "readiness_blockers",
    "readiness_status",
    "sector",
    "position_alert_reason",
    "position_alert_signature",
    "position_alert_ack_signature",
    "position_alert_acknowledged_at",
    "position_alert_status",
    "score_band",
    "setup_status",
    "ticker",
    "updated_at",
}

_LOCK = threading.RLock()
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,14}$")
_TEXT_FIELDS = {
    "ticker",
    "name",
    "sector",
    "industry",
    "score_band",
    "setup_status",
    "decision_status",
    "executed_at",
    "exited_at",
    "exit_reason",
    "position_alert_acknowledged_at",
    "position_alert_ack_signature",
    "review_note",
    "review_priority",
    "review_tags",
    "profile",
    "added_at",
    "updated_at",
}
_NUMERIC_FIELDS = {
    "canslim_score",
    "current_price",
    "pivot_price",
    "pivot_distance_pct",
    "buy_zone_low",
    "buy_zone_high",
    "stop_loss_price",
    "profit_target_low",
    "profit_target_high",
    "execution_price",
    "execution_shares",
    "exit_price",
    "exit_shares",
}
_ACTIVITY_FIELDS = {
    "buy_zone_low",
    "canslim_score",
    "decision_status",
    "executed_at",
    "execution_price",
    "execution_shares",
    "exited_at",
    "exit_price",
    "exit_reason",
    "exit_shares",
    "position_alert_acknowledged_at",
    "position_alert_ack_signature",
    "pivot_price",
    "review_checks",
    "review_note",
    "review_priority",
    "review_tags",
    "stop_loss_price",
}


def get_review_queue(profile: str | None = None, *, store_path: Path | None = None) -> dict[str, Any]:
    """Return persisted review queue items for a profile."""
    profile_name = data_provider.normalize_profile(profile)
    with _LOCK:
        store = _load_store(_path(store_path))
        bucket = _profile_bucket(store, profile_name)
        return {
            "profile": profile_name,
            "items": list(bucket.get("items", [])),
            "activity": list(bucket.get("activity", []))[:10],
            "updated_at": bucket.get("updated_at"),
            "limit": QUEUE_LIMIT,
        }


def get_review_activity(profile: str | None = None, *, store_path: Path | None = None) -> dict[str, Any]:
    """Return recent review queue activity for a profile."""
    profile_name = data_provider.normalize_profile(profile)
    with _LOCK:
        store = _load_store(_path(store_path))
        bucket = _profile_bucket(store, profile_name)
        return {
            "profile": profile_name,
            "activity": list(bucket.get("activity", [])),
            "updated_at": bucket.get("updated_at"),
            "limit": ACTIVITY_LIMIT,
        }


def add_review_item(
    profile: str | None,
    item: Mapping[str, Any],
    *,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Add or update one review queue item and return the profile queue."""
    profile_name = data_provider.normalize_profile(profile or str(item.get("profile") or ""))
    sanitized = _sanitize_item(item, profile_name)
    with _LOCK:
        path = _path(store_path)
        store = _load_store(path)
        bucket = _profile_bucket(store, profile_name)
        previous = next(
            (
                row
                for row in bucket.get("items", [])
                if str(row.get("ticker") or "").upper() == sanitized["ticker"]
            ),
            None,
        )
        action = "updated" if previous else "added"
        changed_fields = _changed_fields(previous, sanitized)
        if previous:
            if "added_at" not in item:
                sanitized["added_at"] = previous.get("added_at") or sanitized["added_at"]
            sanitized = {**previous, **sanitized}
        else:
            sanitized = {
                key: value
                for key, value in sanitized.items()
                if key not in _NUMERIC_FIELDS or value is not None
            }
            sanitized.setdefault("decision_status", "watch")
            sanitized.setdefault("review_priority", "normal")

        remaining = [
            row
            for row in bucket.get("items", [])
            if str(row.get("ticker") or "").upper() != sanitized["ticker"]
        ]
        bucket["items"] = [sanitized, *remaining][:QUEUE_LIMIT]
        bucket["updated_at"] = _now()
        if action == "added" or changed_fields:
            _append_activity(bucket, action, sanitized["ticker"], changed_fields=changed_fields)
        _write_store(path, store)
        return get_review_queue(profile_name, store_path=path)


def add_review_items(
    profile: str | None,
    items: list[Any],
    *,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Add or update multiple review queue items in one write."""
    if not isinstance(items, list):
        raise ValueError("Review items must be a JSON array")
    first_item = items[0] if items and isinstance(items[0], Mapping) else {}
    profile_name = data_provider.normalize_profile(profile or str(first_item.get("profile") or ""))
    sanitized_items: list[tuple[dict[str, Any], bool]] = []
    seen_tickers: set[str] = set()
    for item in items[:QUEUE_LIMIT]:
        if not isinstance(item, Mapping):
            raise ValueError("Review item must be a JSON object")
        sanitized = _sanitize_item(item, data_provider.normalize_profile(profile or str(item.get("profile") or "")))
        if sanitized["ticker"] in seen_tickers:
            continue
        seen_tickers.add(sanitized["ticker"])
        sanitized_items.append((sanitized, "added_at" in item))

    with _LOCK:
        path = _path(store_path)
        store = _load_store(path)
        bucket = _profile_bucket(store, profile_name)
        previous_by_ticker = {str(row.get("ticker") or "").upper(): row for row in bucket.get("items", [])}
        merged_items: list[dict[str, Any]] = []
        added_count = 0
        updated_count = 0
        for sanitized, has_added_at in sanitized_items:
            previous = previous_by_ticker.get(sanitized["ticker"])
            if previous:
                if not has_added_at:
                    sanitized["added_at"] = previous.get("added_at") or sanitized["added_at"]
                sanitized = {**previous, **sanitized}
                updated_count += 1
            else:
                sanitized = {
                    key: value
                    for key, value in sanitized.items()
                    if key not in _NUMERIC_FIELDS or value is not None
                }
                sanitized.setdefault("decision_status", "watch")
                sanitized.setdefault("review_priority", "normal")
                added_count += 1
            merged_items.append(sanitized)

        incoming_tickers = {item["ticker"] for item in merged_items}
        remaining = [
            row
            for row in bucket.get("items", [])
            if str(row.get("ticker") or "").upper() not in incoming_tickers
        ]
        bucket["items"] = [*merged_items, *remaining][:QUEUE_LIMIT]
        bucket["updated_at"] = _now()
        if added_count or updated_count:
            _append_activity(bucket, "bulk_added", "", added_count=added_count, updated_count=updated_count)
        _write_store(path, store)
        return get_review_queue(profile_name, store_path=path)


def remove_review_item(
    profile: str | None,
    ticker: str,
    *,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Remove one ticker from a profile queue."""
    profile_name = data_provider.normalize_profile(profile)
    normalized = _normalize_ticker(ticker)
    with _LOCK:
        path = _path(store_path)
        store = _load_store(path)
        bucket = _profile_bucket(store, profile_name)
        previous_count = len(bucket.get("items", []))
        removed_items = [
            row
            for row in bucket.get("items", [])
            if str(row.get("ticker") or "").upper() == normalized
        ]
        bucket["items"] = [
            row for row in bucket.get("items", []) if str(row.get("ticker") or "").upper() != normalized
        ]
        removed = len(bucket.get("items", [])) < previous_count
        bucket["updated_at"] = _now()
        if removed:
            _append_activity(bucket, "removed", normalized, restorable_items=removed_items)
        _write_store(path, store)
        return get_review_queue(profile_name, store_path=path)


def bulk_update_review_items(
    profile: str | None,
    tickers: list[Any],
    patch: Mapping[str, Any],
    *,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Apply supported review edits to multiple existing queue items."""
    profile_name = data_provider.normalize_profile(profile)
    normalized_tickers = _normalize_ticker_list(tickers)
    if not normalized_tickers:
        return get_review_queue(profile_name, store_path=store_path)
    if not isinstance(patch, Mapping):
        raise ValueError("Review action patch must be a JSON object")

    updates: dict[str, Any] = {}
    if "decision_status" in patch:
        updates["decision_status"] = _normalize_decision_status(patch.get("decision_status"))
    if "review_priority" in patch:
        updates["review_priority"] = _normalize_review_priority(patch.get("review_priority"))
    if not updates:
        raise ValueError("Review action must include a supported field")

    with _LOCK:
        path = _path(store_path)
        store = _load_store(path)
        bucket = _profile_bucket(store, profile_name)
        selected = set(normalized_tickers)
        changed_count = 0
        changed_fields: set[str] = set()
        restorable_items: list[dict[str, Any]] = []
        for item in bucket.get("items", []):
            if str(item.get("ticker") or "").upper() not in selected:
                continue
            previous_item = dict(item)
            item_updates = {
                **updates,
                **_status_transition_defaults(item, updates.get("decision_status")),
            }
            changed = False
            for field, value in item_updates.items():
                if item.get(field) != value:
                    item[field] = value
                    changed = True
                    changed_fields.add(field)
            if changed:
                restorable_items.append(previous_item)
                item["updated_at"] = _now()
                changed_count += 1
        if changed_count:
            bucket["updated_at"] = _now()
            _append_activity(
                bucket,
                "bulk_updated",
                "",
                changed_fields=sorted(changed_fields),
                restorable_items=restorable_items,
                status=updates.get("decision_status"),
                updated_count=changed_count,
            )
            _write_store(path, store)
        return get_review_queue(profile_name, store_path=path)


def bulk_tag_review_items(
    profile: str | None,
    tickers: list[Any],
    tags: Any,
    *,
    mode: str = "add",
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Add or replace review tags on multiple existing queue items."""
    profile_name = data_provider.normalize_profile(profile)
    normalized_tickers = _normalize_ticker_list(tickers)
    if not normalized_tickers:
        return get_review_queue(profile_name, store_path=store_path)
    normalized_mode = str(mode or "add").strip().lower()
    if normalized_mode not in {"add", "replace"}:
        raise ValueError("tag mode must be one of: add, replace")
    normalized_tags = _sanitize_review_tags(tags)
    if normalized_mode == "add" and not normalized_tags:
        raise ValueError("review_tags must include at least one tag")

    with _LOCK:
        path = _path(store_path)
        store = _load_store(path)
        bucket = _profile_bucket(store, profile_name)
        selected = set(normalized_tickers)
        changed_count = 0
        restorable_items: list[dict[str, Any]] = []
        for item in bucket.get("items", []):
            if str(item.get("ticker") or "").upper() not in selected:
                continue
            previous_tags = _sanitize_review_tags(item.get("review_tags"))
            next_tags = (
                _sanitize_review_tags([*previous_tags, *normalized_tags])
                if normalized_mode == "add"
                else normalized_tags
            )
            if previous_tags == next_tags:
                continue
            restorable_items.append(dict(item))
            item["review_tags"] = next_tags
            item["updated_at"] = _now()
            changed_count += 1
        if changed_count:
            bucket["updated_at"] = _now()
            _append_activity(
                bucket,
                "bulk_updated",
                "",
                changed_fields=["review_tags"],
                restorable_items=restorable_items,
                updated_count=changed_count,
            )
            _write_store(path, store)
        return get_review_queue(profile_name, store_path=path)


def bulk_update_review_prices(
    profile: str | None,
    prices: Any,
    *,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Update current prices for existing review queue items."""
    profile_name = data_provider.normalize_profile(profile)
    price_updates = _normalize_price_updates(prices)
    if not price_updates:
        raise ValueError("prices must include at least one ticker and current_price")

    with _LOCK:
        path = _path(store_path)
        store = _load_store(path)
        bucket = _profile_bucket(store, profile_name)
        changed_count = 0
        restorable_items: list[dict[str, Any]] = []
        for item in bucket.get("items", []):
            ticker = str(item.get("ticker") or "").upper()
            if ticker not in price_updates:
                continue
            current_price = price_updates[ticker]
            if item.get("current_price") == current_price:
                continue
            restorable_items.append(dict(item))
            item["current_price"] = current_price
            item["updated_at"] = _now()
            changed_count += 1
        if changed_count:
            bucket["updated_at"] = _now()
            _append_activity(
                bucket,
                "bulk_updated",
                "",
                changed_fields=["current_price"],
                restorable_items=restorable_items,
                updated_count=changed_count,
            )
            _write_store(path, store)
        return get_review_queue(profile_name, store_path=path)


def _status_transition_defaults(item: Mapping[str, Any], status: Any) -> dict[str, Any]:
    """Return default execution/exit fields for bulk lifecycle transitions."""
    normalized_status = str(status or "").strip().lower()
    defaults: dict[str, Any] = {}
    if normalized_status == "bought" and not item.get("executed_at"):
        defaults["executed_at"] = _now()[:10]
    if normalized_status == "sold":
        if not item.get("exited_at"):
            defaults["exited_at"] = _now()[:10]
        if _finite_float(item.get("exit_price")) is None:
            current_price = _finite_float(item.get("current_price"))
            if current_price is not None:
                defaults["exit_price"] = current_price
        if _positive_int(item.get("exit_shares")) is None:
            execution_shares = _positive_int(item.get("execution_shares"))
            if execution_shares is not None:
                defaults["exit_shares"] = execution_shares
    return defaults


def bulk_remove_review_items(
    profile: str | None,
    tickers: list[Any],
    *,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Remove multiple selected tickers from a profile queue."""
    profile_name = data_provider.normalize_profile(profile)
    normalized_tickers = _normalize_ticker_list(tickers)
    if not normalized_tickers:
        return get_review_queue(profile_name, store_path=store_path)
    selected = set(normalized_tickers)
    with _LOCK:
        path = _path(store_path)
        store = _load_store(path)
        bucket = _profile_bucket(store, profile_name)
        previous_items = list(bucket.get("items", []))
        bucket["items"] = [
            row for row in previous_items if str(row.get("ticker") or "").upper() not in selected
        ]
        removed_items = [
            row for row in previous_items if str(row.get("ticker") or "").upper() in selected
        ]
        removed_count = len(previous_items) - len(bucket["items"])
        if removed_count:
            bucket["updated_at"] = _now()
            _append_activity(bucket, "bulk_removed", "", removed_count=removed_count, restorable_items=removed_items)
            _write_store(path, store)
        return get_review_queue(profile_name, store_path=path)


def clear_review_queue(profile: str | None = None, *, store_path: Path | None = None) -> dict[str, Any]:
    """Clear all review items for a profile."""
    profile_name = data_provider.normalize_profile(profile)
    with _LOCK:
        path = _path(store_path)
        store = _load_store(path)
        bucket = _profile_bucket(store, profile_name)
        removed_items = list(bucket.get("items", []))
        removed_count = len(removed_items)
        bucket["items"] = []
        bucket["updated_at"] = _now()
        if removed_count:
            _append_activity(bucket, "cleared", "", removed_count=removed_count, restorable_items=removed_items)
        _write_store(path, store)
        return get_review_queue(profile_name, store_path=path)


def restore_review_activity(
    profile: str | None,
    activity_at: str,
    *,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Restore items captured by a recent destructive review activity."""
    profile_name = data_provider.normalize_profile(profile)
    token = _clean_text(activity_at, max_length=60)
    if not token:
        raise ValueError("activity_at is required")
    with _LOCK:
        path = _path(store_path)
        store = _load_store(path)
        bucket = _profile_bucket(store, profile_name)
        activity = bucket.get("activity") if isinstance(bucket.get("activity"), list) else []
        event = next((row for row in activity if str(row.get("at") or "") == token), None)
        if not event:
            raise ValueError("review activity was not found")
        if event.get("restored_at"):
            raise ValueError("review activity was already restored")
        raw_items = event.get("restorable_items")
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError("review activity cannot be restored")

        restored_items = [_restore_item(item, profile_name) for item in raw_items if isinstance(item, Mapping)]
        if not restored_items:
            raise ValueError("review activity cannot be restored")
        restored_tickers = {item["ticker"] for item in restored_items}
        remaining_items = [
            item
            for item in bucket.get("items", [])
            if str(item.get("ticker") or "").upper() not in restored_tickers
        ]
        bucket["items"] = [*restored_items, *remaining_items][:QUEUE_LIMIT]
        now = _now()
        bucket["updated_at"] = now
        event["restored_at"] = now
        event["restored_count"] = len(restored_items)
        _append_activity(
            bucket,
            "restored",
            "",
            restored_count=len(restored_items),
            source_action=str(event.get("action") or ""),
        )
        _write_store(path, store)
        return get_review_queue(profile_name, store_path=path)


def replace_review_queue(
    profile: str | None,
    items: list[Any],
    *,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Replace a profile queue with sanitized imported items."""
    profile_name = data_provider.normalize_profile(profile)
    imported, _stats = _prepare_import_items(profile_name, items)

    with _LOCK:
        path = _path(store_path)
        store = _load_store(path)
        bucket = _profile_bucket(store, profile_name)
        replaced_count = len(bucket.get("items", []))
        bucket["items"] = imported[:QUEUE_LIMIT]
        bucket["updated_at"] = _now()
        _append_activity(
            bucket,
            "imported",
            "",
            imported_count=len(bucket["items"]),
            removed_count=replaced_count,
        )
        _write_store(path, store)
        return get_review_queue(profile_name, store_path=path)


def validate_review_import_items(profile: str | None, items: list[Any]) -> dict[str, Any]:
    """Validate imported review items without reading or mutating the current store."""
    profile_name = data_provider.normalize_profile(profile)
    imported, stats = _prepare_import_items(profile_name, items)
    return {
        "profile": profile_name,
        "limit": QUEUE_LIMIT,
        "requested_count": stats["requested_count"],
        "imported_count": len(imported),
        "duplicate_count": stats["duplicate_count"],
        "truncated_count": stats["truncated_count"],
    }


def preview_replace_review_queue(
    profile: str | None,
    items: list[Any],
    *,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Return the impact of replacing a profile queue without mutating storage."""
    profile_name = data_provider.normalize_profile(profile)
    imported, stats = _prepare_import_items(profile_name, items)
    incoming_tickers = {item["ticker"] for item in imported}
    with _LOCK:
        current = get_review_queue(profile_name, store_path=store_path)
    existing_items = [item for item in current.get("items", []) if isinstance(item, Mapping)]
    existing_tickers = {str(item.get("ticker") or "").upper() for item in existing_items if item.get("ticker")}
    overlapping_tickers = sorted(existing_tickers & incoming_tickers)
    removed_tickers = sorted(existing_tickers - incoming_tickers)
    new_tickers = sorted(incoming_tickers - existing_tickers)
    return {
        "profile": profile_name,
        "limit": QUEUE_LIMIT,
        "requested_count": stats["requested_count"],
        "imported_count": len(imported),
        "duplicate_count": stats["duplicate_count"],
        "truncated_count": stats["truncated_count"],
        "existing_count": len(existing_items),
        "new_count": len(new_tickers),
        "updated_count": len(overlapping_tickers),
        "removed_count": len(removed_tickers),
        "will_replace": True,
        "incoming_tickers": sorted(incoming_tickers)[:12],
        "new_tickers": new_tickers[:12],
        "updated_tickers": overlapping_tickers[:12],
        "removed_tickers": removed_tickers[:12],
    }


def export_review_queue(
    profile: str | None = None,
    export_format: str | None = None,
    *,
    risk: Mapping[str, Any] | None = None,
    filters: Mapping[str, Any] | None = None,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Return a downloadable review queue export."""
    queue = get_review_queue(profile, store_path=store_path)
    export_filters = _normalize_export_filters(filters)
    if export_filters:
        queue = {
            **queue,
            "export_filters": export_filters,
            "items": _filtered_export_items(queue["items"], export_filters),
        }
    normalized_format = _normalize_export_format(export_format)
    extension = "txt" if normalized_format == "txt" else "json" if normalized_format == "tradingview" else normalized_format
    filter_suffix = _export_filter_suffix(export_filters)
    filename = (
        f"canslim-tradingview-review-{queue['profile']}{filter_suffix}.json"
        if normalized_format == "tradingview"
        else f"canslim-review-{queue['profile']}{filter_suffix}.{extension}"
    )
    if normalized_format == "csv":
        body = _queue_to_csv(queue["items"], risk)
        content_type = "text/csv; charset=utf-8"
    elif normalized_format == "json":
        body = _queue_to_json(queue, risk)
        content_type = "application/json; charset=utf-8"
    elif normalized_format == "tradingview":
        body = _queue_to_tradingview_json(queue, risk)
        content_type = "application/json; charset=utf-8"
    else:
        body = _queue_to_ticker_list(queue["items"])
        content_type = "text/plain; charset=utf-8"
    return {
        "profile": queue["profile"],
        "format": normalized_format,
        "filters": export_filters,
        "filename": filename,
        "content_type": content_type,
        "body": body,
    }


def get_review_summary(
    profile: str | None = None,
    *,
    risk: Mapping[str, Any] | None = None,
    store_path: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Return portfolio-level sizing totals for a profile review queue."""
    queue = get_review_queue(profile, store_path=store_path)
    settings = _export_risk_settings(risk)
    rows = [_export_row(item, risk) for item in queue["items"] if isinstance(item, Mapping)]
    current_time = _summary_now(now)
    status_counts = {status: 0 for status in sorted(DECISION_STATUSES)}
    active_rows: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.get("decision_status") or "watch").lower()
        if status not in status_counts:
            status = "watch"
        status_counts[status] += 1
        if status not in INACTIVE_DECISION_STATUSES:
            active_rows.append(row)

    sized_rows = [row for row in active_rows if _positive_int(row.get("planned_shares"))]
    total_risk_amount = round(sum(_finite_float(row.get("risk_amount")) or 0 for row in sized_rows), 2)
    total_planned_capital = round(sum(_finite_float(row.get("planned_capital")) or 0 for row in sized_rows), 2)
    account_equity = settings.get("account_equity")
    max_capital_pct = settings.get("max_capital_pct")
    max_queue_risk_pct = settings.get("max_queue_risk_pct")
    max_open_position_risk_pct = settings.get("max_open_position_risk_pct")
    risk_budget_pct = _percent_of(total_risk_amount, account_equity)
    planned_capital_pct = _percent_of(total_planned_capital, account_equity)
    unsized_items = max(0, len(active_rows) - len(sized_rows))
    bought_rows = [row for row in active_rows if str(row.get("decision_status") or "watch").lower() == "bought"]
    executed_rows = [row for row in bought_rows if row.get("execution_status") == "recorded"]
    total_execution_value = round(sum(_finite_float(row.get("execution_value")) or 0 for row in executed_rows), 2)
    monitored_rows = [row for row in executed_rows if _finite_float(row.get("position_pnl")) is not None]
    total_position_pnl = round(sum(_finite_float(row.get("position_pnl")) or 0 for row in monitored_rows), 2)
    total_position_pnl_pct = _percent_of(total_position_pnl, total_execution_value)
    open_position_risk = _summary_open_position_risk(executed_rows, account_equity)
    open_position_concentration = _summary_open_position_concentration(executed_rows, settings)
    position_alert_counts = _summary_position_alert_counts(executed_rows)
    open_position_alert_counts = _summary_position_alert_counts(executed_rows, acknowledged=False)
    position_alert_items = _summary_position_alert_items(executed_rows, acknowledged=False)
    acknowledged_position_alert_items = _summary_position_alert_items(executed_rows, acknowledged=True)
    acknowledged_position_alerts = sum(1 for row in executed_rows if bool(row.get("position_alert_acknowledged")))
    bought_execution_missing = max(0, len(bought_rows) - len(executed_rows))
    sold_rows = [row for row in rows if str(row.get("decision_status") or "watch").lower() == "sold"]
    realized_rows = [row for row in sold_rows if row.get("exit_status") == "recorded"]
    sold_exit_missing = max(0, len(sold_rows) - len(realized_rows))
    total_exit_value = round(sum(_finite_float(row.get("exit_value")) or 0 for row in realized_rows), 2)
    total_realized_pnl = round(sum(_finite_float(row.get("realized_pnl")) or 0 for row in realized_rows), 2)
    total_entry_value_for_exits = round(sum(_exit_entry_value(row) or 0 for row in realized_rows), 2)
    total_realized_pnl_pct = _percent_of(total_realized_pnl, total_entry_value_for_exits)
    realized_performance = _summary_realized_performance(realized_rows)
    checklist_complete_items = sum(1 for row in active_rows if bool(row.get("checklist_complete")))
    checklist_incomplete_items = max(0, len(active_rows) - checklist_complete_items)
    ready_checklist_blockers = sum(
        1
        for row in active_rows
        if str(row.get("decision_status") or "watch").lower() == "ready" and not bool(row.get("checklist_complete"))
    )
    readiness_blocker_counts = _summary_readiness_blocker_counts(active_rows)
    readiness_blocker_items = _summary_readiness_blocker_items(active_rows)
    aging = _summary_review_aging(active_rows, current_time)
    concentration = _summary_concentration(active_rows, settings)
    warnings = _summary_warnings(
        unsized_items,
        ready_checklist_blockers,
        bought_execution_missing,
        sold_exit_missing,
        open_position_alert_counts,
        aging.get("stale_active_count", 0),
        aging.get("stale_ready_count", 0),
        concentration.get("warnings", []) + open_position_concentration.get("warnings", []),
        planned_capital_pct,
        risk_budget_pct,
        open_position_risk.get("stop_risk_pct"),
        max_capital_pct,
        max_queue_risk_pct,
        max_open_position_risk_pct,
    )
    risk_actions = _summary_risk_actions(
        unsized_items=unsized_items,
        ready_checklist_blockers=ready_checklist_blockers,
        bought_execution_missing=bought_execution_missing,
        sold_exit_missing=sold_exit_missing,
        position_alert_items=position_alert_items,
        aging=aging,
        concentration=concentration,
        open_position_concentration=open_position_concentration,
        planned_capital_pct=planned_capital_pct,
        risk_budget_pct=risk_budget_pct,
        open_position_risk_pct=open_position_risk.get("stop_risk_pct"),
        max_capital_pct=max_capital_pct,
        max_queue_risk_pct=max_queue_risk_pct,
        max_open_position_risk_pct=max_open_position_risk_pct,
    )
    return {
        "profile": queue["profile"],
        "updated_at": queue.get("updated_at"),
        "risk": settings,
        "total_items": len(rows),
        "active_items": len(active_rows),
        "sized_items": len(sized_rows),
        "unsized_items": unsized_items,
        "executed_items": len(executed_rows),
        "monitored_positions": len(monitored_rows),
        "bought_execution_missing": bought_execution_missing,
        "sold_exit_missing": sold_exit_missing,
        "total_execution_value": total_execution_value,
        "total_position_pnl": total_position_pnl,
        "total_position_pnl_pct": total_position_pnl_pct,
        "open_position_risk": open_position_risk,
        "open_position_concentration": open_position_concentration,
        "closed_items": len(sold_rows),
        "realized_items": len(realized_rows),
        "total_exit_value": total_exit_value,
        "total_realized_pnl": total_realized_pnl,
        "total_realized_pnl_pct": total_realized_pnl_pct,
        "realized_performance": realized_performance,
        "position_alert_distance_pct": POSITION_NEAR_STOP_DISTANCE_PCT,
        "position_alert_counts": position_alert_counts,
        "open_position_alert_counts": open_position_alert_counts,
        "position_alert_items": position_alert_items,
        "open_position_alerts": len(position_alert_items),
        "acknowledged_position_alerts": acknowledged_position_alerts,
        "acknowledged_position_alert_items": acknowledged_position_alert_items,
        "checklist_complete_items": checklist_complete_items,
        "checklist_incomplete_items": checklist_incomplete_items,
        "ready_checklist_blockers": ready_checklist_blockers,
        "readiness_blocker_counts": readiness_blocker_counts,
        "readiness_blocker_items": readiness_blocker_items,
        "aging": aging,
        "concentration": concentration,
        "status_counts": status_counts,
        "total_risk_amount": total_risk_amount,
        "total_planned_capital": total_planned_capital,
        "risk_budget_pct": risk_budget_pct,
        "planned_capital_pct": planned_capital_pct,
        "status_breakdown": _summary_status_breakdown(rows, settings),
        "largest_positions": _summary_largest_positions(sized_rows),
        "risk_actions": risk_actions,
        "warnings": warnings,
    }


def _sanitize_item(item: Mapping[str, Any], profile: str) -> dict[str, Any]:
    ticker = _normalize_ticker(str(item.get("ticker") or ""))
    now = _now()
    sanitized: dict[str, Any] = {
        "ticker": ticker,
        "profile": profile,
        "added_at": _clean_text(item.get("added_at"), max_length=40) or now,
        "updated_at": now,
    }
    for field in _TEXT_FIELDS - {
        "ticker",
        "profile",
        "added_at",
        "updated_at",
        "decision_status",
        "review_priority",
        "review_note",
        "review_tags",
        "executed_at",
    }:
        value = _clean_text(item.get(field), max_length=120)
        if value:
            sanitized[field] = value
    if "decision_status" in item:
        sanitized["decision_status"] = _normalize_decision_status(item.get("decision_status"))
    if "review_priority" in item:
        sanitized["review_priority"] = _normalize_review_priority(item.get("review_priority"))
    if "review_note" in item:
        sanitized["review_note"] = _clean_text(item.get("review_note"), max_length=800) or ""
    if "review_tags" in item:
        sanitized["review_tags"] = _sanitize_review_tags(item.get("review_tags"))
    if "executed_at" in item:
        sanitized["executed_at"] = _clean_text(item.get("executed_at"), max_length=40) or ""
    if "exited_at" in item:
        sanitized["exited_at"] = _clean_text(item.get("exited_at"), max_length=40) or ""
    if "position_alert_ack_signature" in item:
        sanitized["position_alert_ack_signature"] = _clean_text(
            item.get("position_alert_ack_signature"), max_length=120
        ) or ""
    if "position_alert_acknowledged_at" in item:
        sanitized["position_alert_acknowledged_at"] = _clean_text(
            item.get("position_alert_acknowledged_at"), max_length=40
        ) or ""
    if "exit_reason" in item:
        sanitized["exit_reason"] = _clean_text(item.get("exit_reason"), max_length=120) or ""
    if "review_checks" in item:
        sanitized["review_checks"] = _sanitize_review_checks(item.get("review_checks"))
    for field in _NUMERIC_FIELDS:
        if field not in item:
            continue
        value = _positive_int(item.get(field)) if field == "execution_shares" else _finite_float(item.get(field))
        sanitized[field] = value
    return sanitized


def _sanitize_review_checks(value: Any) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {key: False for key in REVIEW_CHECK_KEYS}
    return {key: bool(value.get(key)) for key in REVIEW_CHECK_KEYS}


def _sanitize_review_tags(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        source = [tag for tag in re.split(r"[,;\n|]+", value) if tag.strip()]
    elif isinstance(value, list):
        source = value
    else:
        return []
    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in source:
        text = _clean_text(raw_tag, max_length=MAX_REVIEW_TAG_LENGTH)
        if not text:
            continue
        slug = re.sub(r"\s+", "-", text.lower())
        slug = re.sub(r"[^a-z0-9_-]", "", slug).strip("-_")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        tags.append(slug[:MAX_REVIEW_TAG_LENGTH])
        if len(tags) >= MAX_REVIEW_TAGS:
            break
    return tags


def _review_check_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    checks = _sanitize_review_checks(item.get("review_checks"))
    complete_count = sum(1 for value in checks.values() if value)
    total_count = len(REVIEW_CHECK_KEYS)
    return {
        "review_checks": checks,
        "checklist_complete": complete_count == total_count,
        "checklist_complete_count": complete_count,
        "checklist_total_count": total_count,
    }


def _restore_item(item: Mapping[str, Any], profile: str) -> dict[str, Any]:
    restored = _sanitize_item(item, profile)
    updated_at = _clean_text(item.get("updated_at"), max_length=40)
    if updated_at:
        restored["updated_at"] = updated_at
    return restored


def _prepare_import_items(profile_name: str, items: list[Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not isinstance(items, list):
        raise ValueError("Review items must be a JSON array")
    imported: list[dict[str, Any]] = []
    seen_tickers: set[str] = set()
    duplicate_count = 0
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("Review item must be a JSON object")
        sanitized = _sanitize_item(item, profile_name)
        if sanitized["ticker"] in seen_tickers:
            duplicate_count += 1
            continue
        seen_tickers.add(sanitized["ticker"])
        sanitized = {
            key: value
            for key, value in sanitized.items()
            if key not in _NUMERIC_FIELDS or value is not None
        }
        sanitized.setdefault("decision_status", "watch")
        sanitized.setdefault("review_priority", "normal")
        imported.append(sanitized)
    truncated_count = max(0, len(imported) - QUEUE_LIMIT)
    return imported[:QUEUE_LIMIT], {
        "requested_count": len(items),
        "duplicate_count": duplicate_count,
        "truncated_count": truncated_count,
    }


def _changed_fields(previous: Mapping[str, Any] | None, current: Mapping[str, Any]) -> list[str]:
    if not previous:
        return []
    changed: list[str] = []
    for field in sorted(_ACTIVITY_FIELDS):
        if field not in current:
            continue
        if previous.get(field) != current.get(field):
            changed.append(field)
    return changed


def _append_activity(
    bucket: dict[str, Any],
    action: str,
    ticker: str,
    *,
    changed_fields: list[str] | None = None,
    added_count: int | None = None,
    imported_count: int | None = None,
    removed_count: int | None = None,
    restorable_items: list[Mapping[str, Any]] | None = None,
    restored_count: int | None = None,
    source_action: str | None = None,
    status: str | None = None,
    updated_count: int | None = None,
) -> None:
    activity = bucket.setdefault("activity", [])
    if not isinstance(activity, list):
        activity = []
        bucket["activity"] = activity
    event: dict[str, Any] = {
        "action": action,
        "at": _now(),
    }
    normalized_ticker = str(ticker or "").upper()
    if normalized_ticker:
        event["ticker"] = normalized_ticker
    if changed_fields:
        event["changed_fields"] = changed_fields[:12]
    if added_count is not None:
        event["added_count"] = added_count
    if imported_count is not None:
        event["imported_count"] = imported_count
    if removed_count is not None:
        event["removed_count"] = removed_count
    if restorable_items:
        event["restorable_items"] = [dict(item) for item in restorable_items[:QUEUE_LIMIT]]
    if restored_count is not None:
        event["restored_count"] = restored_count
    if source_action:
        event["source_action"] = source_action
    if status:
        event["status"] = status
    if updated_count is not None:
        event["updated_count"] = updated_count
    activity.insert(0, event)
    del activity[ACTIVITY_LIMIT:]


def _normalize_export_format(value: str | None) -> str:
    normalized = str(value or "csv").strip().lower()
    if normalized in {"tickers", "ticker", "text"}:
        normalized = "txt"
    if normalized in {"tv", "tradingview-plan", "tradingview_review_plan"}:
        normalized = "tradingview"
    if normalized not in EXPORT_FORMATS:
        raise ValueError("format must be one of: csv, json, tradingview, txt")
    return normalized


def _normalize_export_filters(filters: Mapping[str, Any] | None) -> dict[str, Any]:
    filters = filters or {}
    normalized: dict[str, Any] = {}
    status = str(filters.get("status") or "").strip().lower()
    priority = str(filters.get("priority") or "").strip().lower()
    query = _clean_text(filters.get("query") or filters.get("q"), max_length=80) or ""
    tag = (_sanitize_review_tags(filters.get("tag") or filters.get("review_tag")) or [""])[0]
    tickers = _normalize_export_tickers(filters.get("tickers"))
    if status:
        if status not in DECISION_STATUSES:
            raise ValueError("status filter must be one of: watch, ready, pass, bought, sold")
        normalized["status"] = status
    if priority:
        if priority not in REVIEW_PRIORITIES:
            raise ValueError("priority filter must be one of: high, normal, low")
        normalized["priority"] = priority
    if query:
        normalized["query"] = query
    if tag:
        normalized["tag"] = tag
    if tickers:
        normalized["tickers"] = tickers
    return normalized


def _normalize_export_tickers(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        source = [ticker for ticker in re.split(r"[\s,;|]+", value) if ticker.strip()]
    elif isinstance(value, list):
        source = value
    else:
        raise ValueError("tickers filter must be a string or JSON array")
    return _normalize_ticker_list(source)


def _filtered_export_items(items: list[Mapping[str, Any]], filters: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    status = filters.get("status")
    priority = filters.get("priority")
    query = str(filters.get("query") or "").casefold()
    tag = str(filters.get("tag") or "").casefold()
    tickers = set(filters.get("tickers") or [])
    return [
        item
        for item in items
        if (not status or str(item.get("decision_status") or "watch").strip().lower() == status)
        and (not priority or str(item.get("review_priority") or "normal").strip().lower() == priority)
        and (not query or _export_item_matches_query(item, query))
        and (not tag or tag in {value.casefold() for value in _sanitize_review_tags(item.get("review_tags"))})
        and (not tickers or str(item.get("ticker") or "").strip().upper() in tickers)
    ]


def _export_item_matches_query(item: Mapping[str, Any], query: str) -> bool:
    haystack = " ".join(
        [
            str(item.get("ticker") or ""),
            str(item.get("name") or ""),
            str(item.get("review_note") or ""),
            " ".join(_sanitize_review_tags(item.get("review_tags"))),
        ]
    ).casefold()
    return query in haystack


def _export_filter_suffix(filters: Mapping[str, Any]) -> str:
    parts = [filters[key] for key in ("status", "priority") if filters.get(key)]
    if filters.get("tag"):
        parts.append(str(filters["tag"]))
    if filters.get("query"):
        parts.append("search")
    if filters.get("tickers"):
        parts.append("selected")
    return f"-{'-'.join(parts)}" if parts else ""


def _queue_to_csv(items: list[Mapping[str, Any]], risk: Mapping[str, Any] | None) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for item in items:
        writer.writerow(_csv_safe_row(_export_row(item, risk)))
    return buffer.getvalue()


def _queue_to_json(queue: Mapping[str, Any], risk: Mapping[str, Any] | None) -> str:
    payload = {
        "profile": queue.get("profile"),
        "exported_at": _now(),
        "research_disclosure": research_disclosure(),
        "risk": _export_risk_settings(risk),
        "filters": dict(queue.get("export_filters") or {}),
        "activity": queue.get("activity", []),
        "items": [_export_row(item, risk) for item in queue.get("items", []) if isinstance(item, Mapping)],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _queue_to_tradingview_json(queue: Mapping[str, Any], risk: Mapping[str, Any] | None) -> str:
    rows = [_export_row(item, risk) for item in queue.get("items", []) if isinstance(item, Mapping)]
    symbols = [str(row.get("ticker") or "").upper() for row in rows if row.get("ticker")]
    payload = {
        "generated_at": _now(),
        "profile": queue.get("profile"),
        "source": "web_review_queue",
        "research_disclosure": research_disclosure(),
        "candidate_count": len(rows),
        "symbols": symbols,
        "risk": _export_risk_settings(risk),
        "filters": dict(queue.get("export_filters") or {}),
        "workflow": [
            "Import or add symbols to a TradingView watchlist.",
            "Open each symbol on daily and weekly charts.",
            "Check price action around pivot, buy-zone, stop, and target levels.",
            "Capture chart screenshots before changing decision_status to ready or bought.",
            "Create alerts from alert_plan entries while the setup remains valid.",
        ],
        "candidates": [_tradingview_candidate(row) for row in rows],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _queue_to_ticker_list(items: list[Mapping[str, Any]]) -> str:
    tickers = [str(item.get("ticker") or "").strip().upper() for item in items]
    body = "\n".join(ticker for ticker in tickers if ticker)
    return f"{body}\n" if body else ""


def _tradingview_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").upper()
    decision_status = str(row.get("decision_status") or "watch").lower()
    readiness_status = str(row.get("readiness_status") or "pending").lower()
    trade_plan = {
        field: row.get(field)
        for field in TRADINGVIEW_TRADE_PLAN_FIELDS
        if _has_export_value(row.get(field))
    }
    context = {
        field: row.get(field)
        for field in TRADINGVIEW_CONTEXT_FIELDS
        if _has_export_value(row.get(field))
    }
    candidate = {
        "ticker": ticker,
        "name": row.get("name") or "",
        "sector": row.get("sector") or "",
        "industry": row.get("industry") or "",
        "tradingview_symbol": ticker,
        "decision_status": decision_status,
        "review_priority": row.get("review_priority") or "normal",
        "review_tags": _sanitize_review_tags(row.get("review_tags")),
        "review_note": row.get("review_note") or "",
        "review_checklist": row.get("review_checks") or {},
        "checklist_complete": bool(row.get("checklist_complete")),
        "trade_readiness": {
            "status": readiness_status,
            "blockers": _readiness_blockers(row),
        },
        "execution": _tradingview_execution(row),
        **context,
        "trade_plan": trade_plan,
        "suggested_mcp_actions": list(TRADINGVIEW_SUGGESTED_MCP_ACTIONS),
        "alert_plan": [] if decision_status == "pass" else _tradingview_alert_plan(ticker, trade_plan),
    }
    return candidate


def _tradingview_alert_plan(ticker: str, trade_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    alerts = []
    for level_name in TRADINGVIEW_TRADE_PLAN_FIELDS:
        price = trade_plan.get(level_name)
        if not _has_export_value(price):
            continue
        alerts.append(
            {
                "tool": "alert_create",
                "symbol": ticker,
                "level_name": level_name,
                "price": price,
                "message": f"{ticker} {level_name} {price}",
            }
        )
    return alerts


def _tradingview_execution(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": row.get("execution_status") or "not_applicable",
        "blockers": _execution_blockers(row),
        "price": row.get("execution_price") if _has_export_value(row.get("execution_price")) else None,
        "shares": row.get("execution_shares") if _has_export_value(row.get("execution_shares")) else None,
        "value": row.get("execution_value") if _has_export_value(row.get("execution_value")) else None,
        "last_price": row.get("position_last_price") if _has_export_value(row.get("position_last_price")) else None,
        "pnl": row.get("position_pnl") if _has_export_value(row.get("position_pnl")) else None,
        "pnl_pct": row.get("position_pnl_pct") if _has_export_value(row.get("position_pnl_pct")) else None,
        "r_multiple": row.get("position_r_multiple") if _has_export_value(row.get("position_r_multiple")) else None,
        "stop_distance_pct": row.get("stop_distance_pct") if _has_export_value(row.get("stop_distance_pct")) else None,
        "alert_status": row.get("position_alert_status") or "",
        "alert_reason": row.get("position_alert_reason") or "",
        "alert_signature": row.get("position_alert_signature") or "",
        "alert_acknowledged": bool(row.get("position_alert_acknowledged")),
        "alert_acknowledged_at": row.get("position_alert_acknowledged_at") or "",
        "executed_at": row.get("executed_at") or "",
        "exit": _tradingview_exit(row),
    }


def _tradingview_exit(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": row.get("exit_status") or "not_applicable",
        "blockers": _exit_blockers(row),
        "price": row.get("exit_price") if _has_export_value(row.get("exit_price")) else None,
        "shares": row.get("exit_shares") if _has_export_value(row.get("exit_shares")) else None,
        "value": row.get("exit_value") if _has_export_value(row.get("exit_value")) else None,
        "realized_pnl": row.get("realized_pnl") if _has_export_value(row.get("realized_pnl")) else None,
        "realized_pnl_pct": row.get("realized_pnl_pct") if _has_export_value(row.get("realized_pnl_pct")) else None,
        "realized_r_multiple": row.get("realized_r_multiple") if _has_export_value(row.get("realized_r_multiple")) else None,
        "reason": row.get("exit_reason") or "",
        "exited_at": row.get("exited_at") or "",
    }


def _has_export_value(value: Any) -> bool:
    if value in (None, ""):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return True


def _export_row(item: Mapping[str, Any], risk: Mapping[str, Any] | None) -> dict[str, Any]:
    row = {field: item.get(field, "") for field in EXPORT_FIELDS}
    row["review_tags"] = _sanitize_review_tags(item.get("review_tags"))
    sizing = _position_sizing(item, risk)
    row.update(sizing)
    row.update(_review_check_summary(item))
    row.update(_readiness_summary(row))
    row.update(_execution_summary(row))
    row.update(_position_monitor_summary(row))
    row.update(_exit_summary(row))
    return row


def _readiness_summary(row: Mapping[str, Any]) -> dict[str, str]:
    status = str(row.get("decision_status") or "watch").lower()
    if status in INACTIVE_DECISION_STATUSES:
        return {"readiness_status": "inactive", "readiness_blockers": ""}
    if status == "bought":
        return {"readiness_status": "bought", "readiness_blockers": ""}
    if status != "ready":
        return {"readiness_status": "pending", "readiness_blockers": ""}

    blockers: list[str] = []
    if not bool(row.get("checklist_complete")):
        blockers.append(READINESS_BLOCKER_CHECKLIST)
    if not _positive_int(row.get("planned_shares")):
        blockers.append(READINESS_BLOCKER_SIZING)
    return {
        "readiness_status": "blocked" if blockers else "ready",
        "readiness_blockers": ",".join(blockers),
    }


def _readiness_blockers(row: Mapping[str, Any]) -> list[str]:
    blockers = str(row.get("readiness_blockers") or "")
    return [blocker for blocker in blockers.split(",") if blocker]


def _execution_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    status = str(row.get("decision_status") or "watch").lower()
    if status not in {"bought", "sold"}:
        return {"execution_status": "not_applicable", "execution_blockers": "", "execution_value": ""}

    blockers: list[str] = []
    execution_price = _finite_float(row.get("execution_price"))
    execution_shares = _positive_int(row.get("execution_shares"))
    if execution_price is None or execution_price <= 0:
        blockers.append(EXECUTION_BLOCKER_PRICE)
    if execution_shares is None:
        blockers.append(EXECUTION_BLOCKER_SHARES)
    execution_value = round(execution_price * execution_shares, 2) if not blockers else ""
    return {
        "execution_status": "recorded" if not blockers else "missing",
        "execution_blockers": ",".join(blockers),
        "execution_shares": execution_shares or row.get("execution_shares") or "",
        "execution_value": execution_value,
    }


def _execution_blockers(row: Mapping[str, Any]) -> list[str]:
    blockers = str(row.get("execution_blockers") or "")
    return [blocker for blocker in blockers.split(",") if blocker]


def _exit_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    status = str(row.get("decision_status") or "watch").lower()
    if status != "sold":
        return {
            "exit_status": "not_applicable",
            "exit_blockers": "",
            "exit_value": "",
            "realized_pnl": "",
            "realized_pnl_pct": "",
            "realized_r_multiple": "",
        }

    blockers: list[str] = []
    exit_price = _finite_float(row.get("exit_price"))
    execution_price = _finite_float(row.get("execution_price"))
    exit_shares = _positive_int(row.get("exit_shares")) or _positive_int(row.get("execution_shares"))
    stop_price = _finite_float(row.get("stop_loss_price"))
    if exit_price is None or exit_price <= 0:
        blockers.append(EXIT_BLOCKER_PRICE)
    if execution_price is None or execution_price <= 0:
        blockers.append(EXIT_BLOCKER_ENTRY)
    if exit_shares is None:
        blockers.append(EXIT_BLOCKER_SHARES)
    if blockers:
        return {
            "exit_status": "missing",
            "exit_blockers": ",".join(blockers),
            "exit_shares": exit_shares or row.get("exit_shares") or "",
            "exit_value": "",
            "realized_pnl": "",
            "realized_pnl_pct": "",
            "realized_r_multiple": "",
        }
    exit_value = round(exit_price * exit_shares, 2)
    realized_pnl = round((exit_price - execution_price) * exit_shares, 2)
    realized_pnl_pct = round(((exit_price - execution_price) / execution_price) * 100, 2)
    risk_per_share = execution_price - stop_price if stop_price is not None else None
    realized_r_multiple = (
        round((exit_price - execution_price) / risk_per_share, 2)
        if risk_per_share and risk_per_share > 0
        else ""
    )
    return {
        "exit_status": "recorded",
        "exit_blockers": "",
        "exit_shares": exit_shares,
        "exit_value": exit_value,
        "realized_pnl": realized_pnl,
        "realized_pnl_pct": realized_pnl_pct,
        "realized_r_multiple": realized_r_multiple,
    }


def _exit_blockers(row: Mapping[str, Any]) -> list[str]:
    blockers = str(row.get("exit_blockers") or "")
    return [blocker for blocker in blockers.split(",") if blocker]


def _exit_entry_value(row: Mapping[str, Any]) -> float | None:
    execution_price = _finite_float(row.get("execution_price"))
    exit_shares = _positive_int(row.get("exit_shares"))
    if execution_price is None or exit_shares is None:
        return None
    return round(execution_price * exit_shares, 2)


def _position_monitor_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    if row.get("execution_status") != "recorded" or str(row.get("decision_status") or "").lower() != "bought":
        return _blank_position_monitor()

    last_price = _finite_float(row.get("current_price"))
    execution_price = _finite_float(row.get("execution_price"))
    execution_shares = _positive_int(row.get("execution_shares"))
    stop_price = _finite_float(row.get("stop_loss_price"))
    if last_price is None or execution_price is None or execution_shares is None:
        alert_status = "missing_current_price"
        signature = _position_alert_signature(alert_status, last_price, stop_price)
        return _blank_position_monitor(
            alert_status=alert_status,
            alert_reason="current price unavailable",
            alert_signature=signature,
            acknowledged=_position_alert_acknowledged(row, signature),
            acknowledged_at=row.get("position_alert_acknowledged_at") or "",
        )

    pnl = round((last_price - execution_price) * execution_shares, 2)
    pnl_pct = round(((last_price - execution_price) / execution_price) * 100, 2) if execution_price > 0 else ""
    risk_per_share = execution_price - stop_price if stop_price is not None else None
    r_multiple = round((last_price - execution_price) / risk_per_share, 2) if risk_per_share and risk_per_share > 0 else ""
    stop_distance_pct = round(((last_price - stop_price) / last_price) * 100, 2) if stop_price and last_price > 0 else ""
    alert_status, alert_reason = _position_alert_status(last_price, stop_price, stop_distance_pct)
    alert_signature = _position_alert_signature(alert_status, last_price, stop_price)
    alert_acknowledged = _position_alert_acknowledged(row, alert_signature)
    return {
        "position_last_price": round(last_price, 2),
        "position_pnl": pnl,
        "position_pnl_pct": pnl_pct,
        "position_r_multiple": r_multiple,
        "stop_distance_pct": stop_distance_pct,
        "position_alert_status": alert_status,
        "position_alert_reason": alert_reason,
        "position_alert_signature": alert_signature,
        "position_alert_acknowledged": alert_acknowledged,
        "position_alert_acknowledged_at": row.get("position_alert_acknowledged_at") if alert_acknowledged else "",
    }


def _blank_position_monitor(
    *,
    alert_status: str = "",
    alert_reason: str = "",
    alert_signature: str = "",
    acknowledged: bool = False,
    acknowledged_at: str = "",
) -> dict[str, Any]:
    return {
        "position_last_price": "",
        "position_pnl": "",
        "position_pnl_pct": "",
        "position_r_multiple": "",
        "stop_distance_pct": "",
        "position_alert_status": alert_status,
        "position_alert_reason": alert_reason,
        "position_alert_signature": alert_signature,
        "position_alert_acknowledged": acknowledged,
        "position_alert_acknowledged_at": acknowledged_at if acknowledged else "",
    }


def _position_alert_status(
    last_price: float,
    stop_price: float | None,
    stop_distance_pct: float | str,
) -> tuple[str, str]:
    if stop_price is None or stop_price <= 0:
        return "missing_stop_loss", "stop loss unavailable"
    if last_price <= stop_price:
        return "stop_breached", "last price is at or below stop loss"
    if isinstance(stop_distance_pct, (int, float)) and stop_distance_pct <= POSITION_NEAR_STOP_DISTANCE_PCT:
        return "near_stop", f"last price is within {_format_percent_limit(POSITION_NEAR_STOP_DISTANCE_PCT)} of stop loss"
    return "ok", ""


def _position_alert_signature(status: str, last_price: float | None, stop_price: float | None) -> str:
    if status not in POSITION_ALERT_ATTENTION_ORDER:
        return ""
    last_token = f"{last_price:.2f}" if last_price is not None and math.isfinite(last_price) else ""
    stop_token = f"{stop_price:.2f}" if stop_price is not None and math.isfinite(stop_price) else ""
    return f"{status}|{last_token}|{stop_token}"


def _position_alert_acknowledged(row: Mapping[str, Any], signature: str) -> bool:
    if not signature:
        return False
    acknowledged_at = str(row.get("position_alert_acknowledged_at") or "").strip()
    acknowledged_signature = str(row.get("position_alert_ack_signature") or "").strip()
    return bool(acknowledged_at and acknowledged_signature == signature)


def _csv_safe_row(row: Mapping[str, Any]) -> dict[str, Any]:
    safe = {key: ",".join(value) if isinstance(value, list) else value for key, value in row.items()}
    for field in CSV_FORMULA_TEXT_FIELDS:
        safe[field] = _escape_csv_formula(safe.get(field, ""))
    return safe


def _escape_csv_formula(value: Any) -> Any:
    if not isinstance(value, str) or value == "":
        return value
    if value[0] in {"=", "+", "-", "@", "\t", "\r"}:
        return f"'{value}"
    return value


def _position_sizing(item: Mapping[str, Any], risk: Mapping[str, Any] | None) -> dict[str, Any]:
    settings = _export_risk_settings(risk)
    entry = _finite_float(item.get("buy_zone_low"))
    if entry is None:
        entry = _finite_float(item.get("pivot_price"))
    stop = _finite_float(item.get("stop_loss_price"))
    account_equity = settings.get("account_equity")
    risk_pct = settings.get("risk_pct")
    if account_equity is None or risk_pct is None:
        return _blank_sizing()
    risk_amount = account_equity * (risk_pct / 100)
    if entry is None or stop is None:
        return _blank_sizing(risk_amount=risk_amount)
    risk_per_share = entry - stop
    if entry <= 0 or stop <= 0 or risk_amount <= 0 or risk_per_share <= 0:
        return _blank_sizing(risk_amount=risk_amount)
    planned_shares = math.floor(risk_amount / risk_per_share)
    if planned_shares <= 0:
        return _blank_sizing(risk_amount=risk_amount, risk_per_share=risk_per_share)
    return {
        "risk_amount": round(risk_amount, 2),
        "risk_per_share": round(risk_per_share, 2),
        "planned_shares": planned_shares,
        "planned_capital": round(planned_shares * entry, 2),
    }


def _blank_sizing(*, risk_amount: float | None = None, risk_per_share: float | None = None) -> dict[str, Any]:
    return {
        "risk_amount": round(risk_amount, 2) if risk_amount is not None and math.isfinite(risk_amount) else "",
        "risk_per_share": round(risk_per_share, 2) if risk_per_share is not None and math.isfinite(risk_per_share) else "",
        "planned_shares": "",
        "planned_capital": "",
    }


def _export_risk_settings(risk: Mapping[str, Any] | None) -> dict[str, float | None]:
    risk = risk or {}
    account_equity = _finite_float(risk.get("account_equity"))
    risk_pct = _finite_float(risk.get("risk_pct"))
    max_capital_pct = _finite_float(risk.get("max_capital_pct"))
    max_queue_risk_pct = _finite_float(risk.get("max_queue_risk_pct"))
    max_open_position_risk_pct = _finite_float(risk.get("max_open_position_risk_pct"))
    max_concentration_pct = _finite_float(risk.get("max_concentration_pct"))
    max_open_concentration_pct = _finite_float(risk.get("max_open_concentration_pct"))
    return {
        "account_equity": account_equity if account_equity is not None and account_equity >= 0 else None,
        "risk_pct": risk_pct if risk_pct is not None and risk_pct >= 0 else None,
        "max_capital_pct": (
            max_capital_pct if max_capital_pct is not None and max_capital_pct >= 0 else DEFAULT_MAX_CAPITAL_PCT
        ),
        "max_queue_risk_pct": (
            max_queue_risk_pct
            if max_queue_risk_pct is not None and max_queue_risk_pct >= 0
            else DEFAULT_MAX_QUEUE_RISK_PCT
        ),
        "max_open_position_risk_pct": (
            max_open_position_risk_pct
            if max_open_position_risk_pct is not None and max_open_position_risk_pct >= 0
            else DEFAULT_MAX_OPEN_POSITION_RISK_PCT
        ),
        "max_concentration_pct": (
            max_concentration_pct
            if max_concentration_pct is not None and max_concentration_pct >= 0
            else DEFAULT_MAX_CONCENTRATION_PCT
        ),
        "max_open_concentration_pct": (
            max_open_concentration_pct
            if max_open_concentration_pct is not None and max_open_concentration_pct >= 0
            else DEFAULT_MAX_OPEN_CONCENTRATION_PCT
        ),
    }


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _percent_of(value: float, total: float | None) -> float | None:
    if total is None or total <= 0:
        return None
    return round((value / total) * 100, 2)


def _summary_realized_performance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    realized = [row for row in rows if _finite_float(row.get("realized_pnl")) is not None]
    winners = [row for row in realized if (_finite_float(row.get("realized_pnl")) or 0) > 0]
    losers = [row for row in realized if (_finite_float(row.get("realized_pnl")) or 0) < 0]
    flat = [row for row in realized if (_finite_float(row.get("realized_pnl")) or 0) == 0]
    total_count = len(realized)
    total_pnl = sum(_finite_float(row.get("realized_pnl")) or 0 for row in realized)
    winner_sum = sum(_finite_float(row.get("realized_pnl")) or 0 for row in winners)
    loser_sum = sum(_finite_float(row.get("realized_pnl")) or 0 for row in losers)
    average_pnl = round(total_pnl / total_count, 2) if total_count else None
    average_winner_pnl = round(winner_sum / len(winners), 2) if winners else None
    average_loser_pnl = round(loser_sum / len(losers), 2) if losers else None
    r_values = [
        value
        for value in (_finite_float(row.get("realized_r_multiple")) for row in realized)
        if value is not None
    ]
    average_r = round(sum(r_values) / len(r_values), 2) if r_values else None
    sorted_by_pnl = sorted(
        realized,
        key=lambda row: (_finite_float(row.get("realized_pnl")) or 0, str(row.get("ticker") or "")),
        reverse=True,
    )
    curve, max_drawdown, max_drawdown_pct = _summary_realized_curve(realized)
    return {
        "trade_count": total_count,
        "winners": len(winners),
        "losers": len(losers),
        "flat": len(flat),
        "win_rate_pct": _percent_of(len(winners), total_count),
        "average_realized_pnl": average_pnl,
        "average_realized_r": average_r,
        "average_winner_pnl": average_winner_pnl,
        "average_loser_pnl": average_loser_pnl,
        "expectancy_pnl": average_pnl,
        "expectancy_r": average_r,
        "profit_factor": round(winner_sum / abs(loser_sum), 2) if loser_sum < 0 else None,
        "payoff_ratio": (
            round(average_winner_pnl / abs(average_loser_pnl), 2)
            if average_winner_pnl is not None and average_loser_pnl is not None and average_loser_pnl < 0
            else None
        ),
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,
        "cumulative_pnl_curve": curve,
        "best_trade": _realized_trade_snapshot(sorted_by_pnl[0]) if sorted_by_pnl else None,
        "worst_trade": _realized_trade_snapshot(sorted_by_pnl[-1]) if sorted_by_pnl else None,
    }


def _summary_realized_curve(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float | None, float | None]:
    ordered = sorted(
        rows,
        key=lambda row: (
            str(row.get("exited_at") or row.get("updated_at") or row.get("added_at") or ""),
            str(row.get("ticker") or ""),
        ),
    )
    curve: list[dict[str, Any]] = []
    cumulative_pnl = 0.0
    peak_pnl = 0.0
    max_drawdown = 0.0
    max_drawdown_peak = 0.0
    for row in ordered:
        cumulative_pnl = round(cumulative_pnl + (_finite_float(row.get("realized_pnl")) or 0), 2)
        peak_pnl = max(peak_pnl, cumulative_pnl)
        drawdown = round(max(0.0, peak_pnl - cumulative_pnl), 2)
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_peak = peak_pnl
        snapshot = _realized_trade_snapshot(row)
        snapshot.update(
            {
                "cumulative_pnl": cumulative_pnl,
                "drawdown": drawdown,
            }
        )
        curve.append(snapshot)
    max_drawdown_pct = _percent_of(max_drawdown, max_drawdown_peak) if max_drawdown_peak > 0 else None
    return curve, round(max_drawdown, 2) if curve else None, max_drawdown_pct


def _realized_trade_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ticker": row.get("ticker") or "",
        "name": row.get("name") or "",
        "realized_pnl": _finite_float(row.get("realized_pnl")),
        "realized_pnl_pct": _finite_float(row.get("realized_pnl_pct")),
        "realized_r_multiple": _finite_float(row.get("realized_r_multiple")),
        "exit_reason": row.get("exit_reason") or "",
        "exited_at": row.get("exited_at") or "",
    }


def _summary_status_breakdown(rows: list[dict[str, Any]], settings: Mapping[str, Any]) -> list[dict[str, Any]]:
    account_equity = _finite_float(settings.get("account_equity"))
    buckets = {
        status: {"status": status, "count": 0, "risk_amount": 0.0, "planned_capital": 0.0}
        for status in SUMMARY_STATUS_ORDER
    }
    for row in rows:
        status = str(row.get("decision_status") or "watch").lower()
        if status not in DECISION_STATUSES:
            status = "watch"
        bucket = buckets.setdefault(status, {"status": status, "count": 0, "risk_amount": 0.0, "planned_capital": 0.0})
        bucket["count"] += 1
        if status in INACTIVE_DECISION_STATUSES or not _positive_int(row.get("planned_shares")):
            continue
        bucket["risk_amount"] += _finite_float(row.get("risk_amount")) or 0
        bucket["planned_capital"] += _finite_float(row.get("planned_capital")) or 0
    return [
        {
            "status": bucket["status"],
            "count": bucket["count"],
            "risk_amount": round(bucket["risk_amount"], 2),
            "planned_capital": round(bucket["planned_capital"], 2),
            "risk_budget_pct": _percent_of(bucket["risk_amount"], account_equity),
            "planned_capital_pct": _percent_of(bucket["planned_capital"], account_equity),
        }
        for bucket in buckets.values()
    ]


def _summary_open_position_risk(rows: list[dict[str, Any]], account_equity: float | None) -> dict[str, Any]:
    total_market_value = 0.0
    total_stop_risk = 0.0
    stop_distance_weighted_sum = 0.0
    stop_distance_weight = 0.0
    monitored_count = 0
    stop_covered_count = 0
    missing_current_price_count = 0
    missing_stop_loss_count = 0
    risk_items: list[dict[str, Any]] = []

    for row in rows:
        shares = _positive_int(row.get("execution_shares"))
        last_price = _finite_float(row.get("position_last_price"))
        stop_price = _finite_float(row.get("stop_loss_price"))
        alert_status = str(row.get("position_alert_status") or "")
        if alert_status == "missing_current_price":
            missing_current_price_count += 1
        if alert_status == "missing_stop_loss":
            missing_stop_loss_count += 1
        if shares is None or last_price is None or last_price <= 0:
            continue

        monitored_count += 1
        market_value = round(last_price * shares, 2)
        total_market_value += market_value
        if stop_price is None or stop_price <= 0:
            continue

        stop_covered_count += 1
        stop_risk_amount = round(max(0.0, (last_price - stop_price) * shares), 2)
        stop_distance_pct = _finite_float(row.get("stop_distance_pct"))
        total_stop_risk += stop_risk_amount
        if stop_distance_pct is not None:
            stop_distance_weighted_sum += stop_distance_pct * market_value
            stop_distance_weight += market_value
        risk_items.append(
            {
                "ticker": row.get("ticker") or "",
                "name": row.get("name") or "",
                "market_value": market_value,
                "stop_risk_amount": stop_risk_amount,
                "stop_distance_pct": stop_distance_pct,
                "position_pnl": _finite_float(row.get("position_pnl")),
                "position_pnl_pct": _finite_float(row.get("position_pnl_pct")),
                "alert_status": alert_status,
            }
        )

    risk_items.sort(
        key=lambda item: (
            -(_finite_float(item.get("stop_risk_amount")) or 0),
            _alert_distance_sort_value(item.get("stop_distance_pct")),
            str(item.get("ticker") or ""),
        )
    )
    return {
        "position_count": len(rows),
        "monitored_count": monitored_count,
        "stop_covered_count": stop_covered_count,
        "missing_current_price_count": missing_current_price_count,
        "missing_stop_loss_count": missing_stop_loss_count,
        "total_market_value": round(total_market_value, 2),
        "market_value_pct": _percent_of(total_market_value, account_equity),
        "total_stop_risk": round(total_stop_risk, 2),
        "stop_risk_pct": _percent_of(total_stop_risk, account_equity),
        "average_stop_distance_pct": (
            round(stop_distance_weighted_sum / stop_distance_weight, 2) if stop_distance_weight > 0 else None
        ),
        "stop_coverage_pct": _percent_of(stop_covered_count, len(rows)),
        "largest_stop_risk_items": risk_items[:5],
    }


def _summary_open_position_concentration(rows: list[Mapping[str, Any]], settings: Mapping[str, Any]) -> dict[str, Any]:
    sector_rows = _open_position_concentration_breakdown(rows, "sector", settings, fallback="Unclassified")
    setup_rows = _open_position_concentration_breakdown(rows, "setup_status", settings, fallback="Unclassified")
    warning_share_pct = _concentration_warning_share_pct(
        settings.get("max_open_concentration_pct"),
        default=DEFAULT_MAX_OPEN_CONCENTRATION_PCT,
    )
    warnings = _open_position_concentration_warnings(
        sector_rows,
        "sector",
        warning_share_pct,
    ) + _open_position_concentration_warnings(
        setup_rows,
        "setup",
        warning_share_pct,
    )
    return {
        "top_limit": CONCENTRATION_TOP_LIMIT,
        "warning_share_pct": warning_share_pct,
        "sector": sector_rows,
        "setup": setup_rows,
        "top_sector": sector_rows[0] if sector_rows else None,
        "top_setup": setup_rows[0] if setup_rows else None,
        "warnings": warnings,
    }


def _open_position_concentration_breakdown(
    rows: list[Mapping[str, Any]],
    field: str,
    settings: Mapping[str, Any],
    *,
    fallback: str,
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    account_equity = _finite_float(settings.get("account_equity"))
    total_market_value = 0.0
    total_stop_risk = 0.0
    prepared_rows: list[tuple[Mapping[str, Any], float | None, float | None]] = []
    for row in rows:
        shares = _positive_int(row.get("execution_shares"))
        last_price = _finite_float(row.get("position_last_price"))
        stop_price = _finite_float(row.get("stop_loss_price"))
        market_value = round(last_price * shares, 2) if shares is not None and last_price is not None and last_price > 0 else None
        stop_risk_amount = (
            round(max(0.0, (last_price - stop_price) * shares), 2)
            if market_value is not None and shares is not None and stop_price is not None and stop_price > 0
            else None
        )
        if market_value is not None:
            total_market_value += market_value
        if stop_risk_amount is not None:
            total_stop_risk += stop_risk_amount
        prepared_rows.append((row, market_value, stop_risk_amount))

    for row, market_value, stop_risk_amount in prepared_rows:
        raw_label = _clean_text(row.get(field), max_length=80) or fallback
        label = raw_label.replace("_", " ").strip() or fallback
        bucket = buckets.setdefault(
            label,
            {
                "label": label,
                "count": 0,
                "priced_count": 0,
                "stop_covered_count": 0,
                "market_value": 0.0,
                "stop_risk_amount": 0.0,
                "tickers": [],
            },
        )
        bucket["count"] += 1
        ticker = str(row.get("ticker") or "").upper()
        if ticker and len(bucket["tickers"]) < 8:
            bucket["tickers"].append(ticker)
        if market_value is not None:
            bucket["priced_count"] += 1
            bucket["market_value"] = round(bucket["market_value"] + market_value, 2)
        if stop_risk_amount is not None:
            bucket["stop_covered_count"] += 1
            bucket["stop_risk_amount"] = round(bucket["stop_risk_amount"] + stop_risk_amount, 2)

    output = []
    for bucket in buckets.values():
        market_value = _finite_float(bucket.get("market_value")) or 0.0
        stop_risk_amount = _finite_float(bucket.get("stop_risk_amount")) or 0.0
        output.append(
            {
                **bucket,
                "market_value": round(market_value, 2),
                "stop_risk_amount": round(stop_risk_amount, 2),
                "share_of_market_value_pct": _percent_of(market_value, total_market_value),
                "share_of_stop_risk_pct": _percent_of(stop_risk_amount, total_stop_risk),
                "market_value_pct": _percent_of(market_value, account_equity),
                "stop_risk_pct": _percent_of(stop_risk_amount, account_equity),
            }
        )
    output.sort(
        key=lambda item: (
            -(_finite_float(item.get("market_value")) or 0),
            -(_finite_float(item.get("stop_risk_amount")) or 0),
            -int(item.get("count") or 0),
            str(item.get("label") or ""),
        )
    )
    return output[:CONCENTRATION_TOP_LIMIT]


def _open_position_concentration_warnings(
    rows: list[Mapping[str, Any]],
    group_label: str,
    warning_share_pct: float,
) -> list[str]:
    warnings: list[str] = []
    top = rows[0] if rows else None
    if not top:
        return warnings
    label = str(top.get("label") or "")
    share = _finite_float(top.get("share_of_market_value_pct")) or 0.0
    priced_count = int(top.get("priced_count") or 0)
    if label != "Unclassified" and priced_count >= 2 and share >= warning_share_pct:
        warnings.append(f"open {group_label} concentration: {label} is {share:g}% of open market value")
    return warnings


def _summary_largest_positions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exposures = []
    for row in rows:
        planned_capital = _finite_float(row.get("planned_capital")) or 0
        risk_amount = _finite_float(row.get("risk_amount")) or 0
        exposures.append(
            {
                "ticker": row.get("ticker") or "",
                "name": row.get("name") or "",
                "decision_status": row.get("decision_status") or "watch",
                "planned_capital": round(planned_capital, 2),
                "risk_amount": round(risk_amount, 2),
                "planned_shares": _positive_int(row.get("planned_shares")) or 0,
                "entry_price": _finite_float(row.get("buy_zone_low")) or _finite_float(row.get("pivot_price")),
                "stop_loss_price": _finite_float(row.get("stop_loss_price")),
            }
        )
    exposures.sort(key=lambda row: (row["planned_capital"], row["risk_amount"], str(row["ticker"])), reverse=True)
    return exposures[:5]


def _summary_readiness_blocker_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        READINESS_BLOCKER_CHECKLIST: 0,
        READINESS_BLOCKER_SIZING: 0,
    }
    for row in rows:
        if row.get("readiness_status") != "blocked":
            continue
        for blocker in _readiness_blockers(row):
            counts[blocker] = counts.get(blocker, 0) + 1
    return counts


def _summary_readiness_blocker_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        blockers = _readiness_blockers(row)
        if str(row.get("readiness_status") or "") != "blocked" or not blockers:
            continue
        items.append(
            {
                "ticker": row.get("ticker") or "",
                "name": row.get("name") or "",
                "decision_status": row.get("decision_status") or "watch",
                "readiness_status": row.get("readiness_status") or "blocked",
                "readiness_blockers": blockers,
                "checklist_complete_count": _positive_int(row.get("checklist_complete_count")) or 0,
                "checklist_total_count": _positive_int(row.get("checklist_total_count")) or len(REVIEW_CHECK_KEYS),
                "planned_shares": _positive_int(row.get("planned_shares")) or 0,
                "entry_price": _finite_float(row.get("buy_zone_low")) or _finite_float(row.get("pivot_price")),
                "stop_loss_price": _finite_float(row.get("stop_loss_price")),
            }
        )
    return items[:8]


def _summary_position_alert_counts(rows: list[dict[str, Any]], acknowledged: bool | None = None) -> dict[str, int]:
    counts = {status: 0 for status in POSITION_ALERT_STATUSES}
    for row in rows:
        status = str(row.get("position_alert_status") or "")
        if status in counts:
            if acknowledged is not None and bool(row.get("position_alert_acknowledged")) != acknowledged:
                continue
            counts[status] += 1
    return counts


def _summary_position_alert_items(rows: list[dict[str, Any]], *, acknowledged: bool) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.get("position_alert_status") or "")
        if status not in POSITION_ALERT_ATTENTION_ORDER:
            continue
        if bool(row.get("position_alert_acknowledged")) != acknowledged:
            continue
        items.append(
            {
                "ticker": row.get("ticker") or "",
                "name": row.get("name") or "",
                "alert_status": status,
                "alert_reason": row.get("position_alert_reason") or "",
                "alert_signature": row.get("position_alert_signature") or "",
                "alert_acknowledged": bool(row.get("position_alert_acknowledged")),
                "alert_acknowledged_at": row.get("position_alert_acknowledged_at") or "",
                "position_last_price": row.get("position_last_price") or "",
                "stop_loss_price": row.get("stop_loss_price") or "",
                "stop_distance_pct": row.get("stop_distance_pct") or "",
                "position_pnl": row.get("position_pnl") or "",
                "position_pnl_pct": row.get("position_pnl_pct") or "",
                "position_r_multiple": row.get("position_r_multiple") or "",
            }
        )
    items.sort(
        key=lambda item: (
            POSITION_ALERT_ATTENTION_ORDER.get(str(item.get("alert_status") or ""), 99),
            _alert_distance_sort_value(item.get("stop_distance_pct")),
            str(item.get("ticker") or ""),
        )
    )
    return items[:8]


def _summary_concentration(rows: list[Mapping[str, Any]], settings: Mapping[str, Any]) -> dict[str, Any]:
    sector_rows = _concentration_breakdown(rows, "sector", settings, fallback="Unclassified")
    setup_rows = _concentration_breakdown(rows, "setup_status", settings, fallback="Unclassified")
    warning_share_pct = _concentration_warning_share_pct(
        settings.get("max_concentration_pct"),
        default=DEFAULT_MAX_CONCENTRATION_PCT,
    )
    warnings = _concentration_warnings(sector_rows, "sector", warning_share_pct) + _concentration_warnings(
        setup_rows,
        "setup",
        warning_share_pct,
    )
    return {
        "top_limit": CONCENTRATION_TOP_LIMIT,
        "warning_share_pct": warning_share_pct,
        "sector": sector_rows,
        "setup": setup_rows,
        "top_sector": sector_rows[0] if sector_rows else None,
        "top_setup": setup_rows[0] if setup_rows else None,
        "warnings": warnings,
    }


def _concentration_breakdown(
    rows: list[Mapping[str, Any]],
    field: str,
    settings: Mapping[str, Any],
    *,
    fallback: str,
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    total_capital = sum(_finite_float(row.get("planned_capital")) or 0 for row in rows)
    total_risk = sum(_finite_float(row.get("risk_amount")) or 0 for row in rows if _positive_int(row.get("planned_shares")))
    account_equity = _finite_float(settings.get("account_equity"))
    for row in rows:
        raw_label = _clean_text(row.get(field), max_length=80) or fallback
        label = raw_label.replace("_", " ").strip() or fallback
        bucket = buckets.setdefault(
            label,
            {
                "label": label,
                "count": 0,
                "sized_count": 0,
                "risk_amount": 0.0,
                "planned_capital": 0.0,
                "tickers": [],
            },
        )
        bucket["count"] += 1
        ticker = str(row.get("ticker") or "").upper()
        if ticker and len(bucket["tickers"]) < 8:
            bucket["tickers"].append(ticker)
        planned_capital = _finite_float(row.get("planned_capital")) or 0.0
        risk_amount = _finite_float(row.get("risk_amount")) or 0.0
        if _positive_int(row.get("planned_shares")):
            bucket["sized_count"] += 1
            bucket["planned_capital"] = round(bucket["planned_capital"] + planned_capital, 2)
            bucket["risk_amount"] = round(bucket["risk_amount"] + risk_amount, 2)

    output = []
    for bucket in buckets.values():
        planned_capital = _finite_float(bucket.get("planned_capital")) or 0.0
        risk_amount = _finite_float(bucket.get("risk_amount")) or 0.0
        output.append(
            {
                **bucket,
                "planned_capital": round(planned_capital, 2),
                "risk_amount": round(risk_amount, 2),
                "share_of_planned_capital_pct": _percent_of(planned_capital, total_capital),
                "share_of_risk_pct": _percent_of(risk_amount, total_risk),
                "planned_capital_pct": _percent_of(planned_capital, account_equity),
                "risk_budget_pct": _percent_of(risk_amount, account_equity),
            }
        )
    output.sort(
        key=lambda item: (
            -(_finite_float(item.get("planned_capital")) or 0),
            -int(item.get("count") or 0),
            str(item.get("label") or ""),
        )
    )
    return output[:CONCENTRATION_TOP_LIMIT]


def _concentration_warning_share_pct(value: Any, *, default: float) -> float:
    share = _finite_float(value)
    if share is None or share < 0:
        return float(default)
    return min(100.0, share)


def _concentration_warnings(
    rows: list[Mapping[str, Any]],
    group_label: str,
    warning_share_pct: float,
) -> list[str]:
    warnings: list[str] = []
    top = rows[0] if rows else None
    if not top:
        return warnings
    label = str(top.get("label") or "")
    share = _finite_float(top.get("share_of_planned_capital_pct")) or 0.0
    sized_count = int(top.get("sized_count") or 0)
    if label != "Unclassified" and sized_count >= 2 and share >= warning_share_pct:
        warnings.append(f"{group_label} concentration: {label} is {share:g}% of planned capital")
    return warnings


def _summary_review_aging(rows: list[Mapping[str, Any]], now: dt.datetime) -> dict[str, Any]:
    snapshots = [_aging_snapshot(row, now) for row in rows]
    snapshots = [item for item in snapshots if item is not None]
    stale_items = [
        item
        for item in snapshots
        if item["staleness"] in {"ready_stale", "active_stale"}
    ]
    stale_items.sort(
        key=lambda item: (
            0 if item["staleness"] == "ready_stale" else 1,
            -(item.get("idle_days") or 0),
            str(item.get("ticker") or ""),
        )
    )
    buckets = {
        "fresh": sum(1 for item in snapshots if (item.get("idle_days") or 0) <= 1),
        "aging": sum(1 for item in snapshots if 2 <= (item.get("idle_days") or 0) <= 4),
        "stale": sum(1 for item in snapshots if (item.get("idle_days") or 0) >= REVIEW_STALE_DAYS),
    }
    return {
        "active_count": len(snapshots),
        "review_stale_days": REVIEW_STALE_DAYS,
        "ready_stale_days": READY_STALE_DAYS,
        "oldest_active_days": max((item.get("age_days") or 0 for item in snapshots), default=None),
        "oldest_idle_days": max((item.get("idle_days") or 0 for item in snapshots), default=None),
        "stale_active_count": sum(1 for item in stale_items if item["staleness"] == "active_stale"),
        "stale_ready_count": sum(1 for item in stale_items if item["staleness"] == "ready_stale"),
        "buckets": buckets,
        "stale_items": stale_items[:8],
    }


def _aging_snapshot(row: Mapping[str, Any], now: dt.datetime) -> dict[str, Any] | None:
    status = str(row.get("decision_status") or "watch").lower()
    if status in INACTIVE_DECISION_STATUSES:
        return None
    added_at = _parse_datetime(row.get("added_at"))
    updated_at = _parse_datetime(row.get("updated_at")) or added_at
    age_days = _age_days(added_at, now)
    idle_days = _age_days(updated_at, now)
    effective_idle_days = idle_days if idle_days is not None else age_days
    if status == "ready" and effective_idle_days is not None and effective_idle_days >= READY_STALE_DAYS:
        staleness = "ready_stale"
    elif effective_idle_days is not None and effective_idle_days >= REVIEW_STALE_DAYS:
        staleness = "active_stale"
    else:
        staleness = "fresh"
    return {
        "ticker": row.get("ticker") or "",
        "name": row.get("name") or "",
        "decision_status": status,
        "review_priority": row.get("review_priority") or "normal",
        "age_days": age_days,
        "idle_days": effective_idle_days,
        "added_at": row.get("added_at") or "",
        "updated_at": row.get("updated_at") or "",
        "staleness": staleness,
    }


def _summary_now(value: dt.datetime | None) -> dt.datetime:
    current_time = value or dt.datetime.now(dt.timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=dt.timezone.utc)
    return current_time.astimezone(dt.timezone.utc)


def _parse_datetime(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _age_days(value: dt.datetime | None, now: dt.datetime) -> int | None:
    if value is None:
        return None
    return max(0, int((now - value).total_seconds() // 86400))


def _alert_distance_sort_value(value: Any) -> float:
    number = _finite_float(value)
    return number if number is not None else 999.0


def _summary_warnings(
    unsized_items: int,
    ready_checklist_blockers: int,
    bought_execution_missing: int,
    sold_exit_missing: int,
    position_alert_counts: Mapping[str, int],
    stale_active_count: int,
    stale_ready_count: int,
    concentration_warnings: list[Any],
    planned_capital_pct: float | None,
    risk_budget_pct: float | None,
    open_position_risk_pct: float | None,
    max_capital_pct: float | None,
    max_queue_risk_pct: float | None,
    max_open_position_risk_pct: float | None,
) -> list[str]:
    warnings: list[str] = []
    if unsized_items:
        warnings.append(f"{unsized_items} active review item(s) are missing buy or stop levels")
    if ready_checklist_blockers:
        warnings.append(f"{ready_checklist_blockers} ready review item(s) have incomplete pre-buy checklists")
    if bought_execution_missing:
        warnings.append(f"{bought_execution_missing} bought review item(s) are missing execution records")
    if sold_exit_missing:
        warnings.append(f"{sold_exit_missing} sold review item(s) are missing exit records")
    if stale_ready_count:
        warnings.append(f"{stale_ready_count} ready review item(s) have not been touched for {READY_STALE_DAYS}+ days")
    if stale_active_count:
        warnings.append(f"{stale_active_count} active review item(s) have not been touched for {REVIEW_STALE_DAYS}+ days")
    warnings.extend(str(warning) for warning in concentration_warnings if str(warning or "").strip())
    stop_breached = int(position_alert_counts.get("stop_breached") or 0)
    near_stop = int(position_alert_counts.get("near_stop") or 0)
    missing_current_price = int(position_alert_counts.get("missing_current_price") or 0)
    missing_stop_loss = int(position_alert_counts.get("missing_stop_loss") or 0)
    if stop_breached:
        warnings.append(f"{stop_breached} bought position(s) are at or below stop loss")
    if near_stop:
        warnings.append(
            f"{near_stop} bought position(s) are within {_format_percent_limit(POSITION_NEAR_STOP_DISTANCE_PCT)} of stop loss"
        )
    if missing_current_price:
        warnings.append(f"{missing_current_price} executed bought position(s) are missing current prices")
    if missing_stop_loss:
        warnings.append(f"{missing_stop_loss} executed bought position(s) are missing stop levels")
    if planned_capital_pct is not None and planned_capital_pct > 100:
        warnings.append("planned capital exceeds account equity")
    elif (
        planned_capital_pct is not None
        and max_capital_pct is not None
        and planned_capital_pct > max_capital_pct
    ):
        warnings.append(f"planned capital uses more than {_format_percent_limit(max_capital_pct)} of account equity")
    if (
        risk_budget_pct is not None
        and max_queue_risk_pct is not None
        and risk_budget_pct > max_queue_risk_pct
    ):
        warnings.append(f"planned queue risk exceeds {_format_percent_limit(max_queue_risk_pct)} of account equity")
    if (
        open_position_risk_pct is not None
        and max_open_position_risk_pct is not None
        and open_position_risk_pct > max_open_position_risk_pct
    ):
        warnings.append(
            f"open position stop risk exceeds {_format_percent_limit(max_open_position_risk_pct)} of account equity"
        )
    return warnings


def _summary_risk_actions(
    *,
    unsized_items: int,
    ready_checklist_blockers: int,
    bought_execution_missing: int,
    sold_exit_missing: int,
    position_alert_items: list[Mapping[str, Any]],
    aging: Mapping[str, Any],
    concentration: Mapping[str, Any],
    open_position_concentration: Mapping[str, Any],
    planned_capital_pct: float | None,
    risk_budget_pct: float | None,
    open_position_risk_pct: float | None,
    max_capital_pct: float | None,
    max_queue_risk_pct: float | None,
    max_open_position_risk_pct: float | None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []

    def add(
        severity: str,
        category: str,
        label: str,
        detail: str,
        action: str,
        *,
        tickers: list[str] | None = None,
        count: int | None = None,
    ) -> None:
        actions.append(
            {
                "severity": severity,
                "category": category,
                "label": label,
                "detail": detail,
                "action": action,
                "tickers": tickers or [],
                "count": count if count is not None else len(tickers or []),
            }
        )

    stop_breached = _risk_action_alert_tickers(position_alert_items, "stop_breached")
    if stop_breached:
        add(
            "critical",
            "position_alert",
            "Stop breached",
            f"{len(stop_breached)} bought position(s) are at or below stop loss",
            "review_exit",
            tickers=stop_breached,
        )
    near_stop = _risk_action_alert_tickers(position_alert_items, "near_stop")
    if near_stop:
        add(
            "warning",
            "position_alert",
            "Near stop",
            f"{len(near_stop)} bought position(s) are within {_format_percent_limit(POSITION_NEAR_STOP_DISTANCE_PCT)} of stop loss",
            "review_stop",
            tickers=near_stop,
        )
    missing_prices = _risk_action_alert_tickers(position_alert_items, "missing_current_price")
    if missing_prices:
        add(
            "warning",
            "position_alert",
            "Refresh open prices",
            f"{len(missing_prices)} executed bought position(s) are missing current prices",
            "refresh_prices",
            tickers=missing_prices,
        )
    missing_stops = _risk_action_alert_tickers(position_alert_items, "missing_stop_loss")
    if missing_stops:
        add(
            "warning",
            "position_alert",
            "Add open stops",
            f"{len(missing_stops)} executed bought position(s) are missing stop levels",
            "set_stops",
            tickers=missing_stops,
        )

    if planned_capital_pct is not None and planned_capital_pct > 100:
        add(
            "critical",
            "guardrail",
            "Reduce planned capital",
            "Planned capital exceeds account equity",
            "reduce_queue",
        )
    elif max_capital_pct is not None and planned_capital_pct is not None and planned_capital_pct > max_capital_pct:
        add(
            "warning",
            "guardrail",
            "Reduce planned capital",
            f"Planned capital uses {planned_capital_pct:g}% vs {_format_percent_limit(max_capital_pct)} guardrail",
            "reduce_queue",
        )
    if max_queue_risk_pct is not None and risk_budget_pct is not None and risk_budget_pct > max_queue_risk_pct:
        add(
            "warning",
            "guardrail",
            "Reduce queue risk",
            f"Planned queue risk is {risk_budget_pct:g}% vs {_format_percent_limit(max_queue_risk_pct)} guardrail",
            "reduce_queue",
        )
    if (
        max_open_position_risk_pct is not None
        and open_position_risk_pct is not None
        and open_position_risk_pct > max_open_position_risk_pct
    ):
        add(
            "warning",
            "guardrail",
            "Reduce open stop risk",
            f"Open stop risk is {open_position_risk_pct:g}% vs {_format_percent_limit(max_open_position_risk_pct)} guardrail",
            "review_open_risk",
        )

    actions.extend(_risk_action_concentration(concentration, open_position=False))
    actions.extend(_risk_action_concentration(open_position_concentration, open_position=True))

    if unsized_items:
        add(
            "warning",
            "trade_plan",
            "Complete trade plans",
            f"{unsized_items} active review item(s) are missing buy or stop levels",
            "set_trade_plan",
            count=unsized_items,
        )
    if ready_checklist_blockers:
        add(
            "warning",
            "readiness",
            "Complete ready checklists",
            f"{ready_checklist_blockers} ready review item(s) have incomplete pre-buy checklists",
            "complete_checklist",
            count=ready_checklist_blockers,
        )
    if bought_execution_missing:
        add(
            "warning",
            "execution",
            "Record bought fills",
            f"{bought_execution_missing} bought review item(s) are missing execution records",
            "record_fills",
            count=bought_execution_missing,
        )
    if sold_exit_missing:
        add(
            "warning",
            "execution",
            "Record exits",
            f"{sold_exit_missing} sold review item(s) are missing exit records",
            "record_exits",
            count=sold_exit_missing,
        )

    stale_ready = int(aging.get("stale_ready_count") or 0)
    stale_active = int(aging.get("stale_active_count") or 0)
    stale_items = _risk_action_tickers(aging.get("stale_items"))
    if stale_ready:
        add(
            "warning",
            "aging",
            "Revalidate ready ideas",
            f"{stale_ready} ready review item(s) have not been touched for {READY_STALE_DAYS}+ days",
            "refresh_review",
            tickers=stale_items,
            count=stale_ready,
        )
    if stale_active:
        add(
            "warning",
            "aging",
            "Refresh stale reviews",
            f"{stale_active} active review item(s) have not been touched for {REVIEW_STALE_DAYS}+ days",
            "refresh_review",
            tickers=stale_items,
            count=stale_active,
        )
    return actions[:8]


def _risk_action_alert_tickers(items: list[Mapping[str, Any]], status: str) -> list[str]:
    return _risk_action_tickers(item for item in items if str(item.get("alert_status") or "") == status)


def _risk_action_tickers(items: Any) -> list[str]:
    tickers: list[str] = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        ticker = str(item.get("ticker") or "").upper()
        if ticker and ticker not in tickers:
            tickers.append(ticker)
        if len(tickers) >= 8:
            break
    return tickers


def _risk_action_concentration(concentration: Mapping[str, Any], *, open_position: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    threshold = _concentration_warning_share_pct(
        concentration.get("warning_share_pct"),
        default=DEFAULT_MAX_OPEN_CONCENTRATION_PCT if open_position else DEFAULT_MAX_CONCENTRATION_PCT,
    )
    for key, label in (("top_sector", "sector"), ("top_setup", "setup")):
        row = concentration.get(key)
        if not isinstance(row, Mapping):
            continue
        row_label = str(row.get("label") or "")
        if row_label == "Unclassified":
            continue
        count_key = "priced_count" if open_position else "sized_count"
        share_key = "share_of_market_value_pct" if open_position else "share_of_planned_capital_pct"
        amount_key = "market_value" if open_position else "planned_capital"
        share = _finite_float(row.get(share_key)) or 0.0
        count = int(row.get(count_key) or 0)
        if count < 2 or share < threshold:
            continue
        scope = "Open" if open_position else "Plan"
        amount = _finite_float(row.get(amount_key)) or 0.0
        actions.append(
            {
                "severity": "warning",
                "category": "concentration",
                "label": f"{scope} {label} concentration",
                "detail": f"{row_label} is {share:g}% of {'open market value' if open_position else 'planned capital'}",
                "action": "rebalance_open" if open_position else "rebalance_queue",
                "tickers": list(row.get("tickers") or [])[:8],
                "count": count,
                "amount": round(amount, 2),
            }
        )
    return actions


def _format_percent_limit(value: float) -> str:
    return f"{value:g}%"


def _normalize_ticker(ticker: str) -> str:
    normalized = str(ticker or "").strip().upper().replace(".", "-")
    if not _TICKER_RE.match(normalized):
        raise ValueError("Ticker must be 1-15 uppercase letters, numbers, underscores, or hyphens")
    return normalized


def _normalize_ticker_list(tickers: list[Any]) -> list[str]:
    if not isinstance(tickers, list):
        raise ValueError("tickers must be a JSON array")
    normalized: list[str] = []
    seen: set[str] = set()
    for ticker in tickers[:QUEUE_LIMIT]:
        value = _normalize_ticker(str(ticker or ""))
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _normalize_price_updates(prices: Any) -> dict[str, float]:
    if not isinstance(prices, list):
        raise ValueError("prices must be a JSON array")
    normalized: dict[str, float] = {}
    for row in prices:
        if not isinstance(row, Mapping):
            raise ValueError("price rows must be JSON objects")
        ticker = _normalize_ticker(str(row.get("ticker") or ""))
        value = row.get("current_price", row.get("price"))
        price = _finite_float(value)
        if price is None or price < 0:
            raise ValueError("current_price must be a non-negative number")
        normalized[ticker] = round(price, 4)
    return normalized


def _clean_text(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text[:max_length] if text else None


def _normalize_decision_status(value: Any) -> str:
    normalized = str(value or "watch").strip().lower()
    if normalized not in DECISION_STATUSES:
        raise ValueError("decision_status must be one of: watch, ready, pass, bought, sold")
    return normalized


def _normalize_review_priority(value: Any) -> str:
    normalized = str(value or "normal").strip().lower()
    if normalized not in REVIEW_PRIORITIES:
        raise ValueError("review_priority must be one of: high, normal, low")
    return normalized


def _finite_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _profile_bucket(store: dict[str, Any], profile: str) -> dict[str, Any]:
    profiles = store.setdefault("profiles", {})
    bucket = profiles.setdefault(profile, {"items": [], "updated_at": None})
    if not isinstance(bucket.get("items"), list):
        bucket["items"] = []
    if not isinstance(bucket.get("activity"), list):
        bucket["activity"] = []
    return bucket


def _load_store(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {"profiles": {}}
    try:
        payload = json.loads(path.read_text())
    except OSError as exc:
        raise ValueError("Review queue store could not be read") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Review queue store is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Review queue store root must be a JSON object")
    profiles = payload.get("profiles")
    if profiles is None:
        payload["profiles"] = {}
    elif not isinstance(profiles, dict):
        raise ValueError("Review queue store profiles must be a JSON object")
    return payload


def _write_store(path: Path, store: Mapping[str, Any]) -> None:
    write_json_atomic(path, store)


def _path(store_path: Path | None) -> Path:
    return store_path or STORE_PATH


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
