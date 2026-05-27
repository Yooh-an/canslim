"""Tests for CLI mode registration."""

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_screener


def test_runner_accepts_status_update_analyze_tv_export_and_web_modes(monkeypatch):
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

    monkeypatch.setattr(sys, "argv", ["run_screener.py", "--mode", "tv-export", "--config", "config/base.json", "--profile", "canslim_pure"])
    run_screener.main()

    assert "tv-export" in captured[3]
    assert "canslim_pure" in captured[3]

    web_calls = []

    def fake_run_web(
        host,
        port,
        *,
        quiet=False,
        allow_remote=False,
        open_browser=False,
        auth=None,
        auth_env=None,
        require_auth=False,
    ):
        web_calls.append((host, port, quiet, allow_remote, open_browser, auth, auth_env, require_auth))

    monkeypatch.setattr("src.web.server.run", fake_run_web)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_screener.py",
            "--mode",
            "web",
            "--host",
            "0.0.0.0",
            "--port",
            "9999",
            "--quiet",
            "--allow-remote",
            "--open",
            "--auth",
            "desk:secret",
            "--auth-env",
            "DASH_AUTH",
            "--require-auth",
        ],
    )
    run_screener.main()

    assert web_calls == [("0.0.0.0", 9999, True, True, True, "desk:secret", "DASH_AUTH", True)]


def test_runner_profile_sweep_screens_each_configured_profile(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "config"
    profile_dir = config_dir / "profiles"
    profile_dir.mkdir(parents=True)
    config_path = config_dir / "base.json"
    config_path.write_text("{}")
    (profile_dir / "canslim_score_rank.json").write_text("{}")
    (profile_dir / "canslim_pure.json").write_text("{}")
    commands = []

    def fake_run(command):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_screener.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_screener.py", "--mode", "profile-sweep", "--config", str(config_path), "--log-level", "DEBUG"],
    )

    run_screener.main()

    profiles = [command[command.index("--profile") + 1] for command in commands]
    assert profiles == ["canslim_pure", "canslim_score_rank"]
    assert all(command[command.index("--mode") + 1] == "screen" for command in commands)
    assert all(command[command.index("--config") + 1] == str(config_path.resolve()) for command in commands)
    assert all(command[command.index("--log-level") + 1] == "DEBUG" for command in commands)


def test_runner_reports_missing_required_auth_without_traceback(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_screener.py", "--mode", "web", "--port", "8770", "--require-auth", "--auth-env", ""],
    )

    with pytest.raises(SystemExit) as exc_info:
        run_screener.main()

    assert exc_info.value.code == 2
    stderr = capsys.readouterr().err
    assert "Dashboard authentication is required" in stderr
    assert "Traceback" not in stderr


def test_runner_rejects_unknown_mode(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_screener.py", "--mode", "unknown"])

    with pytest.raises(SystemExit):
        run_screener.main()
