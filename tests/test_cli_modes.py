"""Tests for CLI mode registration."""

import argparse
import sys

import pytest

import run_screener


def test_runner_accepts_status_update_and_analyze_modes(monkeypatch):
    captured = []

    def fake_main():
        captured.append(sys.argv[:])

    monkeypatch.setattr(sys, "argv", ["run_screener.py", "--mode", "status", "--config", "config/base.json", "--profile", "canslim_pure"])
    monkeypatch.setattr("src.growth_stock_screener.main", fake_main)

    run_screener.main()

    assert "status" in captured[0]
    assert "canslim_pure" in captured[0]

    monkeypatch.setattr(sys, "argv", ["run_screener.py", "--mode", "update", "--config", "config/base.json"])
    run_screener.main()

    assert "update" in captured[1]

    monkeypatch.setattr(sys, "argv", ["run_screener.py", "--mode", "analyze", "--ticker", "STRL", "--config", "config/base.json"])
    run_screener.main()

    assert "analyze" in captured[2]
    assert "STRL" in captured[2]


def test_runner_rejects_unknown_mode(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_screener.py", "--mode", "unknown"])

    with pytest.raises(SystemExit):
        run_screener.main()
