"""Tests for the web review queue persistence layer."""

import csv
import datetime as dt
import io
import json
from pathlib import Path

import pytest

from src.web import review_store


def test_review_queue_persists_items_by_profile(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"

    pure = review_store.add_review_item(
        "canslim_pure",
        {
            "ticker": "brk.b",
            "name": "Berkshire Hathaway Inc.",
            "canslim_score": "88.5",
            "pivot_distance_pct": "-2.4",
            "buy_zone_low": None,
            "stop_loss_price": "410.25",
            "decision_status": "ready",
            "review_priority": "HIGH",
            "review_tags": ["Breakout Setup", "Breakout Setup", "=bad", "risk/reward"],
            "review_note": " Breakout volume confirmed. ",
        },
        store_path=store_path,
    )
    review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "IESC", "name": "IES Holdings", "canslim_score": 95.56},
        store_path=store_path,
    )

    assert pure["profile"] == "canslim_pure"
    assert pure["items"][0]["ticker"] == "BRK-B"
    assert pure["items"][0]["canslim_score"] == 88.5
    assert pure["items"][0]["stop_loss_price"] == 410.25
    assert pure["items"][0]["decision_status"] == "ready"
    assert pure["items"][0]["review_priority"] == "high"
    assert pure["items"][0]["review_tags"] == ["breakout-setup", "bad", "riskreward"]
    assert pure["items"][0]["review_note"] == "Breakout volume confirmed."
    assert "buy_zone_low" not in pure["items"][0]

    reloaded = review_store.get_review_queue("canslim_pure", store_path=store_path)
    assert [item["ticker"] for item in reloaded["items"]] == ["BRK-B"]
    assert json.loads(store_path.read_text())["profiles"]["canslim_score_rank"]["items"][0]["ticker"] == "IESC"


def test_review_queue_updates_and_removes_ticker(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_item("canslim_score_rank", {"ticker": "IESC", "name": "Old"}, store_path=store_path)
    review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "LINC", "name": "Lincoln"},
        store_path=store_path,
    )
    updated = review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "IESC", "name": "IES Holdings"},
        store_path=store_path,
    )

    assert [item["ticker"] for item in updated["items"]] == ["IESC", "LINC"]
    assert updated["items"][0]["name"] == "IES Holdings"

    removed = review_store.remove_review_item("canslim_score_rank", "IESC", store_path=store_path)
    assert [item["ticker"] for item in removed["items"]] == ["LINC"]

    cleared = review_store.clear_review_queue("canslim_score_rank", store_path=store_path)
    assert cleared["items"] == []


def test_review_queue_preserves_notes_when_market_snapshot_refreshes(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    initial = review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "IESC",
            "name": "IES Holdings",
            "decision_status": "ready",
            "review_note": "Wait for pivot confirmation.",
        },
        store_path=store_path,
    )
    refreshed = review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "IESC", "name": "IES Holdings, Inc.", "canslim_score": 95.56},
        store_path=store_path,
    )

    assert refreshed["items"][0]["added_at"] == initial["items"][0]["added_at"]
    assert refreshed["items"][0]["name"] == "IES Holdings, Inc."
    assert refreshed["items"][0]["canslim_score"] == 95.56
    assert refreshed["items"][0]["decision_status"] == "ready"
    assert refreshed["items"][0]["review_note"] == "Wait for pivot confirmation."
    assert refreshed["activity"][0]["action"] == "updated"
    assert "canslim_score" in refreshed["activity"][0]["changed_fields"]


def test_review_queue_allows_clearing_note(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "IESC", "review_note": "Old note"},
        store_path=store_path,
    )
    updated = review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "IESC", "review_note": ""},
        store_path=store_path,
    )

    assert updated["items"][0]["review_note"] == ""


def test_review_queue_allows_clearing_numeric_trade_levels(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "IESC", "buy_zone_low": 220, "stop_loss_price": 210},
        store_path=store_path,
    )
    updated = review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "IESC", "buy_zone_low": "", "stop_loss_price": None},
        store_path=store_path,
    )

    assert updated["items"][0]["buy_zone_low"] is None
    assert updated["items"][0]["stop_loss_price"] is None


def test_review_queue_bulk_adds_visible_candidates_preserving_existing_decisions(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    initial = review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "IESC", "decision_status": "ready", "review_note": "Keep note."},
        store_path=store_path,
    )

    bulk = review_store.add_review_items(
        "canslim_score_rank",
        [
            {"ticker": "LINC", "name": "Lincoln", "canslim_score": 91},
            {"ticker": "IESC", "name": "IES Holdings", "canslim_score": 95},
            {"ticker": "LINC", "name": "Duplicate"},
        ],
        store_path=store_path,
    )

    assert [item["ticker"] for item in bulk["items"]] == ["LINC", "IESC"]
    assert bulk["items"][0]["decision_status"] == "watch"
    assert bulk["items"][1]["added_at"] == initial["items"][0]["added_at"]
    assert bulk["items"][1]["decision_status"] == "ready"
    assert bulk["items"][1]["review_note"] == "Keep note."
    assert bulk["items"][1]["canslim_score"] == 95.0
    assert bulk["activity"][0]["action"] == "bulk_added"
    assert bulk["activity"][0]["added_count"] == 1
    assert bulk["activity"][0]["updated_count"] == 1


def test_review_queue_bulk_updates_and_removes_selected_items(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_items(
        "canslim_score_rank",
        [
            {"ticker": "IESC", "decision_status": "watch"},
            {"ticker": "LINC", "decision_status": "watch"},
            {"ticker": "MYRG", "decision_status": "ready"},
        ],
        store_path=store_path,
    )

    updated = review_store.bulk_update_review_items(
        "canslim_score_rank",
        ["IESC", "LINC", "IESC"],
        {"decision_status": "pass"},
        store_path=store_path,
    )

    statuses = {item["ticker"]: item["decision_status"] for item in updated["items"]}
    assert statuses == {"IESC": "pass", "LINC": "pass", "MYRG": "ready"}
    assert updated["activity"][0]["action"] == "bulk_updated"
    assert updated["activity"][0]["changed_fields"] == ["decision_status"]
    assert updated["activity"][0]["status"] == "pass"
    assert updated["activity"][0]["updated_count"] == 2
    assert [item["ticker"] for item in updated["activity"][0]["restorable_items"]] == ["IESC", "LINC"]
    assert [item["decision_status"] for item in updated["activity"][0]["restorable_items"]] == ["watch", "watch"]

    restored_update = review_store.restore_review_activity(
        "canslim_score_rank",
        updated["activity"][0]["at"],
        store_path=store_path,
    )
    assert {item["ticker"]: item["decision_status"] for item in restored_update["items"]} == {
        "IESC": "watch",
        "LINC": "watch",
        "MYRG": "ready",
    }
    assert restored_update["activity"][0]["action"] == "restored"
    assert restored_update["activity"][0]["source_action"] == "bulk_updated"
    assert restored_update["activity"][0]["restored_count"] == 2

    removed = review_store.bulk_remove_review_items(
        "canslim_score_rank",
        ["LINC", "MISSING"],
        store_path=store_path,
    )

    assert [item["ticker"] for item in removed["items"]] == ["IESC", "MYRG"]
    assert removed["activity"][0]["action"] == "bulk_removed"
    assert removed["activity"][0]["removed_count"] == 1


def test_review_queue_bulk_updates_priority_and_restores_items(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_items(
        "canslim_score_rank",
        [
            {"ticker": "IESC", "review_priority": "normal"},
            {"ticker": "LINC", "review_priority": "low"},
            {"ticker": "MYRG", "review_priority": "normal"},
        ],
        store_path=store_path,
    )

    updated = review_store.bulk_update_review_items(
        "canslim_score_rank",
        ["IESC", "LINC"],
        {"review_priority": "HIGH"},
        store_path=store_path,
    )

    priorities = {item["ticker"]: item["review_priority"] for item in updated["items"]}
    assert priorities == {"IESC": "high", "LINC": "high", "MYRG": "normal"}
    assert updated["activity"][0]["action"] == "bulk_updated"
    assert updated["activity"][0]["changed_fields"] == ["review_priority"]
    assert updated["activity"][0]["updated_count"] == 2
    assert [item["review_priority"] for item in updated["activity"][0]["restorable_items"]] == ["normal", "low"]

    restored = review_store.restore_review_activity(
        "canslim_score_rank",
        updated["activity"][0]["at"],
        store_path=store_path,
    )

    assert {item["ticker"]: item["review_priority"] for item in restored["items"]} == {
        "IESC": "normal",
        "LINC": "low",
        "MYRG": "normal",
    }
    assert restored["activity"][0]["source_action"] == "bulk_updated"


def test_review_queue_bulk_adds_and_replaces_tags_with_restore(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_items(
        "canslim_score_rank",
        [
            {"ticker": "IESC", "review_tags": ["leader"]},
            {"ticker": "LINC", "review_tags": "setup"},
            {"ticker": "MYRG", "review_tags": "keep"},
        ],
        store_path=store_path,
    )

    tagged = review_store.bulk_tag_review_items(
        "canslim_score_rank",
        ["IESC", "LINC"],
        "Leader, Ready List",
        store_path=store_path,
    )

    tags = {item["ticker"]: item["review_tags"] for item in tagged["items"]}
    assert tags == {
        "IESC": ["leader", "ready-list"],
        "LINC": ["setup", "leader", "ready-list"],
        "MYRG": ["keep"],
    }
    assert tagged["activity"][0]["action"] == "bulk_updated"
    assert tagged["activity"][0]["changed_fields"] == ["review_tags"]
    assert tagged["activity"][0]["updated_count"] == 2
    assert [item["review_tags"] for item in tagged["activity"][0]["restorable_items"]] == [
        ["leader"],
        ["setup"],
    ]

    restored = review_store.restore_review_activity(
        "canslim_score_rank",
        tagged["activity"][0]["at"],
        store_path=store_path,
    )
    assert {item["ticker"]: item["review_tags"] for item in restored["items"]} == {
        "IESC": ["leader"],
        "LINC": ["setup"],
        "MYRG": ["keep"],
    }

    replaced = review_store.bulk_tag_review_items(
        "canslim_score_rank",
        ["IESC", "LINC"],
        "exit-review",
        mode="replace",
        store_path=store_path,
    )

    assert {item["ticker"]: item["review_tags"] for item in replaced["items"]} == {
        "IESC": ["exit-review"],
        "LINC": ["exit-review"],
        "MYRG": ["keep"],
    }


def test_review_queue_bulk_updates_current_prices_with_restore(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_items(
        "canslim_score_rank",
        [
            {"ticker": "IESC", "decision_status": "bought", "current_price": 100},
            {"ticker": "LINC", "decision_status": "bought"},
            {"ticker": "MYRG", "decision_status": "watch", "current_price": 50},
        ],
        store_path=store_path,
    )

    updated = review_store.bulk_update_review_prices(
        "canslim_score_rank",
        [
            {"ticker": "IESC", "current_price": "106.12345"},
            {"ticker": "LINC", "price": 91},
            {"ticker": "MISSING", "current_price": 10},
        ],
        store_path=store_path,
    )

    prices = {item["ticker"]: item.get("current_price") for item in updated["items"]}
    assert prices == {"IESC": 106.1235, "LINC": 91.0, "MYRG": 50.0}
    assert updated["activity"][0]["action"] == "bulk_updated"
    assert updated["activity"][0]["changed_fields"] == ["current_price"]
    assert updated["activity"][0]["updated_count"] == 2
    assert [item.get("current_price") for item in updated["activity"][0]["restorable_items"]] == [100, None]

    restored = review_store.restore_review_activity(
        "canslim_score_rank",
        updated["activity"][0]["at"],
        store_path=store_path,
    )

    assert {item["ticker"]: item.get("current_price") for item in restored["items"]} == {
        "IESC": 100,
        "LINC": None,
        "MYRG": 50.0,
    }


def test_review_queue_bulk_status_defaults_lifecycle_dates_and_exit_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store_path = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_store, "_now", lambda: "2026-05-26T10:00:00+00:00")
    review_store.add_review_items(
        "canslim_score_rank",
        [
            {
                "ticker": "BUYME",
                "decision_status": "watch",
                "execution_price": 101,
                "execution_shares": 12,
            },
            {
                "ticker": "SELLME",
                "decision_status": "bought",
                "current_price": 115.5,
                "execution_price": 101,
                "execution_shares": 12,
            },
        ],
        store_path=store_path,
    )

    bought = review_store.bulk_update_review_items(
        "canslim_score_rank",
        ["BUYME"],
        {"decision_status": "bought"},
        store_path=store_path,
    )
    sold = review_store.bulk_update_review_items(
        "canslim_score_rank",
        ["SELLME"],
        {"decision_status": "sold"},
        store_path=store_path,
    )

    bought_item = next(item for item in bought["items"] if item["ticker"] == "BUYME")
    sold_item = next(item for item in sold["items"] if item["ticker"] == "SELLME")
    assert bought_item["decision_status"] == "bought"
    assert bought_item["executed_at"] == "2026-05-26"
    assert sold_item["decision_status"] == "sold"
    assert sold_item["exited_at"] == "2026-05-26"
    assert sold_item["exit_price"] == 115.5
    assert sold_item["exit_shares"] == 12
    assert set(sold["activity"][0]["changed_fields"]) == {
        "decision_status",
        "exited_at",
        "exit_price",
        "exit_shares",
    }
    assert "exited_at" not in sold["activity"][0]["restorable_items"][0]


def test_review_queue_replace_import_sanitizes_and_tracks_activity(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "OLD", "name": "Old"},
        store_path=store_path,
    )

    imported = review_store.replace_review_queue(
        "canslim_score_rank",
        [
            {
                "ticker": "iesc",
                "name": "IES Holdings",
                "decision_status": "ready",
                "review_note": " Imported note ",
                "buy_zone_low": "220",
                "stop_loss_price": "210",
            },
            {"ticker": "IESC", "name": "Duplicate is ignored"},
            {"ticker": "LINC", "name": "Lincoln"},
        ],
        store_path=store_path,
    )

    assert [item["ticker"] for item in imported["items"]] == ["IESC", "LINC"]
    assert imported["items"][0]["review_note"] == "Imported note"
    assert imported["items"][0]["buy_zone_low"] == 220.0
    assert imported["items"][1]["decision_status"] == "watch"
    assert imported["activity"][0]["action"] == "imported"
    assert imported["activity"][0]["imported_count"] == 2
    assert imported["activity"][0]["removed_count"] == 1


def test_review_queue_exports_csv_json_and_tickers(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "IESC",
            "name": "IES Holdings",
            "canslim_score": 95.56,
            "setup_status": "watchlist_pullback",
            "decision_status": "ready",
            "review_priority": "high",
            "review_tags": "breakout,leader",
            "review_note": "Confirm volume before entry.",
            "review_checks": {
                "weekly_chart": True,
                "daily_chart": True,
                "volume_confirmed": True,
                "market_aligned": False,
                "risk_defined": True,
                "ignored": True,
            },
            "buy_zone_low": 220.0,
            "buy_zone_high": 231.0,
            "stop_loss_price": 210.0,
        },
        store_path=store_path,
    )
    review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "LINC", "name": "Lincoln", "decision_status": "ready"},
        store_path=store_path,
    )

    risk = {"account_equity": 100000, "risk_pct": 0.5}
    csv_export = review_store.export_review_queue("canslim_score_rank", "csv", risk=risk, store_path=store_path)
    rows = list(csv.DictReader(io.StringIO(csv_export["body"])))
    assert csv_export["filename"] == "canslim-review-canslim_score_rank.csv"
    assert csv_export["content_type"] == "text/csv; charset=utf-8"
    assert rows[0]["ticker"] == "LINC"
    assert rows[0]["risk_amount"] == "500.0"
    assert rows[0]["planned_shares"] == ""
    assert rows[0]["readiness_status"] == "blocked"
    assert rows[0]["readiness_blockers"] == "checklist_incomplete,missing_position_size"
    assert rows[1]["ticker"] == "IESC"
    assert rows[1]["decision_status"] == "ready"
    assert rows[1]["review_priority"] == "high"
    assert rows[1]["review_tags"] == "breakout,leader"
    assert rows[1]["review_note"] == "Confirm volume before entry."
    assert rows[1]["checklist_complete"] == "False"
    assert rows[1]["checklist_complete_count"] == "4"
    assert rows[1]["checklist_total_count"] == "5"
    assert rows[1]["readiness_status"] == "blocked"
    assert rows[1]["readiness_blockers"] == "checklist_incomplete"
    assert rows[1]["buy_zone_low"] == "220.0"
    assert rows[1]["risk_amount"] == "500.0"
    assert rows[1]["risk_per_share"] == "10.0"
    assert rows[1]["planned_shares"] == "50"
    assert rows[1]["planned_capital"] == "11000.0"

    json_export = review_store.export_review_queue("canslim_score_rank", "json", risk=risk, store_path=store_path)
    payload = json.loads(json_export["body"])
    assert json_export["filename"] == "canslim-review-canslim_score_rank.json"
    assert payload["profile"] == "canslim_score_rank"
    assert payload["research_disclosure"]["title"] == "Research aid only"
    assert payload["risk"] == {
        "account_equity": 100000.0,
        "risk_pct": 0.5,
        "max_capital_pct": 80,
        "max_queue_risk_pct": 5,
        "max_open_position_risk_pct": 6,
        "max_concentration_pct": 60,
        "max_open_concentration_pct": 60,
    }
    assert payload["activity"][0]["action"] == "added"
    assert [item["ticker"] for item in payload["items"]] == ["LINC", "IESC"]
    assert payload["items"][1]["setup_status"] == "watchlist_pullback"
    assert payload["items"][1]["planned_shares"] == 50
    assert payload["items"][1]["review_tags"] == ["breakout", "leader"]
    assert payload["items"][1]["review_checks"] == {
        "weekly_chart": True,
        "daily_chart": True,
        "volume_confirmed": True,
        "market_aligned": False,
        "risk_defined": True,
    }
    assert payload["items"][1]["checklist_complete"] is False
    assert payload["items"][1]["readiness_status"] == "blocked"
    assert payload["items"][1]["readiness_blockers"] == "checklist_incomplete"

    ticker_export = review_store.export_review_queue("canslim_score_rank", "tickers", risk=risk, store_path=store_path)
    assert ticker_export["format"] == "txt"
    assert ticker_export["filename"] == "canslim-review-canslim_score_rank.txt"
    assert ticker_export["body"] == "LINC\nIESC\n"

    tradingview_export = review_store.export_review_queue(
        "canslim_score_rank",
        "tradingview",
        risk=risk,
        store_path=store_path,
    )
    tradingview_payload = json.loads(tradingview_export["body"])
    assert tradingview_export["filename"] == "canslim-tradingview-review-canslim_score_rank.json"
    assert tradingview_export["content_type"] == "application/json; charset=utf-8"
    assert tradingview_payload["source"] == "web_review_queue"
    assert tradingview_payload["research_disclosure"]["title"] == "Research aid only"
    assert tradingview_payload["symbols"] == ["LINC", "IESC"]
    assert tradingview_payload["candidates"][0]["alert_plan"] == []
    assert tradingview_payload["candidates"][0]["trade_readiness"] == {
        "status": "blocked",
        "blockers": ["checklist_incomplete", "missing_position_size"],
    }
    assert tradingview_payload["candidates"][1]["ticker"] == "IESC"
    assert tradingview_payload["candidates"][1]["decision_status"] == "ready"
    assert tradingview_payload["candidates"][1]["review_priority"] == "high"
    assert tradingview_payload["candidates"][1]["review_tags"] == ["breakout", "leader"]
    assert tradingview_payload["candidates"][1]["review_note"] == "Confirm volume before entry."
    assert tradingview_payload["candidates"][1]["review_checklist"]["risk_defined"] is True
    assert tradingview_payload["candidates"][1]["checklist_complete"] is False
    assert tradingview_payload["candidates"][1]["trade_readiness"] == {
        "status": "blocked",
        "blockers": ["checklist_incomplete"],
    }
    assert tradingview_payload["candidates"][1]["trade_plan"] == {
        "buy_zone_low": 220.0,
        "buy_zone_high": 231.0,
        "stop_loss_price": 210.0,
    }
    assert [alert["level_name"] for alert in tradingview_payload["candidates"][1]["alert_plan"]] == [
        "buy_zone_low",
        "buy_zone_high",
        "stop_loss_price",
    ]

    filtered_csv_export = review_store.export_review_queue(
        "canslim_score_rank",
        "csv",
        risk=risk,
        filters={"status": "ready", "priority": "high"},
        store_path=store_path,
    )
    filtered_rows = list(csv.DictReader(io.StringIO(filtered_csv_export["body"])))
    assert filtered_csv_export["filename"] == "canslim-review-canslim_score_rank-ready-high.csv"
    assert filtered_csv_export["filters"] == {"status": "ready", "priority": "high"}
    assert [row["ticker"] for row in filtered_rows] == ["IESC"]

    tagged_export = review_store.export_review_queue(
        "canslim_score_rank",
        "tickers",
        risk=risk,
        filters={"tag": "leader"},
        store_path=store_path,
    )
    assert tagged_export["filename"] == "canslim-review-canslim_score_rank-leader.txt"
    assert tagged_export["filters"] == {"tag": "leader"}
    assert tagged_export["body"] == "IESC\n"

    filtered_json_export = review_store.export_review_queue(
        "canslim_score_rank",
        "json",
        risk=risk,
        filters={"status": "ready"},
        store_path=store_path,
    )
    filtered_payload = json.loads(filtered_json_export["body"])
    assert filtered_json_export["filename"] == "canslim-review-canslim_score_rank-ready.json"
    assert filtered_payload["filters"] == {"status": "ready"}
    assert [item["ticker"] for item in filtered_payload["items"]] == ["LINC", "IESC"]

    searched_export = review_store.export_review_queue(
        "canslim_score_rank",
        "tickers",
        risk=risk,
        filters={"query": "ies"},
        store_path=store_path,
    )
    assert searched_export["filename"] == "canslim-review-canslim_score_rank-search.txt"
    assert searched_export["filters"] == {"query": "ies"}
    assert searched_export["body"] == "IESC\n"

    selected_export = review_store.export_review_queue(
        "canslim_score_rank",
        "tickers",
        risk=risk,
        filters={"tickers": ["IESC"]},
        store_path=store_path,
    )
    assert selected_export["filename"] == "canslim-review-canslim_score_rank-selected.txt"
    assert selected_export["filters"] == {"tickers": ["IESC"]}
    assert selected_export["body"] == "IESC\n"


def test_review_queue_csv_export_escapes_formula_like_text(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "SAFE",
            "name": '=HYPERLINK("https://example.com")',
            "decision_status": "watch",
            "review_note": "+SUM(1,2)",
            "pivot_distance_pct": -2.4,
        },
        store_path=store_path,
    )

    risk = {"account_equity": 100000, "risk_pct": 0.5}
    csv_export = review_store.export_review_queue("canslim_score_rank", "csv", risk=risk, store_path=store_path)
    row = next(csv.DictReader(io.StringIO(csv_export["body"])))

    assert row["name"] == '\'=HYPERLINK("https://example.com")'
    assert row["review_note"] == "'+SUM(1,2)"
    assert row["pivot_distance_pct"] == "-2.4"

    json_export = review_store.export_review_queue("canslim_score_rank", "json", risk=risk, store_path=store_path)
    payload = json.loads(json_export["body"])
    assert payload["items"][0]["name"] == '=HYPERLINK("https://example.com")'
    assert payload["items"][0]["review_note"] == "+SUM(1,2)"


def test_review_queue_records_bought_execution_details(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "EXEC",
            "name": "Executed Position",
            "decision_status": "bought",
            "current_price": 107.25,
            "buy_zone_low": 100.0,
            "stop_loss_price": 94.0,
            "execution_price": "101.25",
            "execution_shares": "12",
            "executed_at": "2026-05-26",
        },
        store_path=store_path,
    )
    review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "MISS", "decision_status": "bought"},
        store_path=store_path,
    )

    queue = review_store.get_review_queue("canslim_score_rank", store_path=store_path)
    assert queue["items"][1]["execution_price"] == 101.25
    assert queue["items"][1]["execution_shares"] == 12
    assert queue["items"][1]["executed_at"] == "2026-05-26"

    risk = {"account_equity": 100000, "risk_pct": 0.5}
    summary = review_store.get_review_summary("canslim_score_rank", risk=risk, store_path=store_path)
    assert summary["executed_items"] == 1
    assert summary["monitored_positions"] == 1
    assert summary["bought_execution_missing"] == 1
    assert summary["total_execution_value"] == 1215.0
    assert summary["total_position_pnl"] == 72.0
    assert summary["total_position_pnl_pct"] == 5.93
    assert summary["open_position_risk"] == {
        "position_count": 1,
        "monitored_count": 1,
        "stop_covered_count": 1,
        "missing_current_price_count": 0,
        "missing_stop_loss_count": 0,
        "total_market_value": 1287.0,
        "market_value_pct": 1.29,
        "total_stop_risk": 159.0,
        "stop_risk_pct": 0.16,
        "average_stop_distance_pct": 12.35,
        "stop_coverage_pct": 100.0,
        "largest_stop_risk_items": [
            {
                "ticker": "EXEC",
                "name": "Executed Position",
                "market_value": 1287.0,
                "stop_risk_amount": 159.0,
                "stop_distance_pct": 12.35,
                "position_pnl": 72.0,
                "position_pnl_pct": 5.93,
                "alert_status": "ok",
            }
        ],
    }
    assert summary["position_alert_counts"] == {
        "ok": 1,
        "stop_breached": 0,
        "near_stop": 0,
        "missing_current_price": 0,
        "missing_stop_loss": 0,
    }
    assert summary["open_position_alert_counts"] == {
        "ok": 1,
        "stop_breached": 0,
        "near_stop": 0,
        "missing_current_price": 0,
        "missing_stop_loss": 0,
    }
    assert summary["position_alert_items"] == []
    assert summary["acknowledged_position_alerts"] == 0
    assert "1 bought review item(s) are missing execution records" in summary["warnings"]

    json_export = review_store.export_review_queue("canslim_score_rank", "json", risk=risk, store_path=store_path)
    payload = json.loads(json_export["body"])
    executed = next(item for item in payload["items"] if item["ticker"] == "EXEC")
    missing = next(item for item in payload["items"] if item["ticker"] == "MISS")
    assert executed["readiness_status"] == "bought"
    assert executed["execution_status"] == "recorded"
    assert executed["execution_value"] == 1215.0
    assert executed["position_last_price"] == 107.25
    assert executed["position_pnl"] == 72.0
    assert executed["position_pnl_pct"] == 5.93
    assert executed["position_r_multiple"] == 0.83
    assert executed["stop_distance_pct"] == 12.35
    assert executed["position_alert_status"] == "ok"
    assert executed["position_alert_reason"] == ""
    assert missing["execution_status"] == "missing"
    assert missing["execution_blockers"] == "missing_execution_price,missing_execution_shares"

    tradingview_export = review_store.export_review_queue(
        "canslim_score_rank",
        "tradingview",
        risk=risk,
        store_path=store_path,
    )
    tradingview_payload = json.loads(tradingview_export["body"])
    executed_plan = next(candidate for candidate in tradingview_payload["candidates"] if candidate["ticker"] == "EXEC")
    assert executed_plan["execution"] == {
        "status": "recorded",
        "blockers": [],
        "price": 101.25,
        "shares": 12,
        "value": 1215.0,
        "last_price": 107.25,
        "pnl": 72.0,
        "pnl_pct": 5.93,
        "r_multiple": 0.83,
        "stop_distance_pct": 12.35,
        "alert_status": "ok",
        "alert_reason": "",
        "alert_signature": "",
        "alert_acknowledged": False,
        "alert_acknowledged_at": "",
        "executed_at": "2026-05-26",
        "exit": {
            "status": "not_applicable",
            "blockers": [],
            "price": None,
            "shares": None,
            "value": None,
            "realized_pnl": None,
            "realized_pnl_pct": None,
            "realized_r_multiple": None,
            "reason": "",
            "exited_at": "",
        },
    }


def test_review_summary_flags_position_stop_alerts(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    positions = [
        {
            "ticker": "BREACH",
            "name": "Stop Breach",
            "decision_status": "bought",
            "current_price": 93.5,
            "buy_zone_low": 100.0,
            "stop_loss_price": 94.0,
            "execution_price": 100.0,
            "execution_shares": 10,
        },
        {
            "ticker": "NEAR",
            "name": "Near Stop",
            "decision_status": "bought",
            "current_price": 96.0,
            "buy_zone_low": 100.0,
            "stop_loss_price": 94.0,
            "execution_price": 100.0,
            "execution_shares": 5,
        },
        {
            "ticker": "NOPRICE",
            "name": "No Current Price",
            "decision_status": "bought",
            "buy_zone_low": 100.0,
            "stop_loss_price": 94.0,
            "execution_price": 100.0,
            "execution_shares": 3,
        },
        {
            "ticker": "NOSTOP",
            "name": "No Stop",
            "decision_status": "bought",
            "current_price": 105.0,
            "buy_zone_low": 100.0,
            "execution_price": 100.0,
            "execution_shares": 2,
        },
        {
            "ticker": "OKPOS",
            "name": "Healthy Position",
            "decision_status": "bought",
            "current_price": 110.0,
            "buy_zone_low": 100.0,
            "stop_loss_price": 94.0,
            "execution_price": 100.0,
            "execution_shares": 1,
        },
    ]
    for position in positions:
        review_store.add_review_item("canslim_score_rank", position, store_path=store_path)

    risk = {"account_equity": 100000, "risk_pct": 0.5}
    summary = review_store.get_review_summary("canslim_score_rank", risk=risk, store_path=store_path)

    assert summary["executed_items"] == 5
    assert summary["monitored_positions"] == 4
    assert summary["position_alert_distance_pct"] == 3.0
    assert summary["position_alert_counts"] == {
        "ok": 1,
        "stop_breached": 1,
        "near_stop": 1,
        "missing_current_price": 1,
        "missing_stop_loss": 1,
    }
    assert summary["open_position_alert_counts"] == {
        "ok": 1,
        "stop_breached": 1,
        "near_stop": 1,
        "missing_current_price": 1,
        "missing_stop_loss": 1,
    }
    assert summary["open_position_alerts"] == 4
    assert summary["acknowledged_position_alerts"] == 0
    assert [item["ticker"] for item in summary["position_alert_items"]] == [
        "BREACH",
        "NEAR",
        "NOPRICE",
        "NOSTOP",
    ]
    assert summary["position_alert_items"][0]["alert_status"] == "stop_breached"
    assert summary["position_alert_items"][0]["stop_distance_pct"] == -0.53
    assert summary["position_alert_items"][1]["alert_status"] == "near_stop"
    assert summary["position_alert_items"][1]["stop_distance_pct"] == 2.08
    assert summary["open_position_risk"]["position_count"] == 5
    assert summary["open_position_risk"]["monitored_count"] == 4
    assert summary["open_position_risk"]["stop_covered_count"] == 3
    assert summary["open_position_risk"]["missing_current_price_count"] == 1
    assert summary["open_position_risk"]["missing_stop_loss_count"] == 1
    assert summary["open_position_risk"]["total_market_value"] == 1735.0
    assert summary["open_position_risk"]["market_value_pct"] == 1.74
    assert summary["open_position_risk"]["total_stop_risk"] == 26.0
    assert summary["open_position_risk"]["stop_risk_pct"] == 0.03
    assert summary["open_position_risk"]["average_stop_distance_pct"] == 1.38
    assert summary["open_position_risk"]["stop_coverage_pct"] == 60.0
    assert [item["ticker"] for item in summary["open_position_risk"]["largest_stop_risk_items"]] == [
        "OKPOS",
        "NEAR",
        "BREACH",
    ]
    assert summary["warnings"] == [
        "1 active review item(s) are missing buy or stop levels",
        "1 bought position(s) are at or below stop loss",
        "1 bought position(s) are within 3% of stop loss",
        "1 executed bought position(s) are missing current prices",
        "1 executed bought position(s) are missing stop levels",
    ]
    assert [action["label"] for action in summary["risk_actions"][:5]] == [
        "Stop breached",
        "Near stop",
        "Refresh open prices",
        "Add open stops",
        "Complete trade plans",
    ]
    assert summary["risk_actions"][0] == {
        "severity": "critical",
        "category": "position_alert",
        "label": "Stop breached",
        "detail": "1 bought position(s) are at or below stop loss",
        "action": "review_exit",
        "tickers": ["BREACH"],
        "count": 1,
    }

    payload = json.loads(
        review_store.export_review_queue("canslim_score_rank", "json", risk=risk, store_path=store_path)["body"]
    )
    breach = next(item for item in payload["items"] if item["ticker"] == "BREACH")
    near = next(item for item in payload["items"] if item["ticker"] == "NEAR")
    no_price = next(item for item in payload["items"] if item["ticker"] == "NOPRICE")
    no_stop = next(item for item in payload["items"] if item["ticker"] == "NOSTOP")
    assert breach["position_alert_status"] == "stop_breached"
    assert breach["position_alert_reason"] == "last price is at or below stop loss"
    assert breach["position_pnl"] == -65.0
    assert breach["position_r_multiple"] == -1.08
    assert near["position_alert_status"] == "near_stop"
    assert near["position_alert_reason"] == "last price is within 3% of stop loss"
    assert no_price["position_alert_status"] == "missing_current_price"
    assert no_price["position_alert_reason"] == "current price unavailable"
    assert no_stop["position_alert_status"] == "missing_stop_loss"
    assert no_stop["position_alert_reason"] == "stop loss unavailable"

    tradingview_payload = json.loads(
        review_store.export_review_queue("canslim_score_rank", "tradingview", risk=risk, store_path=store_path)["body"]
    )
    tv_breach = next(candidate for candidate in tradingview_payload["candidates"] if candidate["ticker"] == "BREACH")
    assert tv_breach["execution"]["alert_status"] == "stop_breached"
    assert tv_breach["execution"]["alert_reason"] == "last price is at or below stop loss"
    assert tv_breach["execution"]["alert_acknowledged"] is False


def test_review_queue_manual_current_price_clears_missing_price_alert(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "NOPRICE",
            "decision_status": "bought",
            "buy_zone_low": 100.0,
            "stop_loss_price": 94.0,
            "execution_price": 100.0,
            "execution_shares": 3,
        },
        store_path=store_path,
    )

    risk = {"account_equity": 100000, "risk_pct": 0.5}
    missing = review_store.get_review_summary("canslim_score_rank", risk=risk, store_path=store_path)
    assert missing["position_alert_counts"]["missing_current_price"] == 1
    assert missing["open_position_risk"]["missing_current_price_count"] == 1

    updated = review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "NOPRICE", "current_price": 106.0},
        store_path=store_path,
    )
    item = updated["items"][0]
    assert item["decision_status"] == "bought"
    assert item["current_price"] == 106.0

    summary = review_store.get_review_summary("canslim_score_rank", risk=risk, store_path=store_path)
    assert summary["position_alert_counts"]["missing_current_price"] == 0
    assert summary["position_alert_counts"]["ok"] == 1
    assert summary["open_position_risk"]["missing_current_price_count"] == 0
    assert summary["open_position_risk"]["total_market_value"] == 318.0
    assert summary["total_position_pnl"] == 18.0


def test_review_summary_reports_open_position_concentration(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    positions = [
        {
            "ticker": "TECH1",
            "name": "Tech Leader",
            "sector": "Technology",
            "setup_status": "near pivot",
            "decision_status": "bought",
            "current_price": 100.0,
            "buy_zone_low": 94.0,
            "stop_loss_price": 90.0,
            "execution_price": 92.0,
            "execution_shares": 100,
        },
        {
            "ticker": "TECH2",
            "name": "Tech Follow Through",
            "sector": "Technology",
            "setup_status": "near pivot",
            "decision_status": "bought",
            "current_price": 50.0,
            "buy_zone_low": 47.0,
            "stop_loss_price": 45.0,
            "execution_price": 46.0,
            "execution_shares": 100,
        },
        {
            "ticker": "HEALTH",
            "name": "Healthcare Base",
            "sector": "Healthcare",
            "setup_status": "forming base",
            "decision_status": "bought",
            "current_price": 100.0,
            "buy_zone_low": 94.0,
            "stop_loss_price": 90.0,
            "execution_price": 92.0,
            "execution_shares": 50,
        },
        {
            "ticker": "STALE",
            "name": "Stale Price Tech",
            "sector": "Technology",
            "setup_status": "near pivot",
            "decision_status": "bought",
            "buy_zone_low": 25.0,
            "stop_loss_price": 23.0,
            "execution_price": 24.0,
            "execution_shares": 25,
        },
    ]
    for position in positions:
        review_store.add_review_item("canslim_score_rank", position, store_path=store_path)

    summary = review_store.get_review_summary(
        "canslim_score_rank",
        risk={"account_equity": 100000, "risk_pct": 0.5},
        store_path=store_path,
    )

    concentration = summary["open_position_concentration"]
    assert concentration["top_sector"]["label"] == "Technology"
    assert concentration["top_sector"]["count"] == 3
    assert concentration["top_sector"]["priced_count"] == 2
    assert concentration["top_sector"]["stop_covered_count"] == 2
    assert concentration["top_sector"]["market_value"] == 15000.0
    assert concentration["top_sector"]["stop_risk_amount"] == 1500.0
    assert concentration["top_sector"]["share_of_market_value_pct"] == 75.0
    assert concentration["top_sector"]["share_of_stop_risk_pct"] == 75.0
    assert concentration["top_sector"]["market_value_pct"] == 15.0
    assert concentration["top_sector"]["stop_risk_pct"] == 1.5
    assert set(concentration["top_sector"]["tickers"]) == {"TECH1", "TECH2", "STALE"}
    assert concentration["top_setup"]["label"] == "near pivot"
    assert concentration["top_setup"]["share_of_market_value_pct"] == 75.0
    assert "open sector concentration: Technology is 75% of open market value" in concentration["warnings"]
    assert "open setup concentration: near pivot is 75% of open market value" in concentration["warnings"]
    assert "open sector concentration: Technology is 75% of open market value" in summary["warnings"]
    assert "open setup concentration: near pivot is 75% of open market value" in summary["warnings"]
    assert next(action for action in summary["risk_actions"] if action["label"] == "Refresh open prices")[
        "tickers"
    ] == ["STALE"]
    sector_action = next(action for action in summary["risk_actions"] if action["label"] == "Open sector concentration")
    assert sector_action == {
        "severity": "warning",
        "category": "concentration",
        "label": "Open sector concentration",
        "detail": "Technology is 75% of open market value",
        "action": "rebalance_open",
        "tickers": concentration["top_sector"]["tickers"],
        "count": 2,
        "amount": 15000.0,
    }
    setup_action = next(action for action in summary["risk_actions"] if action["label"] == "Open setup concentration")
    assert setup_action == {
        "severity": "warning",
        "category": "concentration",
        "label": "Open setup concentration",
        "detail": "near pivot is 75% of open market value",
        "action": "rebalance_open",
        "tickers": concentration["top_setup"]["tickers"],
        "count": 2,
        "amount": 15000.0,
    }

    loose = review_store.get_review_summary(
        "canslim_score_rank",
        risk={"account_equity": 100000, "risk_pct": 0.5, "max_open_concentration_pct": 80},
        store_path=store_path,
    )
    assert loose["open_position_concentration"]["warning_share_pct"] == 80.0
    assert loose["open_position_concentration"]["warnings"] == []
    assert "open sector concentration: Technology is 75% of open market value" not in loose["warnings"]
    assert not [action for action in loose["risk_actions"] if action["label"].startswith("Open")]


def test_review_position_alert_acknowledgement_suppresses_open_alert(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "ACKSTOP",
            "name": "Acknowledged Stop",
            "decision_status": "bought",
            "current_price": 93.5,
            "buy_zone_low": 100.0,
            "stop_loss_price": 94.0,
            "execution_price": 100.0,
            "execution_shares": 10,
        },
        store_path=store_path,
    )
    risk = {"account_equity": 100000, "risk_pct": 0.5}
    initial_export = json.loads(
        review_store.export_review_queue("canslim_score_rank", "json", risk=risk, store_path=store_path)["body"]
    )
    alert_signature = initial_export["items"][0]["position_alert_signature"]
    assert alert_signature == "stop_breached|93.50|94.00"

    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "ACKSTOP",
            "position_alert_ack_signature": alert_signature,
            "position_alert_acknowledged_at": "2026-05-26T10:00:00+00:00",
        },
        store_path=store_path,
    )

    summary = review_store.get_review_summary("canslim_score_rank", risk=risk, store_path=store_path)
    assert summary["position_alert_counts"]["stop_breached"] == 1
    assert summary["open_position_alert_counts"]["stop_breached"] == 0
    assert summary["open_position_alerts"] == 0
    assert summary["acknowledged_position_alerts"] == 1
    assert summary["position_alert_items"] == []
    assert summary["acknowledged_position_alert_items"][0]["ticker"] == "ACKSTOP"
    assert "1 bought position(s) are at or below stop loss" not in summary["warnings"]

    acknowledged_export = json.loads(
        review_store.export_review_queue("canslim_score_rank", "json", risk=risk, store_path=store_path)["body"]
    )
    acknowledged = acknowledged_export["items"][0]
    assert acknowledged["position_alert_status"] == "stop_breached"
    assert acknowledged["position_alert_acknowledged"] is True
    assert acknowledged["position_alert_acknowledged_at"] == "2026-05-26T10:00:00+00:00"

    review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "ACKSTOP", "current_price": 92.0},
        store_path=store_path,
    )
    changed = review_store.get_review_summary("canslim_score_rank", risk=risk, store_path=store_path)
    assert changed["position_alert_counts"]["stop_breached"] == 1
    assert changed["open_position_alert_counts"]["stop_breached"] == 1
    assert changed["open_position_alerts"] == 1

    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "ACKSTOP",
            "position_alert_ack_signature": "",
            "position_alert_acknowledged_at": "",
        },
        store_path=store_path,
    )
    reopened = review_store.get_review_summary("canslim_score_rank", risk=risk, store_path=store_path)
    assert reopened["position_alert_counts"]["stop_breached"] == 1
    assert reopened["open_position_alert_counts"]["stop_breached"] == 1
    assert reopened["open_position_alerts"] == 1
    assert reopened["acknowledged_position_alerts"] == 0
    assert reopened["position_alert_items"][0]["ticker"] == "ACKSTOP"


def test_review_queue_records_sold_exit_and_realized_pnl(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "SOLDOK",
            "name": "Closed Winner",
            "decision_status": "sold",
            "current_price": 120.0,
            "buy_zone_low": 100.0,
            "stop_loss_price": 94.0,
            "execution_price": 101.25,
            "execution_shares": 12,
            "executed_at": "2026-05-01",
            "exit_price": 115.5,
            "exited_at": "2026-05-26",
            "exit_reason": "Target trim",
        },
        store_path=store_path,
    )
    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "SOLDMISS",
            "name": "Missing Exit",
            "decision_status": "sold",
        },
        store_path=store_path,
    )

    risk = {"account_equity": 100000, "risk_pct": 0.5}
    summary = review_store.get_review_summary("canslim_score_rank", risk=risk, store_path=store_path)

    assert summary["total_items"] == 2
    assert summary["active_items"] == 0
    assert summary["sized_items"] == 0
    assert summary["closed_items"] == 2
    assert summary["realized_items"] == 1
    assert summary["sold_exit_missing"] == 1
    assert summary["total_exit_value"] == 1386.0
    assert summary["total_realized_pnl"] == 171.0
    assert summary["total_realized_pnl_pct"] == 14.07
    assert summary["status_counts"]["sold"] == 2
    assert summary["total_risk_amount"] == 0
    assert summary["total_planned_capital"] == 0
    assert "1 sold review item(s) are missing exit records" in summary["warnings"]

    payload = json.loads(
        review_store.export_review_queue("canslim_score_rank", "json", risk=risk, store_path=store_path)["body"]
    )
    sold = next(item for item in payload["items"] if item["ticker"] == "SOLDOK")
    missing = next(item for item in payload["items"] if item["ticker"] == "SOLDMISS")
    assert sold["readiness_status"] == "inactive"
    assert sold["execution_status"] == "recorded"
    assert sold["position_pnl"] == ""
    assert sold["exit_status"] == "recorded"
    assert sold["exit_shares"] == 12
    assert sold["exit_value"] == 1386.0
    assert sold["realized_pnl"] == 171.0
    assert sold["realized_pnl_pct"] == 14.07
    assert sold["realized_r_multiple"] == 1.97
    assert sold["exit_reason"] == "Target trim"
    assert missing["exit_status"] == "missing"
    assert missing["exit_blockers"] == "missing_exit_price,missing_execution_price,missing_exit_shares"

    tradingview_payload = json.loads(
        review_store.export_review_queue("canslim_score_rank", "tradingview", risk=risk, store_path=store_path)["body"]
    )
    sold_plan = next(candidate for candidate in tradingview_payload["candidates"] if candidate["ticker"] == "SOLDOK")
    assert sold_plan["execution"]["exit"] == {
        "status": "recorded",
        "blockers": [],
        "price": 115.5,
        "shares": 12,
        "value": 1386.0,
        "realized_pnl": 171.0,
        "realized_pnl_pct": 14.07,
        "realized_r_multiple": 1.97,
        "reason": "Target trim",
        "exited_at": "2026-05-26",
    }


def test_review_summary_reports_realized_performance_journal(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    positions = [
        {
            "ticker": "WINR",
            "name": "Winner",
            "decision_status": "sold",
            "buy_zone_low": 100.0,
            "stop_loss_price": 94.0,
            "execution_price": 101.0,
            "execution_shares": 10,
            "exit_price": 115.0,
            "exit_shares": 10,
            "exit_reason": "Target hit",
            "exited_at": "2026-05-20",
        },
        {
            "ticker": "LOSS",
            "name": "Loser",
            "decision_status": "sold",
            "buy_zone_low": 100.0,
            "stop_loss_price": 94.0,
            "execution_price": 100.0,
            "execution_shares": 5,
            "exit_price": 95.0,
            "exit_shares": 5,
            "exit_reason": "Stopped",
            "exited_at": "2026-05-21",
        },
        {
            "ticker": "FLAT",
            "name": "Scratch",
            "decision_status": "sold",
            "buy_zone_low": 100.0,
            "stop_loss_price": 94.0,
            "execution_price": 100.0,
            "execution_shares": 4,
            "exit_price": 100.0,
            "exit_shares": 4,
            "exit_reason": "No follow-through",
            "exited_at": "2026-05-22",
        },
    ]
    for position in positions:
        review_store.add_review_item("canslim_score_rank", position, store_path=store_path)

    summary = review_store.get_review_summary(
        "canslim_score_rank",
        risk={"account_equity": 100000, "risk_pct": 0.5},
        store_path=store_path,
    )

    assert summary["realized_items"] == 3
    assert summary["total_realized_pnl"] == 115.0
    assert summary["realized_performance"] == {
        "trade_count": 3,
        "winners": 1,
        "losers": 1,
        "flat": 1,
        "win_rate_pct": 33.33,
        "average_realized_pnl": 38.33,
        "average_realized_r": 0.39,
        "average_winner_pnl": 140.0,
        "average_loser_pnl": -25.0,
        "expectancy_pnl": 38.33,
        "expectancy_r": 0.39,
        "profit_factor": 5.6,
        "payoff_ratio": 5.6,
        "max_drawdown": 25.0,
        "max_drawdown_pct": 17.86,
        "cumulative_pnl_curve": [
            {
                "ticker": "WINR",
                "name": "Winner",
                "realized_pnl": 140.0,
                "realized_pnl_pct": 13.86,
                "realized_r_multiple": 2.0,
                "exit_reason": "Target hit",
                "exited_at": "2026-05-20",
                "cumulative_pnl": 140.0,
                "drawdown": 0.0,
            },
            {
                "ticker": "LOSS",
                "name": "Loser",
                "realized_pnl": -25.0,
                "realized_pnl_pct": -5.0,
                "realized_r_multiple": -0.83,
                "exit_reason": "Stopped",
                "exited_at": "2026-05-21",
                "cumulative_pnl": 115.0,
                "drawdown": 25.0,
            },
            {
                "ticker": "FLAT",
                "name": "Scratch",
                "realized_pnl": 0.0,
                "realized_pnl_pct": 0.0,
                "realized_r_multiple": 0.0,
                "exit_reason": "No follow-through",
                "exited_at": "2026-05-22",
                "cumulative_pnl": 115.0,
                "drawdown": 25.0,
            },
        ],
        "best_trade": {
            "ticker": "WINR",
            "name": "Winner",
            "realized_pnl": 140.0,
            "realized_pnl_pct": 13.86,
            "realized_r_multiple": 2.0,
            "exit_reason": "Target hit",
            "exited_at": "2026-05-20",
        },
        "worst_trade": {
            "ticker": "LOSS",
            "name": "Loser",
            "realized_pnl": -25.0,
            "realized_pnl_pct": -5.0,
            "realized_r_multiple": -0.83,
            "exit_reason": "Stopped",
            "exited_at": "2026-05-21",
        },
    }


def test_review_summary_totals_position_sized_active_items(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    risk = {"account_equity": 100000, "risk_pct": 0.5}
    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "IESC",
            "decision_status": "ready",
            "buy_zone_low": 220.0,
            "stop_loss_price": 210.0,
        },
        store_path=store_path,
    )
    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "LINC",
            "decision_status": "watch",
            "pivot_price": 100.0,
        },
        store_path=store_path,
    )
    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "PASS",
            "decision_status": "pass",
            "buy_zone_low": 50.0,
            "stop_loss_price": 45.0,
        },
        store_path=store_path,
    )

    summary = review_store.get_review_summary("canslim_score_rank", risk=risk, store_path=store_path)

    assert summary["total_items"] == 3
    assert summary["active_items"] == 2
    assert summary["sized_items"] == 1
    assert summary["unsized_items"] == 1
    assert summary["checklist_complete_items"] == 0
    assert summary["checklist_incomplete_items"] == 2
    assert summary["ready_checklist_blockers"] == 1
    assert summary["readiness_blocker_counts"] == {
        "checklist_incomplete": 1,
        "missing_position_size": 0,
    }
    assert summary["readiness_blocker_items"] == [
        {
            "ticker": "IESC",
            "name": "",
            "decision_status": "ready",
            "readiness_status": "blocked",
            "readiness_blockers": ["checklist_incomplete"],
            "checklist_complete_count": 0,
            "checklist_total_count": 5,
            "planned_shares": 50,
            "entry_price": 220.0,
            "stop_loss_price": 210.0,
        }
    ]
    assert summary["status_counts"] == {"bought": 0, "pass": 1, "ready": 1, "sold": 0, "watch": 1}
    assert summary["total_risk_amount"] == 500.0
    assert summary["total_planned_capital"] == 11000.0
    assert summary["risk_budget_pct"] == 0.5
    assert summary["planned_capital_pct"] == 11.0
    assert summary["status_breakdown"] == [
        {
            "status": "ready",
            "count": 1,
            "risk_amount": 500.0,
            "planned_capital": 11000.0,
            "risk_budget_pct": 0.5,
            "planned_capital_pct": 11.0,
        },
        {
            "status": "watch",
            "count": 1,
            "risk_amount": 0.0,
            "planned_capital": 0.0,
            "risk_budget_pct": 0.0,
            "planned_capital_pct": 0.0,
        },
        {
            "status": "bought",
            "count": 0,
            "risk_amount": 0.0,
            "planned_capital": 0.0,
            "risk_budget_pct": 0.0,
            "planned_capital_pct": 0.0,
        },
        {
            "status": "sold",
            "count": 0,
            "risk_amount": 0.0,
            "planned_capital": 0.0,
            "risk_budget_pct": 0.0,
            "planned_capital_pct": 0.0,
        },
        {
            "status": "pass",
            "count": 1,
            "risk_amount": 0.0,
            "planned_capital": 0.0,
            "risk_budget_pct": 0.0,
            "planned_capital_pct": 0.0,
        },
    ]
    assert summary["largest_positions"] == [
        {
            "ticker": "IESC",
            "name": "",
            "decision_status": "ready",
            "planned_capital": 11000.0,
            "risk_amount": 500.0,
            "planned_shares": 50,
            "entry_price": 220.0,
            "stop_loss_price": 210.0,
        }
    ]
    assert summary["warnings"] == [
        "1 active review item(s) are missing buy or stop levels",
        "1 ready review item(s) have incomplete pre-buy checklists",
    ]


def test_review_summary_uses_configurable_risk_guardrails(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    risk = {"account_equity": 100000, "risk_pct": 0.5, "max_capital_pct": 10, "max_queue_risk_pct": 0.25}
    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "IESC",
            "decision_status": "ready",
            "review_checks": {
                "weekly_chart": True,
                "daily_chart": True,
                "volume_confirmed": True,
                "market_aligned": True,
                "risk_defined": True,
            },
            "buy_zone_low": 220.0,
            "stop_loss_price": 210.0,
        },
        store_path=store_path,
    )

    summary = review_store.get_review_summary("canslim_score_rank", risk=risk, store_path=store_path)

    assert summary["planned_capital_pct"] == 11.0
    assert summary["risk_budget_pct"] == 0.5
    assert summary["warnings"] == [
        "planned capital uses more than 10% of account equity",
        "planned queue risk exceeds 0.25% of account equity",
    ]


def test_review_summary_reports_sector_and_setup_concentration(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    risk = {"account_equity": 100000, "risk_pct": 0.5}
    review_store.add_review_items(
        "canslim_score_rank",
        [
            {
                "ticker": "TECH1",
                "name": "Tech One",
                "sector": "Technology",
                "industry": "Software",
                "setup_status": "near_pivot",
                "decision_status": "ready",
                "buy_zone_low": 100,
                "stop_loss_price": 95,
            },
            {
                "ticker": "TECH2",
                "name": "Tech Two",
                "sector": "Technology",
                "industry": "Semiconductors",
                "setup_status": "near_pivot",
                "decision_status": "watch",
                "buy_zone_low": 50,
                "stop_loss_price": 45,
            },
            {
                "ticker": "HEALTH",
                "name": "Health Co",
                "sector": "Healthcare",
                "industry": "Medical Devices",
                "setup_status": "forming_base",
                "decision_status": "watch",
                "buy_zone_low": 40,
                "stop_loss_price": 38,
            },
        ],
        store_path=store_path,
    )

    summary = review_store.get_review_summary("canslim_score_rank", risk=risk, store_path=store_path)

    assert summary["concentration"]["top_sector"]["label"] == "Technology"
    assert summary["concentration"]["top_sector"]["count"] == 2
    assert summary["concentration"]["top_sector"]["sized_count"] == 2
    assert summary["concentration"]["top_sector"]["planned_capital"] == 15000.0
    assert summary["concentration"]["top_sector"]["share_of_planned_capital_pct"] == 60.0
    assert summary["concentration"]["top_sector"]["tickers"] == ["TECH1", "TECH2"]
    assert summary["concentration"]["top_setup"]["label"] == "near pivot"
    assert summary["concentration"]["warnings"] == [
        "sector concentration: Technology is 60% of planned capital",
        "setup concentration: near pivot is 60% of planned capital",
    ]
    assert summary["warnings"][-2:] == summary["concentration"]["warnings"]
    assert summary["risk_actions"][:2] == [
        {
            "severity": "warning",
            "category": "concentration",
            "label": "Plan sector concentration",
            "detail": "Technology is 60% of planned capital",
            "action": "rebalance_queue",
            "tickers": ["TECH1", "TECH2"],
            "count": 2,
            "amount": 15000.0,
        },
        {
            "severity": "warning",
            "category": "concentration",
            "label": "Plan setup concentration",
            "detail": "near pivot is 60% of planned capital",
            "action": "rebalance_queue",
            "tickers": ["TECH1", "TECH2"],
            "count": 2,
            "amount": 15000.0,
        },
    ]

    loose = review_store.get_review_summary(
        "canslim_score_rank",
        risk={"account_equity": 100000, "risk_pct": 0.5, "max_concentration_pct": 70},
        store_path=store_path,
    )
    assert loose["concentration"]["warning_share_pct"] == 70.0
    assert loose["concentration"]["warnings"] == []
    assert "sector concentration: Technology is 60% of planned capital" not in loose["warnings"]
    assert not [action for action in loose["risk_actions"] if action["label"].startswith("Plan")]


def test_review_summary_surfaces_stale_active_items(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_items(
        "canslim_score_rank",
        [
            {"ticker": "READYOLD", "name": "Ready Old", "decision_status": "ready"},
            {"ticker": "WATCHOLD", "name": "Watch Old", "decision_status": "watch"},
            {"ticker": "FRESH", "name": "Fresh", "decision_status": "watch"},
            {"ticker": "PASSOLD", "name": "Pass Old", "decision_status": "pass"},
        ],
        store_path=store_path,
    )
    store = json.loads(store_path.read_text())
    items = store["profiles"]["canslim_score_rank"]["items"]
    for item in items:
        if item["ticker"] == "READYOLD":
            item["added_at"] = "2026-05-18T12:00:00+00:00"
            item["updated_at"] = "2026-05-23T12:00:00+00:00"
        if item["ticker"] == "WATCHOLD":
            item["added_at"] = "2026-05-17T12:00:00+00:00"
            item["updated_at"] = "2026-05-20T12:00:00+00:00"
        if item["ticker"] == "FRESH":
            item["added_at"] = "2026-05-26T12:00:00+00:00"
            item["updated_at"] = "2026-05-26T12:00:00+00:00"
        if item["ticker"] == "PASSOLD":
            item["added_at"] = "2026-05-01T12:00:00+00:00"
            item["updated_at"] = "2026-05-01T12:00:00+00:00"
    store_path.write_text(json.dumps(store))

    summary = review_store.get_review_summary(
        "canslim_score_rank",
        store_path=store_path,
        now=dt.datetime(2026, 5, 27, 12, tzinfo=dt.timezone.utc),
    )

    assert summary["aging"]["active_count"] == 3
    assert summary["aging"]["oldest_active_days"] == 10
    assert summary["aging"]["oldest_idle_days"] == 7
    assert summary["aging"]["stale_ready_count"] == 1
    assert summary["aging"]["stale_active_count"] == 1
    assert summary["aging"]["buckets"] == {"fresh": 1, "aging": 1, "stale": 1}
    assert [(item["ticker"], item["staleness"], item["idle_days"]) for item in summary["aging"]["stale_items"]] == [
        ("READYOLD", "ready_stale", 4),
        ("WATCHOLD", "active_stale", 7),
    ]
    assert "1 ready review item(s) have not been touched for 2+ days" in summary["warnings"]
    assert "1 active review item(s) have not been touched for 5+ days" in summary["warnings"]


def test_review_summary_warns_when_open_position_stop_risk_exceeds_guardrail(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_item(
        "canslim_score_rank",
        {
            "ticker": "OPENRISK",
            "name": "Open Risk",
            "decision_status": "bought",
            "current_price": 107.25,
            "buy_zone_low": 100.0,
            "stop_loss_price": 94.0,
            "execution_price": 101.25,
            "execution_shares": 12,
        },
        store_path=store_path,
    )

    summary = review_store.get_review_summary(
        "canslim_score_rank",
        risk={
            "account_equity": 100000,
            "risk_pct": 0.5,
            "max_open_position_risk_pct": 0.1,
        },
        store_path=store_path,
    )

    assert summary["risk"]["max_open_position_risk_pct"] == 0.1
    assert summary["open_position_risk"]["stop_risk_pct"] == 0.16
    assert summary["warnings"] == [
        "open position stop risk exceeds 0.1% of account equity",
    ]


def test_review_activity_tracks_remove_and_clear(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "LINC", "name": "Lincoln", "decision_status": "watch"},
        store_path=store_path,
    )
    review_store.add_review_item(
        "canslim_score_rank",
        {"ticker": "IESC", "name": "IES", "decision_status": "ready"},
        store_path=store_path,
    )

    review_store.remove_review_item("canslim_score_rank", "LINC", store_path=store_path)
    activity = review_store.get_review_activity("canslim_score_rank", store_path=store_path)
    assert activity["activity"][0]["action"] == "removed"
    assert activity["activity"][0]["ticker"] == "LINC"
    assert activity["activity"][0]["restorable_items"][0]["ticker"] == "LINC"

    review_store.clear_review_queue("canslim_score_rank", store_path=store_path)
    activity = review_store.get_review_activity("canslim_score_rank", store_path=store_path)
    assert activity["activity"][0]["action"] == "cleared"
    assert activity["activity"][0]["removed_count"] == 1
    assert activity["activity"][0]["restorable_items"][0]["ticker"] == "IESC"

    restored = review_store.restore_review_activity(
        "canslim_score_rank",
        activity["activity"][0]["at"],
        store_path=store_path,
    )
    assert [item["ticker"] for item in restored["items"]] == ["IESC"]
    assert restored["activity"][0]["action"] == "restored"
    assert restored["activity"][0]["restored_count"] == 1

    with pytest.raises(ValueError, match="already restored"):
        review_store.restore_review_activity("canslim_score_rank", activity["activity"][0]["at"], store_path=store_path)


def test_review_queue_rejects_invalid_export_format(tmp_path: Path):
    with pytest.raises(ValueError):
        review_store.export_review_queue("canslim_score_rank", "xlsx", store_path=tmp_path / "review_queue.json")


def test_review_queue_rejects_invalid_export_filters(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"

    with pytest.raises(ValueError, match="status filter"):
        review_store.export_review_queue("canslim_score_rank", "csv", filters={"status": "maybe"}, store_path=store_path)

    with pytest.raises(ValueError, match="priority filter"):
        review_store.export_review_queue("canslim_score_rank", "csv", filters={"priority": "urgent"}, store_path=store_path)

    with pytest.raises(ValueError, match="Ticker must"):
        review_store.export_review_queue("canslim_score_rank", "csv", filters={"tickers": "../bad"}, store_path=store_path)


def test_review_queue_rejects_corrupt_store_without_overwrite(tmp_path: Path):
    store_path = tmp_path / "review_queue.json"
    store_path.write_text('{"profiles": ')

    with pytest.raises(ValueError, match="not valid JSON"):
        review_store.get_review_queue("canslim_score_rank", store_path=store_path)

    with pytest.raises(ValueError, match="not valid JSON"):
        review_store.add_review_item(
            "canslim_score_rank",
            {"ticker": "SAFE1", "decision_status": "watch"},
            store_path=store_path,
        )

    assert store_path.read_text() == '{"profiles": '


def test_review_queue_rejects_invalid_ticker(tmp_path: Path):
    with pytest.raises(ValueError):
        review_store.add_review_item(
            "canslim_score_rank",
            {"ticker": "../bad"},
            store_path=tmp_path / "review_queue.json",
        )


def test_review_queue_rejects_invalid_decision_status(tmp_path: Path):
    with pytest.raises(ValueError):
        review_store.add_review_item(
            "canslim_score_rank",
            {"ticker": "IESC", "decision_status": "maybe"},
            store_path=tmp_path / "review_queue.json",
        )

    with pytest.raises(ValueError):
        review_store.bulk_update_review_items(
            "canslim_score_rank",
            ["IESC"],
            {"decision_status": "maybe"},
            store_path=tmp_path / "review_queue.json",
        )
