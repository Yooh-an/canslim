"""Tests for the local web data adapter."""

import csv
import datetime as dt
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.web import data_provider


def test_get_market_news_sanitizes_non_http_links(monkeypatch: pytest.MonkeyPatch):
    data_provider._cached_market_news.cache_clear()
    rss = b"""
    <rss><channel>
      <item><title>Valid link</title><pubDate>Tue, 26 May 2026 12:00:00 GMT</pubDate><link>https://example.com/story</link></item>
      <item><title>Script link</title><link>javascript:alert(1)</link></item>
      <item><title>Data link</title><link>data:text/html,blocked</link></item>
    </channel></rss>
    """
    monkeypatch.setattr(data_provider, "_read_url", lambda url, timeout=5: rss)

    try:
        news = data_provider.get_market_news(limit=3)
    finally:
        data_provider._cached_market_news.cache_clear()

    assert news[0]["url"] == "https://example.com/story"
    assert news[1]["url"] is None
    assert news[2]["url"] is None


def test_load_candidate_rows_parses_numeric_bool_and_structured_fields(tmp_path: Path):
    csv_path = tmp_path / "results.csv"
    csv_path.write_text(
        "ticker,name,canslim_score,a_score,near_pivot,pass_reasons,component_scores\n"
        "IESC,IES Holdings,95.56,90.07,True,\"['C: growth']\",\"{'c': 100.0, 'a': 90.0}\"\n"
    )

    rows, message = data_provider._load_candidate_rows(csv_path)

    assert message is None
    assert rows[0]["ticker"] == "IESC"
    assert rows[0]["canslim_score"] == 95.56
    assert rows[0]["a_score"] == 90.07
    assert rows[0]["near_pivot"] is True
    assert rows[0]["pass_reasons"] == ["C: growth"]
    assert rows[0]["component_scores"] == {"c": 100.0, "a": 90.0}


def test_load_candidate_rows_handles_empty_screener_output(tmp_path: Path):
    csv_path = tmp_path / "results.csv"
    csv_path.write_text("No companies passed the screening criteria.\n")

    rows, message = data_provider._load_candidate_rows(csv_path)

    assert rows == []
    assert message == "No companies passed the screening criteria."


def test_project_candidate_builds_component_scores_from_columns():
    projected = data_provider._project_candidate(
        {
            "ticker": "LINC",
            "name": "Lincoln",
            "current_price": 102.0,
            "pivot_price": 100.0,
            "buy_zone_low": 100.0,
            "buy_zone_high": 105.0,
            "in_buy_zone": True,
            "stop_loss_price": 92.0,
            "profit_target_low": 120.0,
            "profit_target_high": 125.0,
            "setup_status": "near_pivot",
            "setup_reasons": ["volume confirmed"],
            "a_score": 90.0,
            "c_score": 100.0,
            "n_score": 85.0,
            "s_score": 80.0,
            "l_score": 75.0,
            "i_score": 70.0,
            "m_score": 65.0,
        }
    )

    assert projected["ticker"] == "LINC"
    assert projected["component_scores"]["c"] == 100.0
    assert projected["component_scores"]["m"] == 65.0
    assert projected["research_brief"]["action"] == "actionable"
    assert projected["research_brief"]["trade_plan"]["risk_pct"] == 0.09803921568627451
    assert projected["research_brief"]["trade_plan"]["risk_reward_low"] == 1.8
    assert projected["research_brief"]["setup"]["reasons"] == ["volume confirmed"]
    assert projected["research_brief"]["score"]["strongest_components"] == [
        "Current earnings",
        "Annual growth",
        "New highs/setup",
    ]


def test_summarize_data_health_detects_stale_market_data():
    now = dt.datetime(2026, 5, 26, 12, tzinfo=dt.timezone.utc)
    status = {
        "download_ready": True,
        "parse_ready": True,
        "enrich_ready": True,
        "institutional_ready": True,
        "screen_ready": True,
        "facts_count": 100,
        "company_count": 90,
        "leadership_count": 80,
        "institutional_count": 70,
        "next_action": "none",
        "recommended_commands": [],
        "warnings": [],
        "files": {"results_csv": {"path": "data/processed/results.csv", "mtime": now.timestamp() - 3600}},
    }

    health = data_provider.summarize_data_health(
        status,
        {"as_of": "2026-05-20"},
        [{"ticker": "IESC"}],
        now=now,
    )

    assert health["level"] == "stale_market"
    assert health["readiness_pct"] == 100
    assert health["result_age_hours"] == 1
    assert health["market_age_days"] == 6
    assert health["market_session_lag"] == 2
    assert health["market_expected_as_of"] == "2026-05-22"
    assert health["candidate_count"] == 1
    assert health["stale_source_count"] == 1
    assert health["missing_source_count"] == 0
    assert health["source_findings"] == [
        {
            "level": "stale",
            "source_id": "market_direction",
            "label": "Market direction",
            "detail": "Market direction is 2 completed market sessions old.",
            "age_days": 6,
            "session_lag": 2,
            "as_of": "2026-05-20",
            "expected_as_of": "2026-05-22",
            "next_action": "enrich",
        }
    ]


def test_summarize_data_health_treats_holiday_weekend_gap_as_fresh():
    now = dt.datetime(2026, 5, 26, 13, 30, tzinfo=dt.timezone.utc)
    status = {
        "download_ready": True,
        "parse_ready": True,
        "enrich_ready": True,
        "institutional_ready": True,
        "screen_ready": True,
        "facts_count": 100,
        "company_count": 90,
        "leadership_count": 80,
        "institutional_count": 70,
        "next_action": "none",
        "recommended_commands": [],
        "warnings": [],
        "files": {"results_csv": {"path": "data/processed/results.csv", "mtime": now.timestamp() - 3600}},
    }

    health = data_provider.summarize_data_health(
        status,
        {"as_of": "2026-05-22"},
        [{"ticker": "IESC"}],
        now=now,
    )

    assert health["level"] == "ready"
    assert health["market_age_days"] == 4
    assert health["market_session_lag"] == 0
    assert health["market_expected_as_of"] == "2026-05-22"
    assert health["source_findings"] == []


def test_sort_candidates_sorts_supported_fields_with_missing_values_last():
    rows = [
        {"ticker": "AAA", "rs_rating": None, "canslim_score": 99},
        {"ticker": "BBB", "rs_rating": 91.5, "canslim_score": 88},
        {"ticker": "CCC", "rs_rating": 82.0, "canslim_score": 95},
    ]

    data_provider.sort_candidates(rows, "rs", "desc")

    assert [row["ticker"] for row in rows] == ["BBB", "CCC", "AAA"]

    data_provider.sort_candidates(rows, "ticker", "asc")

    assert [row["ticker"] for row in rows] == ["AAA", "BBB", "CCC"]


def test_available_profiles_returns_operating_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project = tmp_path
    profile_dir = project / "config" / "profiles"
    processed_dir = project / "data" / "processed"
    profile_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)
    (profile_dir / "canslim_score_rank.json").write_text("{}")
    (profile_dir / "canslim_watchlist.json").write_text("{}")
    (processed_dir / "results_canslim_score_rank.csv").write_text(
        "ticker,canslim_score\n"
        "IESC,91.25\n"
        "LINC,88\n"
    )
    (processed_dir / "results_canslim_watchlist.csv").write_text("ticker,canslim_score\n")

    monkeypatch.setattr(data_provider, "PROJECT_ROOT", project)
    monkeypatch.setattr(data_provider, "PROFILE_DIR", profile_dir)
    monkeypatch.setattr(
        data_provider,
        "load_profile_config",
        lambda profile=None: {
            "profile_name": profile or "canslim_score_rank",
            "data_paths": {"output_file": f"data/processed/results_{profile or 'canslim_score_rank'}.csv"},
        },
    )

    profiles = data_provider.available_profiles()

    assert profiles[0]["name"] == "canslim_score_rank"
    assert profiles[0]["state"] == "ready"
    assert profiles[0]["candidate_count"] == 2
    assert profiles[0]["top_score"] == 91.25
    assert profiles[0]["result_exists"] is True
    assert profiles[0]["result_age_hours"] is not None
    assert profiles[1]["name"] == "canslim_watchlist"
    assert profiles[1]["state"] == "empty"
    assert profiles[1]["candidate_count"] == 0


def test_summarize_candidate_quality_flags_missing_trade_plan_fields():
    quality = data_provider.summarize_candidate_quality(
        [
            {
                "ticker": "READY",
                "name": "Ready Co",
                "canslim_score": 91,
                "current_price": 100,
                "pivot_price": 98,
                "buy_zone_low": 98,
                "stop_loss_price": 91,
                "rs_rating": 94,
                "quarterly_eps_growth": 0.38,
                "revenue_growth": 0.22,
                "setup_status": "near_pivot",
                "sector": "Industrial",
                "in_buy_zone": False,
            },
            {
                "ticker": "MISS",
                "name": "Missing Co",
                "canslim_score": 88,
                "current_price": "",
                "pivot_price": 52,
                "buy_zone_low": "",
                "stop_loss_price": "",
                "rs_rating": "",
                "quarterly_eps_growth": 0.31,
                "revenue_growth": 0.18,
                "setup_status": "breakout_unconfirmed",
                "in_buy_zone": True,
            },
        ]
    )

    assert quality["level"] == "blocked"
    assert quality["summary"] == "4/6 critical fields ready"
    coverage = {item["key"]: item for item in quality["coverage"]}
    assert coverage["current_price"]["coverage_pct"] == 50.0
    assert coverage["current_price"]["level"] == "blocked"
    assert coverage["stop_loss_price"]["level"] == "warning"
    assert coverage["sector"]["level"] == "warning"
    assert quality["issue_rows"] == [
        {
            "ticker": "MISS",
            "name": "Missing Co",
            "missing": ["Price", "Buy low", "Stop"],
            "score": 88.0,
        }
    ]


def test_operational_diagnostics_reports_environment_readiness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project = tmp_path
    profile_dir = project / "config" / "profiles"
    processed_dir = project / "data" / "processed"
    raw_dir = project / "data" / "raw"
    workspace_dir = project / "data" / "web_workspace"
    web_assets = project / "web" / "assets"
    profile_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    workspace_dir.mkdir(parents=True)
    web_assets.mkdir(parents=True)
    (project / "config" / "base.json").write_text("{}")
    (profile_dir / "canslim_score_rank.json").write_text("{}")
    (profile_dir / "canslim_gap.json").write_text("{}")
    (web_assets.parent / "index.html").write_text("<html></html>")
    (web_assets / "app.js").write_text("console.log('ok');")
    (web_assets / "app.css").write_text("body{}")
    (project / "run_screener.py").write_text("print('ok')\n")
    screener = project / "screener"
    screener.write_text("#!/bin/sh\n")
    screener.chmod(0o755)
    (processed_dir / "results_canslim_score_rank.csv").write_text(
        "ticker,canslim_score\n"
        "IESC,91\n"
    )

    monkeypatch.setattr(data_provider, "PROJECT_ROOT", project)
    monkeypatch.setattr(data_provider, "CONFIG_PATH", project / "config" / "base.json")
    monkeypatch.setattr(data_provider, "PROFILE_DIR", profile_dir)
    monkeypatch.setattr(
        data_provider,
        "load_profile_config",
        lambda profile=None: {
            "profile_name": profile or "canslim_score_rank",
            "data_paths": {
                "raw_data_dir": "data/raw",
                "processed_data_dir": "data/processed",
                "output_file": f"data/processed/results_{profile or 'canslim_score_rank'}.csv",
            },
        },
    )
    monkeypatch.setattr(
        data_provider,
        "collect_pipeline_status",
        lambda config: {
            "download_ready": True,
            "parse_ready": True,
            "enrich_ready": True,
            "institutional_ready": True,
            "screen_ready": True,
            "next_action": "none",
        },
    )
    monkeypatch.setattr(
        data_provider.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(total=20 * 1024**3, used=10 * 1024**3, free=10 * 1024**3),
    )

    diagnostics = data_provider.get_operational_diagnostics("canslim_score_rank")

    checks = {check["id"]: check for check in diagnostics["checks"]}
    assert diagnostics["level"] == "warning"
    assert checks["web_static"]["level"] == "ready"
    assert checks["browser_security_policy"]["level"] == "ready"
    assert checks["browser_security_policy"]["detail"] == "4/4 browser isolation policies configured"
    assert checks["web_security_posture"]["level"] == "ready"
    assert checks["web_security_posture"]["detail"] == "11/11 controls ready"
    assert diagnostics["security"]["level"] == "ready"
    assert diagnostics["security"]["summary"] == "11/11 controls ready"
    isolation_control = next(control for control in diagnostics["security"]["controls"] if control["id"] == "browser_isolation_headers")
    assert isolation_control["detail"] == "strict CSP, frame denial, COOP/CORP, and XFO configured"
    host_origin_control = next(control for control in diagnostics["security"]["controls"] if control["id"] == "host_origin_guard")
    assert host_origin_control["detail"] == "validated Host header and explicit same-origin Origin required for writes"
    access_control = next(control for control in diagnostics["security"]["controls"] if control["id"] == "access_control")
    assert access_control["detail"] == (
        "local-only binding by default; optional Basic Auth via --auth or CANSLIM_DASHBOARD_AUTH; "
        "--require-auth available for fail-closed deployments"
    )
    assert {control["id"] for control in diagnostics["security"]["controls"]} == {
        "csrf_write_token",
        "download_token",
        "host_origin_guard",
        "access_control",
        "auth_failure_throttle",
        "request_body_limit",
        "write_rate_limit",
        "request_timeout",
        "browser_isolation_headers",
        "browser_permission_policy",
        "diagnostic_redaction",
    }
    assert checks["workspace_store"]["level"] == "ready"
    assert checks["workspace_disk_space"]["level"] == "ready"
    assert checks["workspace_disk_space"]["detail"] == "10.0 GiB free"
    assert checks["workspace_store_integrity"]["level"] == "ready"
    assert checks["workspace_store_integrity"]["detail"] == "0/4 store file(s) present and readable"
    assert checks["workspace_atomic_temps"]["level"] == "ready"
    assert checks["workspace_atomic_temps"]["detail"] == "no interrupted write temp files"
    assert checks["cli_entrypoints"]["level"] == "ready"
    assert checks["active_results"]["detail"] == "1 candidate row(s)"
    assert checks["profile_outputs"]["level"] == "warning"
    assert checks["profile_outputs"]["detail"] == "1/2 generated · 1 with candidates · 1 missing"
    assert checks["profile_outputs"]["next_action"] == "profile-sweep"
    assert checks["generated_artifacts"]["level"] == "warning"
    deployment = diagnostics["deployment"]
    assert deployment["auth_env"] == data_provider.security_posture.DEFAULT_AUTH_ENV
    assert deployment["current_access"] == {
        "allow_remote": False,
        "auth_enabled": False,
        "require_auth": False,
    }
    assert deployment["probe"] == {
        "path": "/api/readiness",
        "method": "GET",
        "success": "HTTP 200 with ok=true; HTTP 503 when a release gate is blocked",
        "detail": "uses the same release gates shown in Data Operations and support bundles",
    }
    commands = {command["id"]: command for command in deployment["commands"]}
    assert commands["local"]["command"] == "./screener web --open"
    assert "--allow-remote --require-auth" in commands["remote"]["command"]
    assert f"-e {data_provider.security_posture.DEFAULT_AUTH_ENV}='USER:PASSWORD'" in commands["container"]["command"]
    assert "change-this-password" not in json.dumps(deployment)
    release = diagnostics["release_readiness"]
    assert release["level"] == "warning"
    assert release["summary"] == "9/11 release gates ready"
    assert release["counts"] == {"ready": 9, "warning": 2, "blocked": 0}
    assert release["next_actions"] == ["profile-sweep", "tv-export"]
    assert {item["id"] for item in release["items"]} == {
        "access_control",
        "active_results",
        "browser_security_policy",
        "cli_entrypoints",
        "generated_artifacts",
        "pipeline_state",
        "profile_outputs",
        "web_security_posture",
        "web_static",
        "workspace_disk_space",
        "workspace_store_integrity",
    }
    readiness = data_provider.get_release_readiness("canslim_score_rank")
    assert readiness["ok"] is True
    assert readiness["status"] == "degraded"
    assert readiness["summary"] == release["summary"]
    assert readiness["next_actions"] == release["next_actions"]
    assert readiness["diagnostics"]["summary"] == diagnostics["summary"]
    assert readiness["security"]["summary"] == diagnostics["security"]["summary"]
    assert readiness["deployment"]["commands"][0]["id"] == "local"


def test_operational_diagnostics_treats_empty_profile_outputs_as_generated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project = tmp_path
    profile_dir = project / "config" / "profiles"
    processed_dir = project / "data" / "processed"
    raw_dir = project / "data" / "raw"
    workspace_dir = project / "data" / "web_workspace"
    web_assets = project / "web" / "assets"
    profile_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    workspace_dir.mkdir(parents=True)
    web_assets.mkdir(parents=True)
    (project / "config" / "base.json").write_text("{}")
    (profile_dir / "canslim_score_rank.json").write_text("{}")
    (profile_dir / "canslim_empty.json").write_text("{}")
    (web_assets.parent / "index.html").write_text("<html></html>")
    (web_assets / "app.js").write_text("console.log('ok');")
    (web_assets / "app.css").write_text("body{}")
    (project / "run_screener.py").write_text("print('ok')\n")
    screener = project / "screener"
    screener.write_text("#!/bin/sh\n")
    screener.chmod(0o755)
    (processed_dir / "results_canslim_score_rank.csv").write_text("ticker,canslim_score\n")
    (processed_dir / "results_canslim_empty.csv").write_text("ticker,canslim_score\n")

    monkeypatch.setattr(data_provider, "PROJECT_ROOT", project)
    monkeypatch.setattr(data_provider, "CONFIG_PATH", project / "config" / "base.json")
    monkeypatch.setattr(data_provider, "PROFILE_DIR", profile_dir)
    monkeypatch.setattr(
        data_provider,
        "load_profile_config",
        lambda profile=None: {
            "profile_name": profile or "canslim_score_rank",
            "data_paths": {
                "raw_data_dir": "data/raw",
                "processed_data_dir": "data/processed",
                "output_file": f"data/processed/results_{profile or 'canslim_score_rank'}.csv",
            },
        },
    )
    monkeypatch.setattr(
        data_provider,
        "collect_pipeline_status",
        lambda config: {
            "download_ready": True,
            "parse_ready": True,
            "enrich_ready": True,
            "institutional_ready": True,
            "screen_ready": True,
            "next_action": "none",
        },
    )
    monkeypatch.setattr(
        data_provider.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(total=20 * 1024**3, used=10 * 1024**3, free=10 * 1024**3),
    )

    diagnostics = data_provider.get_operational_diagnostics("canslim_score_rank")

    checks = {check["id"]: check for check in diagnostics["checks"]}
    assert checks["profile_outputs"]["level"] == "ready"
    assert checks["profile_outputs"]["detail"] == "2/2 generated · 2 empty"
    assert checks["profile_outputs"]["next_action"] == ""


def test_diagnostic_workspace_disk_space_warns_and_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace_dir = tmp_path / "data" / "web_workspace"
    workspace_dir.mkdir(parents=True)

    monkeypatch.setattr(
        data_provider.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(total=1024**3, used=824 * 1024**2, free=200 * 1024**2),
    )
    level, detail, path = data_provider._diagnostic_workspace_disk_space(workspace_dir)
    assert level == "warning"
    assert detail == "200.0 MiB free; backups may fail"
    assert path == workspace_dir

    monkeypatch.setattr(
        data_provider.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(total=1024**3, used=1004 * 1024**2, free=20 * 1024**2),
    )
    level, detail, path = data_provider._diagnostic_workspace_disk_space(workspace_dir)
    assert level == "blocked"
    assert detail == "20.0 MiB free; workspace writes may fail"
    assert path == workspace_dir


def test_operational_diagnostics_blocks_corrupt_workspace_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project = tmp_path
    profile_dir = project / "config" / "profiles"
    processed_dir = project / "data" / "processed"
    raw_dir = project / "data" / "raw"
    workspace_dir = project / "data" / "web_workspace"
    web_assets = project / "web" / "assets"
    profile_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    workspace_dir.mkdir(parents=True)
    web_assets.mkdir(parents=True)
    (project / "config" / "base.json").write_text("{}")
    (profile_dir / "canslim_score_rank.json").write_text("{}")
    (web_assets.parent / "index.html").write_text("<html></html>")
    (web_assets / "app.js").write_text("console.log('ok');")
    (web_assets / "app.css").write_text("body{}")
    (project / "run_screener.py").write_text("print('ok')\n")
    screener = project / "screener"
    screener.write_text("#!/bin/sh\n")
    screener.chmod(0o755)
    (processed_dir / "results_canslim_score_rank.csv").write_text("ticker,canslim_score\nIESC,91\n")
    (workspace_dir / "review_queue.json").write_text('{"profiles": ')

    monkeypatch.setattr(data_provider, "PROJECT_ROOT", project)
    monkeypatch.setattr(data_provider, "CONFIG_PATH", project / "config" / "base.json")
    monkeypatch.setattr(data_provider, "PROFILE_DIR", profile_dir)
    monkeypatch.setattr(
        data_provider,
        "load_profile_config",
        lambda profile=None: {
            "profile_name": profile or "canslim_score_rank",
            "data_paths": {
                "raw_data_dir": "data/raw",
                "processed_data_dir": "data/processed",
                "output_file": f"data/processed/results_{profile or 'canslim_score_rank'}.csv",
            },
        },
    )
    monkeypatch.setattr(
        data_provider,
        "collect_pipeline_status",
        lambda config: {
            "download_ready": True,
            "parse_ready": True,
            "enrich_ready": True,
            "institutional_ready": True,
            "screen_ready": True,
            "next_action": "none",
        },
    )

    diagnostics = data_provider.get_operational_diagnostics("canslim_score_rank")

    checks = {check["id"]: check for check in diagnostics["checks"]}
    assert diagnostics["level"] == "blocked"
    assert checks["workspace_store_integrity"]["level"] == "blocked"
    assert checks["workspace_store_integrity"]["detail"] == "review queue store is not valid JSON"
    assert checks["workspace_store_integrity"]["path"] == "data/web_workspace/review_queue.json"
    assert checks["workspace_store_integrity"]["next_action"] == "open-workspace-backups"
    assert diagnostics["release_readiness"]["level"] == "blocked"
    assert "open-workspace-backups" in diagnostics["release_readiness"]["next_actions"]
    readiness = data_provider.get_release_readiness("canslim_score_rank")
    assert readiness["ok"] is False
    assert readiness["status"] == "blocked"


def test_operational_diagnostics_blocks_corrupt_workspace_audit_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    project = tmp_path
    profile_dir = project / "config" / "profiles"
    processed_dir = project / "data" / "processed"
    raw_dir = project / "data" / "raw"
    workspace_dir = project / "data" / "web_workspace"
    web_assets = project / "web" / "assets"
    profile_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    workspace_dir.mkdir(parents=True)
    web_assets.mkdir(parents=True)
    (project / "config" / "base.json").write_text("{}")
    (profile_dir / "canslim_score_rank.json").write_text("{}")
    (web_assets.parent / "index.html").write_text("<html></html>")
    (web_assets / "app.js").write_text("console.log('ok');")
    (web_assets / "app.css").write_text("body{}")
    (project / "run_screener.py").write_text("print('ok')\n")
    screener = project / "screener"
    screener.write_text("#!/bin/sh\n")
    screener.chmod(0o755)
    (processed_dir / "results_canslim_score_rank.csv").write_text("ticker,canslim_score\nIESC,91\n")
    (workspace_dir / "workspace_audit.json").write_text('{"events": {}}')

    monkeypatch.setattr(data_provider, "PROJECT_ROOT", project)
    monkeypatch.setattr(data_provider, "CONFIG_PATH", project / "config" / "base.json")
    monkeypatch.setattr(data_provider, "PROFILE_DIR", profile_dir)
    monkeypatch.setattr(
        data_provider,
        "load_profile_config",
        lambda profile=None: {
            "profile_name": profile or "canslim_score_rank",
            "data_paths": {
                "raw_data_dir": "data/raw",
                "processed_data_dir": "data/processed",
                "output_file": f"data/processed/results_{profile or 'canslim_score_rank'}.csv",
            },
        },
    )
    monkeypatch.setattr(
        data_provider,
        "collect_pipeline_status",
        lambda config: {
            "download_ready": True,
            "parse_ready": True,
            "enrich_ready": True,
            "institutional_ready": True,
            "screen_ready": True,
            "next_action": "none",
        },
    )

    diagnostics = data_provider.get_operational_diagnostics("canslim_score_rank")

    checks = {check["id"]: check for check in diagnostics["checks"]}
    assert diagnostics["level"] == "blocked"
    assert checks["workspace_store_integrity"]["level"] == "blocked"
    assert checks["workspace_store_integrity"]["detail"] == "workspace audit events must be a JSON array"
    assert checks["workspace_store_integrity"]["path"] == "data/web_workspace/workspace_audit.json"
    assert checks["workspace_store_integrity"]["next_action"] == "repair-workspace-audit"


def test_operational_diagnostics_warns_on_interrupted_workspace_temp_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    project = tmp_path
    profile_dir = project / "config" / "profiles"
    processed_dir = project / "data" / "processed"
    raw_dir = project / "data" / "raw"
    workspace_dir = project / "data" / "web_workspace"
    backups_dir = workspace_dir / "backups"
    web_assets = project / "web" / "assets"
    profile_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    backups_dir.mkdir(parents=True)
    web_assets.mkdir(parents=True)
    (project / "config" / "base.json").write_text("{}")
    (profile_dir / "canslim_score_rank.json").write_text("{}")
    (web_assets.parent / "index.html").write_text("<html></html>")
    (web_assets / "app.js").write_text("console.log('ok');")
    (web_assets / "app.css").write_text("body{}")
    (project / "run_screener.py").write_text("print('ok')\n")
    screener = project / "screener"
    screener.write_text("#!/bin/sh\n")
    screener.chmod(0o755)
    (processed_dir / "results_canslim_score_rank.csv").write_text("ticker,canslim_score\nIESC,91\n")
    preferences_temp = workspace_dir / ".preferences.json.interrupted.tmp"
    backup_temp = backups_dir / ".canslim-workspace-backup-canslim_score_rank-20260526T100000Z.json.interrupted.tmp"
    ignored_temp = workspace_dir / "preferences.json.tmp"
    preferences_temp.write_text("{}")
    backup_temp.write_text("{}")
    ignored_temp.write_text("{}")

    monkeypatch.setattr(data_provider, "PROJECT_ROOT", project)
    monkeypatch.setattr(data_provider, "CONFIG_PATH", project / "config" / "base.json")
    monkeypatch.setattr(data_provider, "PROFILE_DIR", profile_dir)
    monkeypatch.setattr(
        data_provider,
        "load_profile_config",
        lambda profile=None: {
            "profile_name": profile or "canslim_score_rank",
            "data_paths": {
                "raw_data_dir": "data/raw",
                "processed_data_dir": "data/processed",
                "output_file": f"data/processed/results_{profile or 'canslim_score_rank'}.csv",
            },
        },
    )
    monkeypatch.setattr(
        data_provider,
        "collect_pipeline_status",
        lambda config: {
            "download_ready": True,
            "parse_ready": True,
            "enrich_ready": True,
            "institutional_ready": True,
            "screen_ready": True,
            "next_action": "none",
        },
    )

    diagnostics = data_provider.get_operational_diagnostics("canslim_score_rank")

    checks = {check["id"]: check for check in diagnostics["checks"]}
    assert diagnostics["level"] == "warning"
    assert checks["workspace_atomic_temps"]["level"] == "warning"
    assert checks["workspace_atomic_temps"]["detail"] == "2 interrupted write temp file(s) present"
    assert checks["workspace_atomic_temps"]["next_action"] == "cleanup-workspace-temps"
    assert checks["workspace_atomic_temps"]["path"] in {
        "data/web_workspace/.preferences.json.interrupted.tmp",
        "data/web_workspace/backups/.canslim-workspace-backup-canslim_score_rank-20260526T100000Z.json.interrupted.tmp",
    }

    cleanup = data_provider.cleanup_workspace_atomic_temp_files()

    assert cleanup["deleted_count"] == 2
    assert cleanup["failed_count"] == 0
    assert not preferences_temp.exists()
    assert not backup_temp.exists()
    assert ignored_temp.exists()

    diagnostics = data_provider.get_operational_diagnostics("canslim_score_rank")
    checks = {check["id"]: check for check in diagnostics["checks"]}
    assert checks["workspace_atomic_temps"]["level"] == "ready"
    assert checks["workspace_atomic_temps"]["next_action"] == ""


def test_get_candidates_returns_normalized_sort_metadata(monkeypatch):
    monkeypatch.setattr(data_provider, "load_profile_config", lambda profile=None: {"profile_name": "canslim_score_rank", "data_paths": {"output_file": "data/processed/results.csv"}})
    monkeypatch.setattr(data_provider, "_result_path", lambda config: data_provider.PROJECT_ROOT / "data" / "processed" / "results.csv")
    monkeypatch.setattr(
        data_provider,
        "_load_candidate_rows",
        lambda path: (
            [
                {"ticker": "AAA", "canslim_score": 80.0, "rs_rating": 92.0},
                {"ticker": "BBB", "canslim_score": 90.0, "rs_rating": 70.0},
            ],
            None,
        ),
    )

    payload = data_provider.get_candidates(sort_by="rs", sort_dir="desc")

    assert payload["sort"] == {"by": "rs", "dir": "desc"}
    assert [row["ticker"] for row in payload["candidates"]] == ["AAA", "BBB"]


def test_export_candidates_applies_filters_and_escapes_formula_text(monkeypatch):
    monkeypatch.setattr(
        data_provider,
        "load_profile_config",
        lambda profile=None: {
            "profile_name": "canslim_score_rank",
            "data_paths": {"output_file": "data/processed/results.csv"},
        },
    )
    monkeypatch.setattr(
        data_provider,
        "_result_path",
        lambda config: data_provider.PROJECT_ROOT / "data" / "processed" / "results.csv",
    )
    monkeypatch.setattr(
        data_provider,
        "_load_candidate_rows",
        lambda path: (
            [
                {
                    "ticker": "SAFE",
                    "name": "=FORMULA",
                    "canslim_score": 92.0,
                    "setup_status": "near_pivot",
                    "rs_rating": 91.0,
                },
                {
                    "ticker": "LOW",
                    "name": "Low Score",
                    "canslim_score": 65.0,
                    "setup_status": "near_pivot",
                    "rs_rating": 80.0,
                },
            ],
            None,
        ),
    )

    export = data_provider.export_candidates(
        "canslim_score_rank",
        min_score=70,
        setup="near_pivot",
        sort_by="score",
        sort_dir="desc",
    )

    rows = list(csv.DictReader(io.StringIO(export["body"])))
    assert export["filename"] == "canslim-screener-canslim_score_rank-near_pivot-score70.csv"
    assert export["content_type"] == "text/csv; charset=utf-8"
    assert [row["ticker"] for row in rows] == ["SAFE"]
    assert rows[0]["name"] == "'=FORMULA"
    assert rows[0]["action"] == "watch_breakout"


def test_get_candidate_comparison_returns_requested_rows(monkeypatch):
    monkeypatch.setattr(
        data_provider,
        "load_profile_config",
        lambda profile=None: {
            "profile_name": "canslim_score_rank",
            "data_paths": {"output_file": "data/processed/results.csv"},
        },
    )
    monkeypatch.setattr(
        data_provider,
        "_result_path",
        lambda config: data_provider.PROJECT_ROOT / "data" / "processed" / "results.csv",
    )
    monkeypatch.setattr(
        data_provider,
        "_load_candidate_rows",
        lambda path: (
            [
                {
                    "ticker": "AAA",
                    "name": "Alpha",
                    "canslim_score": 91,
                    "rs_rating": 88,
                    "quarterly_eps_growth": 0.42,
                    "revenue_growth": 0.18,
                    "setup_status": "near_pivot",
                    "pivot_distance_pct": -2.5,
                    "pass_reasons": ["C", "A"],
                    "fail_reasons": ["volume"],
                },
                {
                    "ticker": "BBB",
                    "name": "Beta",
                    "canslim_score": 86,
                    "setup_status": "forming_base",
                },
            ],
            None,
        ),
    )

    payload = data_provider.get_candidate_comparison("canslim_score_rank", tickers="BBB,AAA,MISS,AAA")

    assert payload["profile"] == "canslim_score_rank"
    assert payload["tickers"] == ["BBB", "AAA", "MISS"]
    assert payload["missing"] == ["MISS"]
    assert [row["ticker"] for row in payload["candidates"]] == ["BBB", "AAA"]
    assert payload["candidates"][1]["action"] == "watch_breakout"
    assert payload["candidates"][1]["pass_count"] == 2
    assert payload["candidates"][1]["watch_count"] == 1


def test_get_profile_summary_formats_strategy_rules(tmp_path: Path, monkeypatch):
    project = tmp_path
    processed_dir = project / "data" / "processed"
    processed_dir.mkdir(parents=True)
    results_csv = processed_dir / "results_alpha.csv"
    results_csv.write_text("ticker,canslim_score\nIESC,91\nMYRG,89\n")

    monkeypatch.setattr(data_provider, "PROJECT_ROOT", project)
    monkeypatch.setattr(
        data_provider,
        "load_profile_config",
        lambda profile=None: {
            "profile_name": "alpha_profile",
            "config_path": "config/base.json",
            "data_paths": {"output_file": "data/processed/results_alpha.csv"},
            "screening_criteria": {
                "quarterly_eps_growth": 0.1,
                "annual_eps_cagr": 0.15,
                "revenue_growth": 0.08,
                "profit_margin": 0.03,
                "roe": 0.12,
                "debt_to_equity": 3,
                "outperform_sp500": True,
                "min_market_cap": 300_000_000,
            },
            "leadership_criteria": {
                "rs_rating_min": 60,
                "price_vs_52w_high_min": 0.75,
                "avg_dollar_volume_min": 5_000_000,
            },
            "market_direction": {"required": False},
            "supply_demand_criteria": {"require_supply_demand": True},
            "institutional_criteria": {"require_institutional_sponsorship": False},
            "pattern_criteria": {"require_near_pivot": True, "require_valid_breakout": False},
        },
    )

    payload = data_provider.get_profile_summary("alpha_profile")

    assert payload["profile"] == "alpha_profile"
    assert payload["label"] == "alpha profile"
    assert payload["result_file"] == "data/processed/results_alpha.csv"
    assert payload["candidate_count"] == 2
    assert {"group": "Growth", "label": "Q EPS", "value": "≥ 10%", "source": "quarterly_eps_growth"} in payload["rules"]
    assert {"group": "Liquidity", "label": "Market cap", "value": "≥ $300M", "source": "min_market_cap"} in payload["rules"]
    assert {"group": "Leadership", "label": "S&P 500", "value": "Outperform", "source": "screening_criteria.outperform_sp500"} in payload["rules"]
    assert payload["requirements"] == [
        {"label": "Market", "value": "Optional", "required": False, "source": "market_direction.required"},
        {"label": "Supply", "value": "Required", "required": True, "source": "supply_demand_criteria.require_supply_demand"},
        {
            "label": "Institutional",
            "value": "Optional",
            "required": False,
            "source": "institutional_criteria.require_institutional_sponsorship",
        },
        {
            "label": "Industry",
            "value": "Optional",
            "required": False,
            "source": "leadership_criteria.require_industry_leadership",
        },
        {"label": "Near pivot", "value": "Required", "required": True, "source": "pattern_criteria.require_near_pivot"},
        {
            "label": "Breakout",
            "value": "Optional",
            "required": False,
            "source": "pattern_criteria.require_valid_breakout",
        },
    ]


def test_export_stock_dossier_builds_auditable_payload(tmp_path: Path, monkeypatch):
    project = tmp_path
    processed_dir = project / "data" / "processed"
    processed_dir.mkdir(parents=True)
    results_csv = processed_dir / "results_alpha.csv"
    results_csv.write_text("ticker,canslim_score\nIESC,91\n")

    config = {
        "profile_name": "alpha_profile",
        "config_path": "config/base.json",
        "data_paths": {"output_file": "data/processed/results_alpha.csv"},
        "screening_criteria": {"quarterly_eps_growth": 0.1},
    }
    monkeypatch.setattr(data_provider, "PROJECT_ROOT", project)
    monkeypatch.setattr(data_provider, "load_profile_config", lambda profile=None: config)
    monkeypatch.setattr(
        data_provider,
        "analyze_ticker",
        lambda ticker, loaded_config: {
            "found": True,
            "ticker": ticker,
            "name": "IES Holdings",
            "canslim_score": 91,
            "current_price": 100,
        },
    )
    monkeypatch.setattr(data_provider, "get_price_history", lambda ticker: [{"date": "2026-05-26", "close": 100}])
    monkeypatch.setattr(data_provider, "collect_pipeline_status", lambda loaded_config: {"next_action": "none", "warnings": [], "files": {}})
    monkeypatch.setattr(data_provider, "_load_market_direction", lambda loaded_config: {"as_of": "2026-05-26"})
    monkeypatch.setattr(data_provider, "get_data_provenance", lambda profile=None: {"profile": profile, "source_count": 1, "sources": []})

    export = data_provider.export_stock_dossier("iesc", "alpha_profile")
    payload = json.loads(export["body"])

    assert export["filename"] == "canslim-dossier-alpha_profile-IESC.json"
    assert export["content_type"] == "application/json; charset=utf-8"
    assert payload["schema_version"] == 1
    assert payload["type"] == "stock_research_dossier"
    assert payload["research_only"] is True
    assert payload["research_disclosure"]["title"] == "Research aid only"
    assert payload["profile"] == "alpha_profile"
    assert payload["ticker"] == "IESC"
    assert payload["analysis"]["ticker"] == "IESC"
    assert payload["analysis"]["price_history"] == [{"date": "2026-05-26", "close": 100}]
    assert payload["profile_summary"]["rules"][0]["label"] == "Q EPS"
    assert payload["data_health"]["next_action"] == "none"
    assert payload["provenance"] == {"profile": "alpha_profile", "source_count": 1, "sources": []}


def test_summarize_action_center_prioritizes_daily_work():
    rows = [
        data_provider._project_candidate(
            {
                "ticker": "EXTD",
                "name": "Extended Co",
                "canslim_score": 98.0,
                "setup_status": "extended",
                "extended_from_pivot": True,
                "pivot_distance_pct": 0.16,
                "current_price": 116.0,
            }
        ),
        data_provider._project_candidate(
            {
                "ticker": "BUY",
                "name": "Buy Zone Co",
                "canslim_score": 91.0,
                "setup_status": "near_pivot",
                "in_buy_zone": True,
                "pivot_distance_pct": 0.02,
                "current_price": 102.0,
                "buy_zone_low": 100.0,
                "buy_zone_high": 105.0,
                "stop_loss_price": 94.0,
            }
        ),
        data_provider._project_candidate(
            {
                "ticker": "NEAR",
                "name": "Near Pivot Co",
                "canslim_score": 88.0,
                "setup_status": "near_pivot",
                "pivot_distance_pct": -0.01,
                "current_price": 99.0,
            }
        ),
    ]

    payload = data_provider.summarize_action_center(
        rows,
        {"recommended_exposure": 0.8, "market_direction_status": "confirmed_uptrend"},
        {"next_action": "none", "recommended_commands": []},
    )

    assert payload["posture"] == "risk_on"
    assert payload["high_quality_count"] == 3
    assert payload["action_counts"] == {
        "actionable": 1,
        "watch_breakout": 1,
        "building_base": 0,
        "extended": 1,
        "research": 0,
    }
    assert [candidate["ticker"] for candidate in payload["focus_candidates"]] == ["BUY", "NEAR", "EXTD"]
    assert payload["focus_candidates"][0]["reason"] == "Inside buy zone"
    assert payload["tasks"][0]["label"] == "1 candidate(s) in buy zone"


def test_summarize_decision_brief_surfaces_session_call_to_action():
    rows = [
        data_provider._project_candidate(
            {
                "ticker": "BUY",
                "name": "Buy Zone Co",
                "canslim_score": 91.0,
                "setup_status": "near_pivot",
                "in_buy_zone": True,
                "pivot_distance_pct": 0.02,
                "current_price": 102.0,
                "buy_zone_low": 100.0,
                "buy_zone_high": 105.0,
                "stop_loss_price": 94.0,
            }
        ),
        data_provider._project_candidate(
            {
                "ticker": "BASE",
                "name": "Base Co",
                "canslim_score": 88.0,
                "setup_status": "forming_base",
                "pivot_distance_pct": -0.08,
                "current_price": 92.0,
            }
        ),
    ]
    health = {
        "level": "ready",
        "next_action": "none",
        "ready_checks": 5,
        "total_checks": 5,
        "source_findings": [],
        "recommended_commands": [],
    }

    payload = data_provider.summarize_decision_brief(
        rows,
        {"recommended_exposure": 0.8, "market_direction_status": "confirmed_uptrend"},
        {"next_action": "none"},
        data_health=health,
        candidate_quality={"level": "ready", "summary": "6/6 critical fields ready", "issue_rows": []},
    )

    assert payload["level"] == "ready"
    assert payload["title"] == "Validate entries"
    assert payload["metrics"][0] == {
        "label": "Data",
        "value": "Ready",
        "detail": "5/5 checks",
        "level": "ready",
    }
    assert payload["metrics"][2]["detail"] == "1 buy zone · 0 pivot · 1 base"
    assert [item["ticker"] for item in payload["focus"]] == ["BUY", "BASE"]
    assert payload["next_steps"][0]["label"] == "Validate buy-zone setups"


def test_summarize_decision_brief_prioritizes_pipeline_blockers():
    payload = data_provider.summarize_decision_brief(
        [],
        {},
        {"next_action": "screen"},
        data_health={
            "level": "needs_pipeline",
            "next_action": "screen",
            "ready_checks": 4,
            "total_checks": 5,
            "recommended_commands": ["python run_screener.py --mode screen"],
            "source_findings": [
                {
                    "level": "missing",
                    "label": "Screen results",
                    "detail": "Result CSV is missing or empty.",
                    "next_action": "screen",
                }
            ],
        },
        action_center={
            "action_counts": {},
            "high_quality_count": 0,
            "recommended_exposure": None,
            "focus_candidates": [],
            "tasks": [],
        },
        candidate_quality={"level": "blocked", "summary": "No candidate rows", "issue_rows": []},
    )

    assert payload["level"] == "blocked"
    assert payload["title"] == "Pipeline first"
    assert payload["blockers"][0]["level"] == "blocked"
    assert payload["next_steps"][0] == {
        "kind": "pipeline",
        "label": "Run screen",
        "detail": "python run_screener.py --mode screen",
        "action": "screen",
        "priority": "high",
    }


def test_get_review_items_for_tickers_parses_tradingview_symbols_and_failures(monkeypatch):
    monkeypatch.setattr(
        data_provider,
        "load_profile_config",
        lambda profile=None: {"profile_name": "canslim_score_rank"},
    )

    def fake_analyze_ticker(ticker, config):
        if ticker == "NOPE":
            return {"found": False, "ticker": ticker}
        return {
            "found": True,
            "ticker": ticker,
            "name": f"{ticker} Company",
            "sector": "Technology",
            "industry": "Software",
            "current_price": 100.0,
            "pivot_price": 105.0,
            "buy_zone_low": 105.0,
            "buy_zone_high": 110.25,
            "stop_loss_price": 96.6,
            "profit_target_low": 126.0,
            "profit_target_high": 131.25,
            "canslim_score": 91.5,
            "score_band": "excellent",
            "setup_status": "near_pivot",
            "c_score": 90.0,
        }

    monkeypatch.setattr(data_provider, "analyze_ticker", fake_analyze_ticker)

    payload = data_provider.get_review_items_for_tickers(
        "NASDAQ:iesc, BRK.B bad/ticker NOPE IESC",
        "canslim_score_rank",
        limit=3,
    )

    assert payload["requested"] == ["IESC", "BRK-B", "NOPE"]
    assert payload["truncated_count"] == 0
    assert [item["ticker"] for item in payload["items"]] == ["IESC", "BRK-B"]
    assert payload["items"][0]["profile"] == "canslim_score_rank"
    assert payload["items"][0]["sector"] == "Technology"
    assert payload["items"][0]["industry"] == "Software"
    assert payload["items"][0]["buy_zone_low"] == 105.0
    assert payload["items"][0]["stop_loss_price"] == 96.6
    assert payload["failures"] == [
        {"ticker": "bad/ticker", "error": "Invalid ticker format"},
        {"ticker": "NOPE", "error": "Ticker was not found in the enriched company list"},
    ]


def test_get_data_provenance_reports_source_metadata(tmp_path: Path, monkeypatch):
    project = tmp_path
    config_dir = project / "config"
    profile_dir = config_dir / "profiles"
    processed_dir = project / "data" / "processed"
    profile_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)
    base_config = config_dir / "base.json"
    profile_config = profile_dir / "canslim_score_rank.json"
    results_csv = processed_dir / "results.csv"
    market_direction = processed_dir / "market_direction.json"
    enriched = processed_dir / "companies_list_enriched.json"
    companies = processed_dir / "companies_list.json"
    metrics = processed_dir / "financial_metrics.parquet"
    base_config.write_text("{}")
    profile_config.write_text("{}")
    results_csv.write_text("ticker,canslim_score,setup_status\nIESC,91,near_pivot\n")
    market_direction.write_text('{"as_of": "2026-05-26"}')
    enriched.write_text("[]")
    companies.write_text("[]")
    metrics.write_text("metrics")

    monkeypatch.setattr(data_provider, "PROJECT_ROOT", project)
    monkeypatch.setattr(data_provider, "CONFIG_PATH", base_config)
    monkeypatch.setattr(data_provider, "PROFILE_DIR", profile_dir)
    monkeypatch.setattr(
        data_provider,
        "load_profile_config",
        lambda profile=None: {
            "profile_name": "canslim_score_rank",
            "config_path": "config/base.json",
            "data_paths": {
                "output_file": "data/processed/results.csv",
                "processed_data_dir": "data/processed",
            },
        },
    )
    monkeypatch.setattr(data_provider, "_load_market_direction", lambda config: {"as_of": "2026-05-26"})
    monkeypatch.setattr(
        data_provider,
        "collect_pipeline_status",
        lambda config: {
            "download_ready": True,
            "parse_ready": True,
            "enrich_ready": True,
            "institutional_ready": True,
            "screen_ready": True,
            "facts_count": 10,
            "company_count": 5,
            "leadership_count": 4,
            "institutional_count": 3,
            "next_action": "none",
            "recommended_commands": [],
            "warnings": [],
            "files": {
                "results_csv": {"path": "data/processed/results.csv"},
                "market_direction": {"path": "data/processed/market_direction.json"},
                "companies_list_enriched": {"path": "data/processed/companies_list_enriched.json"},
                "companies_list": {"path": "data/processed/companies_list.json"},
                "financial_metrics": {"path": "data/processed/financial_metrics.parquet"},
                "cusip_ticker_mapping": {"path": "data/processed/cusip_ticker_mapping.csv"},
            },
        },
    )

    payload = data_provider.get_data_provenance("canslim_score_rank")

    sources = {source["id"]: source for source in payload["sources"]}
    assert payload["profile"] == "canslim_score_rank"
    assert payload["missing_required"] == []
    assert payload["stale_sources"] == []
    assert payload["readiness_pct"] == 100
    assert sources["results_csv"]["path"] == "data/processed/results.csv"
    assert sources["results_csv"]["rows"] == 1
    assert len(sources["results_csv"]["sha256_12"]) == 12
    assert sources["cusip_ticker_mapping"]["exists"] is False
    assert sources["cusip_ticker_mapping"]["required"] is False


def test_get_artifacts_lists_and_validates_allowlisted_downloads(tmp_path: Path, monkeypatch):
    project = tmp_path
    processed_dir = project / "data" / "processed"
    processed_dir.mkdir(parents=True)
    results_csv = processed_dir / "alpha.csv"
    results_md = processed_dir / "alpha.md"
    watchlist = processed_dir / "alpha_tradingview_watchlist.txt"
    results_csv.write_text("ticker,canslim_score\nIESC,91\n")
    results_md.write_text("# Alpha report\n")
    watchlist.write_text("IESC\n")

    monkeypatch.setattr(data_provider, "PROJECT_ROOT", project)
    monkeypatch.setattr(
        data_provider,
        "load_profile_config",
        lambda profile=None: {
            "profile_name": "canslim_score_rank",
            "data_paths": {"output_file": "data/processed/alpha.csv"},
        },
    )

    payload = data_provider.get_artifacts("canslim_score_rank")

    artifacts = {artifact["id"]: artifact for artifact in payload["artifacts"]}
    assert payload["profile"] == "canslim_score_rank"
    assert artifacts["results_csv"]["exists"] is True
    assert artifacts["results_csv"]["rows"] == 1
    assert artifacts["results_csv"]["path"] == "data/processed/alpha.csv"
    assert artifacts["results_csv"]["content_type"] == "text/csv; charset=utf-8"
    assert artifacts["results_csv"]["download_url"] == (
        "/api/artifacts/download?profile=canslim_score_rank&id=results_csv"
    )
    assert artifacts["results_md"]["filename"] == "alpha.md"
    assert artifacts["tradingview_watchlist"]["exists"] is True
    assert artifacts["tradingview_review_plan"]["exists"] is False

    artifact_file = data_provider.get_artifact_file("results_csv", "canslim_score_rank")
    assert artifact_file["path"] == results_csv.resolve()
    assert artifact_file["filename"] == "alpha.csv"

    with pytest.raises(ValueError, match="artifact id must be one of"):
        data_provider.get_artifact_file("../../../etc/passwd", "canslim_score_rank")
    with pytest.raises(FileNotFoundError, match="TradingView review plan"):
        data_provider.get_artifact_file("tradingview_review_plan", "canslim_score_rank")


def test_summarize_data_health_surfaces_next_pipeline_action():
    now = dt.datetime(2026, 5, 26, 12, tzinfo=dt.timezone.utc)
    status = {
        "download_ready": True,
        "parse_ready": True,
        "enrich_ready": True,
        "institutional_ready": True,
        "screen_ready": False,
        "facts_count": 100,
        "company_count": 90,
        "leadership_count": 80,
        "institutional_count": 70,
        "next_action": "screen",
        "recommended_commands": ["python run_screener.py --mode screen --config config/base.json"],
        "warnings": [],
        "files": {"results_csv": {"path": "data/processed/results.csv"}},
    }

    health = data_provider.summarize_data_health(status, {}, [], now=now)

    assert health["level"] == "needs_pipeline"
    assert health["next_action"] == "screen"
    assert health["recommended_commands"] == ["python run_screener.py --mode screen --config config/base.json"]
    assert health["checks"][-1]["label"] == "Screen"
    assert health["checks"][-1]["ready"] is False
    assert health["source_findings"][0] == {
        "level": "missing",
        "source_id": "results_csv",
        "label": "Screen results",
        "detail": "Result CSV is missing or empty.",
        "path": "data/processed/results.csv",
        "next_action": "screen",
    }
