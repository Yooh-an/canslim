"""Tests for persisted web session journal notes."""

from pathlib import Path

import pytest

from src.web import session_journal


def test_session_journal_persists_profile_date_notes(tmp_path: Path):
    store_path = tmp_path / "session_journal.json"

    saved = session_journal.save_session_journal(
        "canslim_score_rank",
        {
            "date": "2026-05-26",
            "market_thesis": "  Uptrend intact\nWatch distribution.  ",
            "watchlist_focus": "Construction leaders",
            "risk_notes": "Half-size new buys",
            "post_session_review": "No forced entries",
        },
        store_path=store_path,
    )

    assert saved["profile"] == "canslim_score_rank"
    assert saved["date"] == "2026-05-26"
    assert saved["market_thesis"] == "Uptrend intact\nWatch distribution."
    assert saved["watchlist_focus"] == "Construction leaders"
    assert saved["risk_notes"] == "Half-size new buys"
    assert saved["post_session_review"] == "No forced entries"
    assert saved["updated_at"]
    assert session_journal.get_session_journal(
        "canslim_score_rank",
        session_date="2026-05-26",
        store_path=store_path,
    ) == saved


def test_session_journal_returns_empty_entry_when_missing(tmp_path: Path):
    entry = session_journal.get_session_journal(
        "canslim_score_rank",
        session_date="2026-05-26",
        store_path=tmp_path / "missing.json",
    )

    assert entry == {
        "profile": "canslim_score_rank",
        "date": "2026-05-26",
        "market_thesis": "",
        "watchlist_focus": "",
        "risk_notes": "",
        "post_session_review": "",
        "updated_at": "",
    }


def test_session_journal_rejects_corrupt_store_without_overwrite(tmp_path: Path):
    store_path = tmp_path / "session_journal.json"
    store_path.write_text('{"profiles": ')

    with pytest.raises(ValueError, match="not valid JSON"):
        session_journal.get_session_journal("canslim_score_rank", store_path=store_path)

    with pytest.raises(ValueError, match="not valid JSON"):
        session_journal.save_session_journal(
            "canslim_score_rank",
            {"date": "2026-05-26", "market_thesis": "Do not overwrite"},
            store_path=store_path,
        )

    assert store_path.read_text() == '{"profiles": '


def test_session_journal_sanitizes_invalid_values(tmp_path: Path):
    saved = session_journal.save_session_journal(
        "../bad",
        {
            "date": "not-a-date",
            "market_thesis": "x" * 2100,
            "watchlist_focus": None,
            "risk_notes": "risk\x00note",
            "post_session_review": "done",
            "updated_at": "ignored",
        },
        store_path=tmp_path / "session_journal.json",
    )

    assert saved["profile"] == "canslim_score_rank"
    assert len(saved["market_thesis"]) == session_journal.MAX_NOTE_LENGTH
    assert saved["watchlist_focus"] == ""
    assert saved["risk_notes"] == "risknote"
    assert saved["post_session_review"] == "done"
    assert saved["updated_at"] != "ignored"


def test_session_journal_exports_and_replaces_entries(tmp_path: Path):
    store_path = tmp_path / "session_journal.json"
    session_journal.save_session_journal(
        "canslim_score_rank",
        {"date": "2026-05-25", "market_thesis": "old"},
        store_path=store_path,
    )

    restored = session_journal.replace_journal_entries(
        "canslim_score_rank",
        {
            "entries": [
                {"date": "2026-05-26", "market_thesis": "new"},
                {"date": "2026-05-24", "risk_notes": "defensive"},
                "bad entry",
            ]
        },
        store_path=store_path,
    )

    assert [entry["date"] for entry in restored["entries"]] == ["2026-05-26", "2026-05-24"]
    assert restored["entries"][0]["market_thesis"] == "new"
    assert restored["entries"][1]["risk_notes"] == "defensive"
    assert session_journal.get_session_journal(
        "canslim_score_rank",
        session_date="2026-05-25",
        store_path=store_path,
    )["market_thesis"] == ""
