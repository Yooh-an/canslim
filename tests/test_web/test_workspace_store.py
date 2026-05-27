"""Tests for persisted web workspace preferences."""

from pathlib import Path

import pytest

from src.web import workspace_store


def test_workspace_preferences_persist_profile_and_screener_filters(tmp_path: Path):
    store_path = tmp_path / "preferences.json"

    saved = workspace_store.save_preferences(
        {
            "profile": "canslim_watchlist",
            "screener": {
                "query": "  industrials  ",
                "min_score": "82.5",
                "setup": "near_pivot",
                "sort_by": "rs",
                "sort_dir": "asc",
            },
            "screener_views": [
                {
                    "id": "leaders",
                    "name": "  Leadership list  ",
                    "query": "  semis  ",
                    "min_score": "88",
                    "setup": "near_pivot",
                    "sort_by": "eps",
                    "sort_dir": "desc",
                }
            ],
            "review_views": [
                {
                    "id": "ready-high",
                    "name": "  Ready high  ",
                    "query": "  infra  ",
                    "sort_by": "risk",
                    "sort_dir": "asc",
                    "status": "ready",
                    "priority": "high",
                    "tag": "Breakout Setup",
                }
            ],
            "risk": {
                "account_equity": "250000",
                "risk_pct": "0.75",
                "max_capital_pct": "70",
                "max_queue_risk_pct": "3.5",
                "max_open_position_risk_pct": "4.5",
                "max_concentration_pct": "55",
                "max_open_concentration_pct": "45",
            },
            "review": {
                "query": "  ies  ",
                "sort_by": "priority",
                "sort_dir": "asc",
                "status": "sold",
                "priority": "high",
                "tag": "Breakout Setup",
            },
        },
        store_path=store_path,
    )

    assert saved["profile"] == "canslim_watchlist"
    assert saved["screener"] == {
        "query": "industrials",
        "min_score": 82.5,
        "setup": "near_pivot",
        "sort_by": "rs",
        "sort_dir": "asc",
    }
    assert saved["screener_views"] == [
        {
            "id": "leaders",
            "name": "Leadership list",
            "query": "semis",
            "min_score": 88.0,
            "setup": "near_pivot",
            "sort_by": "eps",
            "sort_dir": "desc",
        }
    ]
    assert saved["review_views"] == [
        {
            "id": "ready-high",
            "name": "Ready high",
            "query": "infra",
            "sort_by": "risk",
            "sort_dir": "asc",
            "status": "ready",
            "priority": "high",
            "tag": "breakout-setup",
        }
    ]
    assert saved["review"] == {
        "query": "ies",
        "sort_by": "priority",
        "sort_dir": "asc",
        "status": "sold",
        "priority": "high",
        "tag": "breakout-setup",
    }
    assert saved["risk"] == {
        "account_equity": 250000.0,
        "risk_pct": 0.75,
        "max_capital_pct": 70.0,
        "max_queue_risk_pct": 3.5,
        "max_open_position_risk_pct": 4.5,
        "max_concentration_pct": 55.0,
        "max_open_concentration_pct": 45.0,
    }
    assert saved["updated_at"]
    assert workspace_store.get_preferences(store_path=store_path) == saved


def test_workspace_preferences_sanitize_invalid_values(tmp_path: Path):
    saved = workspace_store.save_preferences(
        {
            "profile": "../bad",
            "screener": {
                "query": "x" * 120,
                "min_score": 400,
                "setup": "unknown",
                "sort_by": "bad",
                "sort_dir": "sideways",
            },
            "screener_views": [
                "not-object",
                {"id": "<bad id!>", "name": "  ", "query": "drop"},
                {
                    "id": "view-1",
                    "name": "z" * 80,
                    "query": "q" * 120,
                    "min_score": -5,
                    "setup": "invalid",
                    "sort_by": "unknown",
                    "sort_dir": "sideways",
                },
                {
                    "id": "view-1",
                    "name": "Breakouts",
                    "query": "breakout",
                    "min_score": 97,
                    "setup": "breakout_confirmed",
                    "sort_by": "pivot",
                    "sort_dir": "asc",
                },
            ],
            "review_views": [
                "not-object",
                {"id": "<bad id!>", "name": "  ", "query": "drop"},
                {
                    "id": "review-1",
                    "name": "r" * 80,
                    "query": "q" * 120,
                    "sort_by": "bad",
                    "sort_dir": "sideways",
                    "status": "unknown",
                    "priority": "urgent",
                    "tag": "=bad tag!",
                },
                {
                    "id": "review-1",
                    "name": "Bought risk",
                    "query": "bought",
                    "sort_by": "capital",
                    "sort_dir": "asc",
                    "status": "bought",
                    "priority": "low",
                    "tag": "Risk Tag",
                },
            ],
            "risk": {
                "account_equity": -50,
                "risk_pct": 20,
                "max_capital_pct": 120,
                "max_queue_risk_pct": 99,
                "max_open_position_risk_pct": 99,
                "max_concentration_pct": 120,
                "max_open_concentration_pct": 120,
            },
            "review": {
                "query": "y" * 120,
                "sort_by": "bad",
                "sort_dir": "sideways",
                "status": "unknown",
                "priority": "urgent",
                "tag": "=bad tag!",
            },
        },
        store_path=tmp_path / "preferences.json",
    )

    assert saved["profile"] == "canslim_score_rank"
    assert saved["screener"]["query"] == "x" * 80
    assert saved["screener"]["min_score"] == 100
    assert saved["screener"]["setup"] == ""
    assert saved["screener"]["sort_by"] == "score"
    assert saved["screener"]["sort_dir"] == "desc"
    assert saved["screener_views"] == [
        {
            "id": "view-1",
            "name": "z" * 40,
            "query": "q" * 80,
            "min_score": 0,
            "setup": "",
            "sort_by": "score",
            "sort_dir": "desc",
        },
        {
            "id": "view-1-2",
            "name": "Breakouts",
            "query": "breakout",
            "min_score": 97.0,
            "setup": "breakout_confirmed",
            "sort_by": "pivot",
            "sort_dir": "asc",
        },
    ]
    assert saved["review_views"] == [
        {
            "id": "review-1",
            "name": "r" * 40,
            "query": "q" * 80,
            "sort_by": "added_at",
            "sort_dir": "desc",
            "status": "",
            "priority": "",
            "tag": "bad-tag",
        },
        {
            "id": "review-1-2",
            "name": "Bought risk",
            "query": "bought",
            "sort_by": "capital",
            "sort_dir": "asc",
            "status": "bought",
            "priority": "low",
            "tag": "risk-tag",
        },
    ]
    assert saved["review"]["sort_by"] == "added_at"
    assert saved["review"]["sort_dir"] == "desc"
    assert saved["review"]["status"] == ""
    assert saved["review"]["priority"] == ""
    assert saved["review"]["query"] == "y" * 80
    assert saved["review"]["tag"] == "bad-tag"
    assert saved["risk"]["account_equity"] == 0
    assert saved["risk"]["risk_pct"] == 5
    assert saved["risk"]["max_capital_pct"] == 100
    assert saved["risk"]["max_queue_risk_pct"] == 25
    assert saved["risk"]["max_open_position_risk_pct"] == 25
    assert saved["risk"]["max_concentration_pct"] == 100
    assert saved["risk"]["max_open_concentration_pct"] == 100


def test_workspace_preferences_default_when_store_missing(tmp_path: Path):
    preferences = workspace_store.get_preferences(store_path=tmp_path / "missing.json")

    assert preferences["profile"] == "canslim_score_rank"
    assert preferences["screener"]["query"] == ""
    assert preferences["screener"]["min_score"] == 70
    assert preferences["screener"]["setup"] == ""
    assert preferences["screener"]["sort_by"] == "score"
    assert preferences["screener"]["sort_dir"] == "desc"
    assert preferences["screener_views"] == []
    assert preferences["review_views"] == []
    assert preferences["review"]["sort_by"] == "added_at"
    assert preferences["review"]["sort_dir"] == "desc"
    assert preferences["review"]["status"] == ""
    assert preferences["review"]["priority"] == ""
    assert preferences["review"]["query"] == ""
    assert preferences["review"]["tag"] == ""
    assert preferences["risk"]["account_equity"] == 100000
    assert preferences["risk"]["risk_pct"] == 0.5
    assert preferences["risk"]["max_capital_pct"] == 80
    assert preferences["risk"]["max_queue_risk_pct"] == 5
    assert preferences["risk"]["max_open_position_risk_pct"] == 6
    assert preferences["risk"]["max_concentration_pct"] == 60
    assert preferences["risk"]["max_open_concentration_pct"] == 60


def test_workspace_preferences_rejects_corrupt_store_without_overwrite(tmp_path: Path):
    store_path = tmp_path / "preferences.json"
    store_path.write_text('{"profile": ')

    with pytest.raises(ValueError, match="not valid JSON"):
        workspace_store.get_preferences(store_path=store_path)

    with pytest.raises(ValueError, match="not valid JSON"):
        workspace_store.save_preferences({"profile": "canslim_score_rank"}, store_path=store_path)

    assert store_path.read_text() == '{"profile": '


def test_workspace_preferences_load_old_store_without_saved_screener_views(tmp_path: Path):
    store_path = tmp_path / "preferences.json"
    store_path.write_text('{"profile":"canslim_watchlist","screener":{"query":"steel"}}')

    preferences = workspace_store.get_preferences(store_path=store_path)

    assert preferences["profile"] == "canslim_watchlist"
    assert preferences["screener"]["query"] == "steel"
    assert preferences["screener_views"] == []
    assert preferences["review_views"] == []


def test_workspace_preferences_limit_saved_screener_views(tmp_path: Path):
    views = [
        {
            "id": f"view-{index}",
            "name": f"View {index}",
            "query": f"query {index}",
            "min_score": 70 + index,
            "sort_by": "score",
            "sort_dir": "desc",
        }
        for index in range(20)
    ]

    saved = workspace_store.save_preferences(
        {"profile": "canslim_score_rank", "screener_views": views},
        store_path=tmp_path / "preferences.json",
    )

    assert len(saved["screener_views"]) == workspace_store.MAX_SCREENER_VIEWS
    assert saved["screener_views"][0]["id"] == "view-0"
    assert saved["screener_views"][-1]["id"] == "view-11"


def test_workspace_preferences_limit_saved_review_views(tmp_path: Path):
    views = [
        {
            "id": f"review-{index}",
            "name": f"Review {index}",
            "query": f"query {index}",
            "sort_by": "risk",
            "sort_dir": "desc",
            "status": "ready",
            "priority": "high",
            "tag": f"tag-{index}",
        }
        for index in range(20)
    ]

    saved = workspace_store.save_preferences(
        {"profile": "canslim_score_rank", "review_views": views},
        store_path=tmp_path / "preferences.json",
    )

    assert len(saved["review_views"]) == workspace_store.MAX_REVIEW_VIEWS
    assert saved["review_views"][0]["id"] == "review-0"
    assert saved["review_views"][-1]["id"] == "review-11"
