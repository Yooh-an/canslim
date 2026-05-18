"""Export screening results into TradingView operation artifacts.

The core screener should stay data-source agnostic. This module only converts an
already-generated CAN SLIM/SEPA result CSV into files that are easy to use with
TradingView Desktop/MCP workflows:

- a plain-symbol watchlist text file
- a JSON review/alert plan with trade levels and suggested MCP actions
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from numbers import Real
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

SUGGESTED_MCP_ACTIONS = [
    "chart_set_symbol",
    "chart_set_timeframe",
    "chart_manage_indicator",
    "capture_screenshot",
    "alert_create",
]

TRADE_PLAN_FIELDS = [
    "pivot_price",
    "buy_zone_low",
    "buy_zone_high",
    "stop_loss_price",
    "profit_target_low",
    "profit_target_high",
]

CONTEXT_FIELDS = [
    "canslim_score",
    "score_band",
    "rs_rating",
    "price_vs_52w_high",
    "breakout_volume_ratio",
    "base_depth_65d",
    "up_down_volume_ratio_50d",
    "avg_dollar_volume_50d",
    "in_buy_zone",
]


def export_tradingview_artifacts(config: Mapping[str, Any], limit: int | None = None) -> dict[str, Any]:
    """Write TradingView watchlist/review artifacts for the configured result CSV."""
    output_file = Path(config.get("data_paths", {}).get("output_file", "data/processed/results.csv"))
    if not output_file.exists():
        raise FileNotFoundError(f"Run screen mode first; result file does not exist: {output_file}")

    results = _read_results(output_file)
    candidates = _candidate_records(results, limit=limit)
    if not candidates:
        raise ValueError(f"No ticker rows found in screening result file: {output_file}")

    symbols = [candidate["ticker"] for candidate in candidates]
    watchlist_file = output_file.with_name(f"{output_file.stem}_tradingview_watchlist.txt")
    review_plan_file = output_file.with_name(f"{output_file.stem}_tradingview_review_plan.json")

    watchlist_file.write_text("\n".join(symbols) + "\n")
    review_plan_file.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "profile": config.get("profile_name", "default"),
                "source_file": str(output_file),
                "watchlist_file": str(watchlist_file),
                "candidate_count": len(candidates),
                "symbols": symbols,
                "workflow": [
                    "Import or add symbols to a TradingView watchlist.",
                    "Open each symbol on daily and weekly charts.",
                    "Check price action around pivot/buy-zone/stop levels.",
                    "Capture chart screenshots for manual review.",
                    "Create alerts from the alert_plan entries if the setup is still valid.",
                ],
                "candidates": candidates,
            },
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )

    return {
        "source_file": str(output_file),
        "watchlist_file": str(watchlist_file),
        "review_plan_file": str(review_plan_file),
        "symbols": symbols,
        "candidate_count": len(candidates),
    }


def _read_results(output_file: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(output_file)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"Screening result file is empty: {output_file}") from exc
    except pd.errors.ParserError as exc:
        raise ValueError(f"Screening result file is not a valid CSV: {output_file}") from exc


def _candidate_records(results: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if "ticker" not in results.columns:
        return []

    work = results.copy()
    work["ticker"] = work["ticker"].map(_normalize_ticker)
    work = work[work["ticker"] != ""]
    if work.empty:
        return []

    rows_by_ticker: dict[str, dict[str, Any]] = {}
    for row in work.to_dict(orient="records"):
        row["_sort_score"] = _score_value(row.get("canslim_score"))
        ticker = row["ticker"]
        existing = rows_by_ticker.get(ticker)
        if existing is None or row["_sort_score"] > existing["_sort_score"]:
            rows_by_ticker[ticker] = row

    rows = sorted(rows_by_ticker.values(), key=lambda row: (-row["_sort_score"], row["ticker"]))
    if limit is not None:
        rows = rows[:limit]

    return [_candidate_from_row(row) for row in rows]


def _candidate_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    ticker = str(row.get("ticker", "")).upper()
    trade_plan = {field: _json_value(row.get(field)) for field in TRADE_PLAN_FIELDS if _has_value(row.get(field))}
    context = {field: _json_value(row.get(field)) for field in CONTEXT_FIELDS if _has_value(row.get(field))}

    return {
        "ticker": ticker,
        "name": _json_value(row.get("name")),
        "tradingview_symbol": ticker,
        **context,
        "trade_plan": trade_plan,
        "suggested_mcp_actions": list(SUGGESTED_MCP_ACTIONS),
        "alert_plan": _alert_plan(ticker, trade_plan),
    }


def _alert_plan(ticker: str, trade_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    alerts = []
    for level_name in ["pivot_price", "buy_zone_low", "buy_zone_high", "stop_loss_price", "profit_target_low", "profit_target_high"]:
        value = trade_plan.get(level_name)
        if value is None:
            continue
        alerts.append(
            {
                "tool": "alert_create",
                "symbol": ticker,
                "level_name": level_name,
                "price": value,
                "message": f"{ticker} {level_name} {value}",
            }
        )
    return alerts


def _score_value(value: Any) -> float:
    if not _has_value(value):
        return float("-inf")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _normalize_ticker(value: Any) -> str:
    if not _has_value(value):
        return ""
    return str(value).strip().upper().replace(".", "-")


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, Real) and not isinstance(value, bool) and not math.isfinite(float(value)):
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _json_value(value: Any) -> Any:
    if not _has_value(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value
