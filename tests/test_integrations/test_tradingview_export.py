"""Tests for TradingView operation artifact export."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.integrations.tradingview_export import export_tradingview_artifacts


def _config(tmp_path: Path, output_file: Path) -> dict:
    return {
        "profile_name": "canslim_pure",
        "data_paths": {
            "processed_data_dir": str(tmp_path),
            "output_file": str(output_file),
        },
    }


def test_exports_watchlist_and_review_plan_sorted_by_score(tmp_path):
    results_file = tmp_path / "results_canslim_pure.csv"
    pd.DataFrame(
        [
            {
                "ticker": "low",
                "name": "Lower Score Inc",
                "canslim_score": 71.2,
                "score_band": "watch",
                "pivot_price": 50,
                "buy_zone_low": 50,
                "buy_zone_high": 52.5,
                "stop_loss_price": 46,
                "profit_target_low": 60,
                "profit_target_high": 62.5,
                "rs_rating": 81,
            },
            {
                "ticker": "strl",
                "name": "Sterling Infrastructure",
                "canslim_score": 92.68,
                "score_band": "exceptional",
                "pivot_price": 886.22,
                "buy_zone_low": 886.22,
                "buy_zone_high": 930.53,
                "stop_loss_price": 815.32,
                "profit_target_low": 1063.46,
                "profit_target_high": 1107.77,
                "rs_rating": 95.69,
                "in_buy_zone": True,
            },
        ]
    ).to_csv(results_file, index=False)

    summary = export_tradingview_artifacts(_config(tmp_path, results_file))

    watchlist_path = Path(summary["watchlist_file"])
    plan_path = Path(summary["review_plan_file"])
    assert watchlist_path.exists()
    assert plan_path.exists()
    assert watchlist_path.read_text().splitlines() == ["STRL", "LOW"]

    plan = json.loads(plan_path.read_text())
    assert plan["profile"] == "canslim_pure"
    assert plan["source_file"] == str(results_file)
    assert [candidate["ticker"] for candidate in plan["candidates"]] == ["STRL", "LOW"]
    assert plan["candidates"][0]["trade_plan"]["buy_zone_low"] == 886.22
    assert plan["candidates"][0]["suggested_mcp_actions"] == [
        "chart_set_symbol",
        "chart_set_timeframe",
        "chart_manage_indicator",
        "capture_screenshot",
        "alert_create",
    ]


def test_export_fails_clearly_when_results_file_is_missing(tmp_path):
    missing_file = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError, match="Run screen mode first"):
        export_tradingview_artifacts(_config(tmp_path, missing_file))


def test_export_ignores_blank_and_duplicate_tickers(tmp_path):
    results_file = tmp_path / "results.csv"
    pd.DataFrame(
        [
            {"ticker": "app", "canslim_score": 80},
            {"ticker": "APP", "canslim_score": 75},
            {"ticker": "", "canslim_score": 90},
        ]
    ).to_csv(results_file, index=False)

    summary = export_tradingview_artifacts(_config(tmp_path, results_file))

    assert summary["symbols"] == ["APP"]
    assert Path(summary["watchlist_file"]).read_text().splitlines() == ["APP"]


def test_export_writes_strict_json_when_metrics_are_infinite(tmp_path):
    results_file = tmp_path / "results.csv"
    pd.DataFrame(
        [
            {
                "ticker": "INFY",
                "canslim_score": 88,
                "up_down_volume_ratio_50d": float("inf"),
            }
        ]
    ).to_csv(results_file, index=False)

    summary = export_tradingview_artifacts(_config(tmp_path, results_file))
    plan_text = Path(summary["review_plan_file"]).read_text()

    def reject_nonstandard_json_constant(value):
        raise ValueError(value)

    plan = json.loads(plan_text, parse_constant=reject_nonstandard_json_constant)
    assert "up_down_volume_ratio_50d" not in plan["candidates"][0]
