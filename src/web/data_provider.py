"""Data adapters used by the local browser UI.

The web UI intentionally reuses the existing CLI pipeline outputs instead of
introducing a second screening engine. Live market calls are best-effort and
fall back to local files when the network is unavailable.
"""

from __future__ import annotations

import ast
import csv
import datetime as dt
import email.utils
import hashlib
import io
import json
import math
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.screeners.ticker_analysis import analyze_ticker
from src.web import security_headers, security_posture
from src.web.disclosure import research_disclosure
from src.utils.config_loader import load_config_file
from src.utils.pipeline_status import collect_pipeline_status


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "base.json"
PROFILE_DIR = PROJECT_ROOT / "config" / "profiles"
DEFAULT_PROFILE = "canslim_score_rank"
MAX_PROVENANCE_HASH_BYTES = 25_000_000
ARTIFACT_DEFINITIONS = (
    {
        "id": "results_csv",
        "label": "Results CSV",
        "description": "Ranked screening output used by the dashboard.",
        "content_type": "text/csv; charset=utf-8",
    },
    {
        "id": "results_md",
        "label": "Markdown report",
        "description": "Human-readable screening report generated beside the CSV.",
        "content_type": "text/markdown; charset=utf-8",
    },
    {
        "id": "tradingview_watchlist",
        "label": "TradingView watchlist",
        "description": "Ticker list for TradingView watchlist import.",
        "content_type": "text/plain; charset=utf-8",
    },
    {
        "id": "tradingview_review_plan",
        "label": "TradingView review plan",
        "description": "Alert and manual review plan for shortlisted candidates.",
        "content_type": "application/json; charset=utf-8",
    },
)

_PROFILE_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_IMPORT_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,14}$")
_NUMBER_RE = re.compile(r"^-?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$", re.IGNORECASE)
TICKER_IMPORT_LIMIT = 25
CANDIDATE_COMPARE_LIMIT = 6
WORKSPACE_DISK_WARNING_BYTES = 500 * 1024 * 1024
WORKSPACE_DISK_BLOCKED_BYTES = 50 * 1024 * 1024
ACTION_PRIORITY = {
    "actionable": 0,
    "watch_breakout": 1,
    "building_base": 2,
    "extended": 3,
    "research": 4,
}
US_MARKET_TIMEZONE = "America/New_York"
US_MARKET_CLOSE = dt.time(16, 0)

STRUCTURED_FIELDS = {
    "classification_reasons",
    "component_scores",
    "fail_reasons",
    "pass_reasons",
    "setup_reasons",
    "top_accumulating_managers",
}

BOOL_FIELDS = {
    "extended_from_pivot",
    "in_buy_zone",
    "industry_group_leader",
    "industry_stock_leader",
    "is_adr",
    "is_financial",
    "is_recent_listing",
    "near_pivot",
    "new_20d_high",
    "new_52w_high",
    "recent_new_52w_high",
    "rs_line_near_high",
    "rs_line_new_high",
    "valid_breakout",
}

NUMERIC_FIELDS = {
    "annual_eps_base",
    "annual_eps_cagr",
    "annual_eps_latest",
    "annual_eps_years",
    "assets",
    "avg_dollar_volume_50d",
    "a_score",
    "base_depth_65d",
    "base_tightness_3w",
    "breakout_pct",
    "breakout_volume_ratio",
    "buy_zone_high",
    "buy_zone_low",
    "c_score",
    "canslim_score",
    "current_price",
    "debt",
    "debt_current",
    "debt_noncurrent",
    "debt_to_equity",
    "equity",
    "exited_holder_count",
    "i_score",
    "increased_holder_count",
    "industry_rs_rank",
    "industry_stock_rank",
    "institutional_accumulation_score",
    "institutional_holders",
    "institutional_holders_previous",
    "institutional_holders_qoq_change",
    "institutional_ownership",
    "institutional_shares",
    "institutional_shares_previous",
    "institutional_shares_qoq_change",
    "institutional_value",
    "institutional_value_previous",
    "institutional_value_qoq_change",
    "l_score",
    "liabilities",
    "liabilities_to_equity",
    "listing_age_days",
    "m_score",
    "market_cap",
    "market_outperformance_12m",
    "n_score",
    "new_holder_count",
    "pct_from_pivot",
    "pivot_distance_pct",
    "pivot_price",
    "price_return_12m",
    "price_return_3m",
    "price_return_6m",
    "price_return_9m",
    "price_vs_52w_high",
    "profit_margin",
    "profit_target_high",
    "profit_target_low",
    "quarterly_eps_growth",
    "quarterly_eps_latest",
    "quarterly_eps_year_ago",
    "revenue_growth",
    "revenue_latest",
    "revenue_year_ago",
    "roe",
    "rs_line_pct_from_high",
    "rs_rating",
    "rs_score",
    "s_score",
    "shares_outstanding",
    "short_days_to_cover",
    "short_interest",
    "short_percent_float",
    "short_percent_shares_outstanding",
    "short_term_debt",
    "sma_200",
    "sma_50",
    "stop_loss_price",
    "up_down_volume_ratio_50d",
    "volume_dry_up_ratio_10_50",
    "volume_trend_50_200",
}

CANDIDATE_FIELDS = [
    "ticker",
    "name",
    "sector",
    "industry",
    "current_price",
    "market_cap",
    "canslim_score",
    "score_band",
    "setup_status",
    "setup_type",
    "pivot_price",
    "pivot_distance_pct",
    "buy_zone_low",
    "buy_zone_high",
    "in_buy_zone",
    "extended_from_pivot",
    "stop_loss_price",
    "profit_target_low",
    "profit_target_high",
    "pct_from_pivot",
    "price_vs_52w_high",
    "rs_rating",
    "quarterly_eps_growth",
    "annual_eps_cagr",
    "revenue_growth",
    "roe",
    "avg_dollar_volume_50d",
    "institutional_accumulation_score",
    "institutional_ownership",
    "c_score",
    "a_score",
    "n_score",
    "s_score",
    "l_score",
    "i_score",
    "m_score",
    "pass_reasons",
    "fail_reasons",
    "setup_reasons",
]
CANDIDATE_EXPORT_FIELDS = [
    "ticker",
    "name",
    "sector",
    "industry",
    "canslim_score",
    "score_band",
    "setup_status",
    "setup_type",
    "current_price",
    "pivot_price",
    "pivot_distance_pct",
    "buy_zone_low",
    "buy_zone_high",
    "stop_loss_price",
    "profit_target_low",
    "profit_target_high",
    "rs_rating",
    "quarterly_eps_growth",
    "annual_eps_cagr",
    "revenue_growth",
    "roe",
    "market_cap",
    "avg_dollar_volume_50d",
    "institutional_accumulation_score",
    "institutional_ownership",
    "c_score",
    "a_score",
    "n_score",
    "s_score",
    "l_score",
    "i_score",
    "m_score",
    "action",
    "pass_reasons",
    "fail_reasons",
    "setup_reasons",
]

MARKET_SYMBOLS = [
    {"symbol": "SPY", "label": "S&P 500", "suffix": ""},
    {"symbol": "QQQ", "label": "Nasdaq 100 ETF", "suffix": ""},
    {"symbol": "IWM", "label": "Russell 2000 ETF", "suffix": ""},
    {"symbol": "^VIX", "label": "VIX", "suffix": ""},
    {"symbol": "^TNX", "label": "10Y yield", "suffix": "%"},
    {"symbol": "DX-Y.NYB", "label": "Dollar index", "suffix": ""},
    {"symbol": "GC=F", "label": "Gold", "suffix": ""},
    {"symbol": "CL=F", "label": "WTI crude", "suffix": ""},
]

PIPELINE_CHECKS = [
    ("download_ready", "Download", "facts_count", "company facts"),
    ("parse_ready", "Parse", "company_count", "companies"),
    ("enrich_ready", "Enrich", "leadership_count", "leadership rows"),
    ("institutional_ready", "Institutional", "institutional_count", "sponsored rows"),
    ("screen_ready", "Screen", None, "results"),
]

CANDIDATE_QUALITY_FIELDS = (
    {"key": "canslim_score", "label": "Score", "critical": True, "kind": "number"},
    {"key": "current_price", "label": "Price", "critical": True, "kind": "number"},
    {"key": "pivot_price", "label": "Pivot", "critical": True, "kind": "number"},
    {"key": "stop_loss_price", "label": "Stop", "critical": False, "kind": "number"},
    {"key": "rs_rating", "label": "RS", "critical": True, "kind": "number"},
    {"key": "quarterly_eps_growth", "label": "EPS Q", "critical": True, "kind": "number"},
    {"key": "revenue_growth", "label": "Revenue", "critical": True, "kind": "number"},
    {"key": "setup_status", "label": "Setup", "critical": False, "kind": "text"},
    {"key": "sector", "label": "Sector", "critical": False, "kind": "text"},
    {"key": "avg_dollar_volume_50d", "label": "Dollar vol", "critical": False, "kind": "number"},
    {"key": "institutional_accumulation_score", "label": "Inst. score", "critical": False, "kind": "number"},
)
TRADE_PLAN_QUALITY_FIELDS = ("current_price", "pivot_price", "buy_zone_low", "stop_loss_price")
RELEASE_READINESS_CHECK_IDS = (
    "web_static",
    "browser_security_policy",
    "web_security_posture",
    "workspace_store_integrity",
    "workspace_disk_space",
    "cli_entrypoints",
    "active_results",
    "profile_outputs",
    "generated_artifacts",
    "pipeline_state",
)

SORT_FIELDS = {
    "ticker": "ticker",
    "name": "name",
    "score": "canslim_score",
    "setup": "setup_status",
    "rs": "rs_rating",
    "eps": "quarterly_eps_growth",
    "revenue": "revenue_growth",
    "pivot": "pivot_distance_pct",
    "market_cap": "market_cap",
}
DEFAULT_SORT_BY = "score"
DEFAULT_SORT_DIR = "desc"


def available_profiles() -> list[Dict[str, Any]]:
    """Return profile metadata for the frontend selector."""
    now = dt.datetime.now(dt.timezone.utc)
    preferred = [
        "canslim_score_rank",
        "canslim_watchlist",
        "canslim_pure",
        "financials_leaders",
        "ipo_spinoff_watchlist",
        "adr_global_growth",
    ]
    names = {path.stem for path in PROFILE_DIR.glob("*.json")}
    ordered = [name for name in preferred if name in names]
    ordered.extend(sorted(names.difference(ordered)))

    profiles: list[Dict[str, Any]] = []
    for name in ordered:
        rows: list[Dict[str, Any]] = []
        result_exists = False
        result_updated_at = None
        result_age_hours = None
        state = "missing"
        try:
            config = load_profile_config(name)
            result_path = _result_path(config)
            result_exists = result_path.exists()
            result_updated_at, result_age_hours = _mtime_summary(result_path.stat().st_mtime, now) if result_exists else (None, None)
            rows, _ = _load_candidate_rows(result_path)
            count = len(rows)
            state = "ready" if count else "empty" if result_exists else "missing"
        except Exception:
            result_path = None
            count = 0
        top_score = max((_num(row.get("canslim_score"), None) or 0 for row in rows), default=None)
        profiles.append(
            {
                "name": name,
                "label": name.replace("_", " "),
                "candidate_count": count,
                "result_file": str(result_path.relative_to(PROJECT_ROOT)) if result_path else None,
                "result_exists": result_exists,
                "result_updated_at": result_updated_at,
                "result_age_hours": result_age_hours,
                "top_score": round(top_score, 2) if top_score else None,
                "state": state,
            }
        )
    return profiles


def normalize_profile(profile: str | None) -> str:
    """Return a known profile name, defaulting to the broad ranking profile."""
    candidate = (profile or DEFAULT_PROFILE).strip()
    if not _PROFILE_RE.match(candidate):
        return DEFAULT_PROFILE
    if (PROFILE_DIR / f"{candidate}.json").exists():
        return candidate
    return DEFAULT_PROFILE


def load_profile_config(profile: str | None = None) -> Dict[str, Any]:
    """Load the base configuration with an optional profile overlay."""
    profile_name = normalize_profile(profile)
    config = load_config_file(str(CONFIG_PATH), profile=profile_name)
    config["config_path"] = str(CONFIG_PATH.relative_to(PROJECT_ROOT))
    config["profile_name"] = profile_name
    return config


def get_overview(profile: str | None = None) -> Dict[str, Any]:
    """Collect dashboard-level market, status, and top-candidate data."""
    config = load_profile_config(profile)
    candidates = get_candidates(config["profile_name"], limit=300)["candidates"]
    status = collect_pipeline_status(config)
    market_direction = _load_market_direction(config)
    data_health = summarize_data_health(status, market_direction, candidates)
    candidate_quality = summarize_candidate_quality(candidates)
    action_center = summarize_action_center(candidates, market_direction, status)

    return _json_safe(
        {
            "profile": config["profile_name"],
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "profiles": available_profiles(),
            "research_disclosure": research_disclosure(),
            "profile_summary": _profile_summary_from_config(config),
            "status": status,
            "data_health": data_health,
            "market_direction": market_direction,
            "indicators": get_market_indicators(market_direction),
            "news": get_market_news(),
            "top_candidates": candidates[:6],
            "candidate_stats": summarize_candidates(candidates),
            "candidate_quality": candidate_quality,
            "action_center": action_center,
            "decision_brief": summarize_decision_brief(
                candidates,
                market_direction,
                status,
                data_health=data_health,
                action_center=action_center,
                candidate_quality=candidate_quality,
            ),
        }
    )


def get_profile_summary(profile: str | None = None) -> Dict[str, Any]:
    """Return the active profile's key screening rules for transparent UI display."""
    return _profile_summary_from_config(load_profile_config(profile))


def get_data_provenance(profile: str | None = None) -> Dict[str, Any]:
    """Return auditable source-file metadata behind the active dashboard."""
    config = load_profile_config(profile)
    profile_name = config["profile_name"]
    status = collect_pipeline_status(config)
    market_direction = _load_market_direction(config)
    now = dt.datetime.now(dt.timezone.utc)
    sources: list[Dict[str, Any]] = []
    seen: set[str] = set()

    def add_source(
        source_id: str,
        label: str,
        path_value: Any,
        *,
        required: bool = True,
        stale_after_hours: float | None = None,
    ) -> None:
        if not path_value:
            return
        path = _resolve_project_path(path_value)
        key = str(path)
        if key in seen:
            return
        seen.add(key)
        sources.append(
            _source_snapshot(
                source_id,
                label,
                path,
                now=now,
                required=required,
                stale_after_hours=stale_after_hours,
            )
        )

    add_source("base_config", "Base config", CONFIG_PATH)
    add_source("profile_config", "Profile config", PROFILE_DIR / f"{profile_name}.json")
    for source_id, label, required, stale_after_hours in [
        ("results_csv", "Screen results", True, 48),
        ("results_md", "Screen report", False, None),
        ("market_direction", "Market direction", True, 72),
        ("companies_list_enriched", "Enriched companies", True, None),
        ("financial_metrics", "Financial metrics", True, None),
        ("companies_list", "Company list", True, None),
        ("cusip_ticker_mapping", "CUSIP mapping", False, None),
        ("cusip_mapping_coverage", "Mapping coverage", False, None),
    ]:
        file_info = (status.get("files") or {}).get(source_id, {})
        add_source(source_id, label, file_info.get("path"), required=required, stale_after_hours=stale_after_hours)

    result_source = next((source for source in sources if source["id"] == "results_csv"), None)
    if result_source:
        result_source["rows"] = _count_candidate_rows(_resolve_project_path(result_source["path"])) if result_source["exists"] else 0

    missing_required = [source["id"] for source in sources if source["required"] and not source["exists"]]
    stale_sources = [
        source["id"]
        for source in sources
        if source["exists"] and source.get("stale")
    ]
    return _json_safe(
        {
            "profile": profile_name,
            "generated_at": now.isoformat(),
            "readiness_pct": summarize_data_health(status, market_direction, get_candidates(profile_name, limit=12)["candidates"])["readiness_pct"],
            "next_action": status.get("next_action"),
            "source_count": len(sources),
            "missing_required": missing_required,
            "stale_sources": stale_sources,
            "sources": sources,
        }
    )


def get_artifacts(profile: str | None = None) -> Dict[str, Any]:
    """Return downloadable generated artifacts for the active profile."""
    config = load_profile_config(profile)
    profile_name = config["profile_name"]
    output_path = _result_path(config)
    now = dt.datetime.now(dt.timezone.utc)
    return _json_safe(
        {
            "profile": profile_name,
            "generated_at": now.isoformat(),
            "artifacts": [
                _artifact_snapshot(definition, _artifact_path(output_path, definition["id"]), now=now, profile=profile_name)
                for definition in ARTIFACT_DEFINITIONS
            ],
        }
    )


def get_operational_diagnostics(
    profile: str | None = None,
    *,
    access_context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return local environment and workflow readiness checks for the dashboard."""
    config = load_profile_config(profile)
    profile_name = config["profile_name"]
    now = dt.datetime.now(dt.timezone.utc)
    status = collect_pipeline_status(config)
    result_path = _result_path(config)
    profiles = available_profiles()
    artifacts = get_artifacts(profile_name).get("artifacts", [])
    checks: list[Dict[str, Any]] = []

    def add_check(
        check_id: str,
        label: str,
        level: str,
        detail: str,
        *,
        path: Path | str | None = None,
        next_action: str = "",
    ) -> None:
        checks.append(
            {
                "id": check_id,
                "label": label,
                "level": _diagnostic_level(level),
                "detail": detail,
                "path": _relative_path(_resolve_project_path(path)) if path else "",
                "next_action": next_action,
            }
        )

    add_check(
        "project_root",
        "Project workspace",
        "ready" if PROJECT_ROOT.exists() and PROJECT_ROOT.is_dir() else "blocked",
        "workspace mounted" if PROJECT_ROOT.exists() and PROJECT_ROOT.is_dir() else "workspace directory is unavailable",
        path=PROJECT_ROOT,
    )
    add_check(
        "runtime_config",
        "Runtime config",
        "ready" if CONFIG_PATH.exists() and CONFIG_PATH.is_file() else "blocked",
        "base config readable" if CONFIG_PATH.exists() and CONFIG_PATH.is_file() else "config/base.json is missing",
        path=CONFIG_PATH,
    )
    profile_config_path = PROFILE_DIR / f"{profile_name}.json"
    add_check(
        "profile_config",
        "Active profile config",
        "ready" if profile_config_path.exists() and profile_config_path.is_file() else "blocked",
        f"{profile_name} profile loaded" if profile_config_path.exists() and profile_config_path.is_file() else "active profile file is missing",
        path=profile_config_path,
    )

    static_files = [
        PROJECT_ROOT / "web" / "index.html",
        PROJECT_ROOT / "web" / "assets" / "app.js",
        PROJECT_ROOT / "web" / "assets" / "app.css",
    ]
    missing_static = [path for path in static_files if not path.exists() or not path.is_file()]
    add_check(
        "web_static",
        "Web static bundle",
        "ready" if not missing_static else "blocked",
        "HTML/CSS/JS assets ready" if not missing_static else f"{len(missing_static)} static asset(s) missing",
        path=missing_static[0] if missing_static else PROJECT_ROOT / "web",
    )
    add_check(
        "browser_security_policy",
        "Browser security policy",
        _diagnostic_browser_security_policy_level(),
        _diagnostic_browser_security_policy_detail(),
        path=PROJECT_ROOT / "web",
    )
    security = security_posture.security_posture(project_root=PROJECT_ROOT, access_context=access_context)
    add_check(
        "web_security_posture",
        "Web security posture",
        str(security.get("level") or "warning"),
        str(security.get("summary") or "security controls unavailable"),
        path=PROJECT_ROOT / "web",
    )

    data_paths = config.get("data_paths") if isinstance(config.get("data_paths"), Mapping) else {}
    for check_id, label, key, action in [
        ("raw_data_dir", "Raw data directory", "raw_data_dir", "download"),
        ("processed_data_dir", "Processed data directory", "processed_data_dir", "screen"),
    ]:
        path = _resolve_project_path(data_paths.get(key, f"data/{'raw' if key == 'raw_data_dir' else 'processed'}"))
        level, detail = _diagnostic_directory_readiness(path)
        add_check(check_id, label, level, detail, path=path, next_action=action if level != "ready" else "")

    workspace_dir = PROJECT_ROOT / "data" / "web_workspace"
    workspace_level, workspace_detail = _diagnostic_directory_readiness(workspace_dir)
    add_check(
        "workspace_store",
        "Workspace persistence",
        workspace_level,
        workspace_detail,
        path=workspace_dir / "preferences.json",
    )
    disk_level, disk_detail, disk_path = _diagnostic_workspace_disk_space(workspace_dir)
    add_check(
        "workspace_disk_space",
        "Workspace free space",
        disk_level,
        disk_detail,
        path=disk_path,
    )
    store_level, store_detail, store_path = _diagnostic_workspace_store_integrity(workspace_dir)
    store_next_action = ""
    if store_level == "blocked":
        repairable_store_failure = (
            "not valid JSON" in store_detail
            or "root must be a JSON object" in store_detail
            or "profiles must be a JSON object" in store_detail
        )
        repairable_audit_failure = repairable_store_failure or "events must be a JSON array" in store_detail
        if store_path.name == "workspace_audit.json":
            store_next_action = "repair-workspace-audit" if repairable_audit_failure else ""
        elif store_path.name in {"preferences.json", "review_queue.json", "session_journal.json"}:
            store_next_action = "open-workspace-backups" if repairable_store_failure else ""
    add_check(
        "workspace_store_integrity",
        "Workspace store integrity",
        store_level,
        store_detail,
        path=store_path,
        next_action=store_next_action,
    )
    temp_level, temp_detail, temp_path = _diagnostic_atomic_temp_files(workspace_dir)
    add_check(
        "workspace_atomic_temps",
        "Workspace interrupted writes",
        temp_level,
        temp_detail,
        path=temp_path,
        next_action="cleanup-workspace-temps" if temp_level == "warning" else "",
    )

    run_screener = PROJECT_ROOT / "run_screener.py"
    screener = PROJECT_ROOT / "screener"
    if not run_screener.exists() or not screener.exists():
        cli_level = "blocked"
        cli_detail = "CLI entrypoint missing"
    elif not os.access(screener, os.X_OK):
        cli_level = "warning"
        cli_detail = "screener wrapper is not executable"
    else:
        cli_level = "ready"
        cli_detail = "CLI entrypoints available"
    add_check("cli_entrypoints", "Pipeline commands", cli_level, cli_detail, path=screener)

    result_exists = result_path.exists() and result_path.is_file()
    result_rows = _count_candidate_rows(result_path) if result_exists else 0
    if result_exists and result_rows:
        result_level = "ready"
        result_detail = f"{result_rows} candidate row(s)"
        result_action = ""
    elif result_exists:
        result_level = "warning"
        result_detail = "result file exists but has no candidates"
        result_action = "screen"
    else:
        result_level = "warning"
        result_detail = "active profile result CSV is missing"
        result_action = "screen"
    add_check("active_results", "Active results", result_level, result_detail, path=result_path, next_action=result_action)

    total_profiles = len(profiles)
    generated_profiles = sum(1 for item in profiles if item.get("state") in {"ready", "empty"})
    candidate_profiles = sum(1 for item in profiles if item.get("state") == "ready")
    missing_profiles = sum(1 for item in profiles if item.get("state") == "missing")
    empty_profiles = sum(1 for item in profiles if item.get("state") == "empty")
    profile_level = "ready" if total_profiles and generated_profiles == total_profiles else "warning"
    profile_detail = (
        f"{generated_profiles}/{total_profiles} generated"
        + (f" · {candidate_profiles} with candidates" if candidate_profiles else "")
        + (f" · {empty_profiles} empty" if empty_profiles else "")
        + (f" · {missing_profiles} missing" if missing_profiles else "")
    )
    add_check(
        "profile_outputs",
        "Profile outputs",
        profile_level,
        profile_detail,
        path=PROFILE_DIR,
        next_action="profile-sweep" if missing_profiles else "",
    )

    ready_artifacts = sum(1 for artifact in artifacts if artifact.get("exists"))
    artifact_total = len(artifacts)
    artifact_level = "ready" if artifact_total and ready_artifacts == artifact_total else "warning"
    missing_artifact_ids = {str(artifact.get("id") or "") for artifact in artifacts if not artifact.get("exists")}
    artifact_action = (
        "tv-export"
        if {"tradingview_watchlist", "tradingview_review_plan"} & missing_artifact_ids
        else "screen"
        if "results_md" in missing_artifact_ids
        else ""
    )
    add_check(
        "generated_artifacts",
        "Generated artifacts",
        artifact_level,
        f"{ready_artifacts}/{artifact_total} downloadable",
        path=result_path.parent,
        next_action=artifact_action if result_exists and ready_artifacts < artifact_total else "",
    )

    ready_pipeline_checks = sum(1 for key, *_ in PIPELINE_CHECKS if bool(status.get(key)))
    total_pipeline_checks = len(PIPELINE_CHECKS)
    next_action = str(status.get("next_action") or "none")
    pipeline_ready = next_action == "none" and ready_pipeline_checks == total_pipeline_checks
    add_check(
        "pipeline_state",
        "Pipeline state",
        "ready" if pipeline_ready else "warning",
        (
            f"{ready_pipeline_checks}/{total_pipeline_checks} stages ready"
            if pipeline_ready
            else f"{ready_pipeline_checks}/{total_pipeline_checks} stages ready · {next_action.replace('_', ' ')} needed"
        ),
        path=result_path,
        next_action="" if pipeline_ready else _diagnostic_next_action(next_action),
    )

    level = _diagnostic_rollup_level(checks)
    counts = {
        "ready": sum(1 for check in checks if check["level"] == "ready"),
        "warning": sum(1 for check in checks if check["level"] == "warning"),
        "blocked": sum(1 for check in checks if check["level"] == "blocked"),
    }
    return _json_safe(
        {
            "profile": profile_name,
            "generated_at": now.isoformat(),
            "level": level,
            "summary": f"{counts['ready']}/{len(checks)} ready",
            "counts": counts,
            "checks": checks,
            "security": security,
            "release_readiness": _release_readiness(checks, security),
            "deployment": _deployment_guide(access_context),
        }
    )


def get_release_readiness(
    profile: str | None = None,
    *,
    access_context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return the machine-readable release gate summary for deploy monitors."""
    diagnostics = get_operational_diagnostics(profile, access_context=access_context)
    release = diagnostics.get("release_readiness") if isinstance(diagnostics.get("release_readiness"), Mapping) else {}
    level = _diagnostic_level(str(release.get("level") or diagnostics.get("level") or "warning"))
    status = "blocked" if level == "blocked" else "degraded" if level == "warning" else "ready"
    return _json_safe(
        {
            "ok": level != "blocked",
            "status": status,
            "profile": diagnostics.get("profile"),
            "generated_at": diagnostics.get("generated_at"),
            "level": level,
            "summary": release.get("summary") or diagnostics.get("summary"),
            "recommendation": release.get("recommendation") or "",
            "counts": release.get("counts") or diagnostics.get("counts") or {},
            "next_actions": release.get("next_actions") or [],
            "gates": release.get("items") or [],
            "diagnostics": {
                "level": diagnostics.get("level"),
                "summary": diagnostics.get("summary"),
                "counts": diagnostics.get("counts") or {},
            },
            "security": {
                "level": (diagnostics.get("security") or {}).get("level")
                if isinstance(diagnostics.get("security"), Mapping)
                else None,
                "summary": (diagnostics.get("security") or {}).get("summary")
                if isinstance(diagnostics.get("security"), Mapping)
                else None,
            },
            "deployment": diagnostics.get("deployment") or _deployment_guide(access_context),
        }
    )


def cleanup_workspace_atomic_temp_files() -> Dict[str, Any]:
    """Delete interrupted atomic-write temp files under the web workspace."""
    workspace_dir = PROJECT_ROOT / "data" / "web_workspace"
    temp_files = _workspace_atomic_temp_files(workspace_dir)
    deleted: list[str] = []
    failures: list[dict[str, str]] = []
    workspace_root = workspace_dir.resolve()
    for path in temp_files:
        try:
            resolved = path.resolve()
            resolved.relative_to(workspace_root)
            path.unlink()
            deleted.append(_relative_path(resolved))
        except OSError as exc:
            failures.append({"path": _relative_path(path), "error": str(exc)})
        except ValueError:
            failures.append({"path": str(path), "error": "temp file is outside workspace"})
    return _json_safe(
        {
            "workspace": _relative_path(workspace_dir),
            "deleted_count": len(deleted),
            "failed_count": len(failures),
            "deleted": deleted,
            "failures": failures,
        }
    )


def get_artifact_file(artifact_id: str, profile: str | None = None) -> Dict[str, Any]:
    """Return a validated local file descriptor for an allowlisted artifact."""
    definition = _artifact_definition(artifact_id)
    config = load_profile_config(profile)
    output_path = _result_path(config)
    path = _artifact_path(output_path, definition["id"])
    _ensure_project_artifact_path(path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Artifact is not available: {definition['label']}")
    return {
        "id": definition["id"],
        "label": definition["label"],
        "path": path,
        "filename": path.name,
        "content_type": definition["content_type"],
    }


def _profile_summary_from_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Project profile configuration into compact decision-rule metadata."""
    profile_name = str(config.get("profile_name") or DEFAULT_PROFILE)
    output_path = _result_path(config)
    try:
        candidate_count = _count_candidate_rows(output_path)
    except Exception:
        candidate_count = 0
    rules: list[Dict[str, Any]] = []
    screening = config.get("screening_criteria") if isinstance(config.get("screening_criteria"), Mapping) else {}
    leadership = config.get("leadership_criteria") if isinstance(config.get("leadership_criteria"), Mapping) else {}

    for key, label, comparator, value_type, group in [
        ("quarterly_eps_growth", "Q EPS", "≥", "percent", "Growth"),
        ("annual_eps_cagr", "A EPS CAGR", "≥", "percent", "Growth"),
        ("revenue_growth", "Revenue", "≥", "percent", "Growth"),
        ("profit_margin", "Margin", "≥", "percent", "Quality"),
        ("roe", "ROE", "≥", "percent", "Quality"),
        ("debt_to_equity", "D/E", "≤", "number", "Quality"),
        ("min_market_cap", "Market cap", "≥", "money", "Liquidity"),
    ]:
        rule = _profile_threshold_rule(screening, key, label, comparator, value_type, group)
        if rule:
            rules.append(rule)

    if screening.get("outperform_sp500") is True:
        rules.append(
            {
                "group": "Leadership",
                "label": "S&P 500",
                "value": "Outperform",
                "source": "screening_criteria.outperform_sp500",
            }
        )

    for key, label, comparator, value_type, group in [
        ("rs_rating_min", "RS rating", "≥", "number", "Leadership"),
        ("price_vs_52w_high_min", "52W high", "≥", "percent", "Leadership"),
        ("avg_dollar_volume_min", "50D dollar vol", "≥", "money", "Liquidity"),
    ]:
        rule = _profile_threshold_rule(leadership, key, label, comparator, value_type, group)
        if rule:
            rules.append(rule)

    requirements = [
        _profile_requirement(config, "market_direction", "required", "Market"),
        _profile_requirement(config, "supply_demand_criteria", "require_supply_demand", "Supply"),
        _profile_requirement(config, "institutional_criteria", "require_institutional_sponsorship", "Institutional"),
        _profile_requirement(config, "leadership_criteria", "require_industry_leadership", "Industry"),
        _profile_requirement(config, "pattern_criteria", "require_near_pivot", "Near pivot"),
        _profile_requirement(config, "pattern_criteria", "require_valid_breakout", "Breakout"),
    ]

    return _json_safe(
        {
            "profile": profile_name,
            "label": profile_name.replace("_", " "),
            "config_path": config.get("config_path"),
            "result_file": _relative_path(output_path),
            "candidate_count": candidate_count,
            "rules": rules,
            "requirements": requirements,
        }
    )


def get_candidates(
    profile: str | None = None,
    *,
    limit: int = 80,
    query: str = "",
    min_score: float | None = None,
    setup: str = "",
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = DEFAULT_SORT_DIR,
) -> Dict[str, Any]:
    """Return rows from the active profile's screener CSV."""
    config = load_profile_config(profile)
    result_path = _result_path(config)
    rows, message = _load_candidate_rows(result_path)
    rows = [_project_candidate(row) for row in rows]

    if query:
        needle = query.strip().lower()
        rows = [
            row
            for row in rows
            if needle in str(row.get("ticker") or "").lower()
            or needle in str(row.get("name") or "").lower()
            or needle in str(row.get("sector") or "").lower()
            or needle in str(row.get("industry") or "").lower()
        ]
    if min_score is not None:
        rows = [row for row in rows if _num(row.get("canslim_score")) >= min_score]
    if setup:
        rows = [row for row in rows if str(row.get("setup_status") or "") == setup]

    normalized_sort_by, normalized_sort_dir = normalize_sort(sort_by, sort_dir)
    sort_candidates(rows, normalized_sort_by, normalized_sort_dir)
    safe_limit = max(1, min(int(limit or 80), 300))

    return _json_safe(
        {
            "profile": config["profile_name"],
            "result_file": str(result_path.relative_to(PROJECT_ROOT)),
            "message": message,
            "total": len(rows),
            "limit": safe_limit,
            "sort": {"by": normalized_sort_by, "dir": normalized_sort_dir},
            "stats": summarize_candidates(rows),
            "candidates": rows[:safe_limit],
        }
    )


def export_candidates(
    profile: str | None = None,
    *,
    query: str = "",
    min_score: float | None = None,
    setup: str = "",
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = DEFAULT_SORT_DIR,
    limit: int = 300,
) -> Dict[str, Any]:
    """Return a CSV export for the currently filtered screener view."""
    payload = get_candidates(
        profile,
        limit=limit,
        query=query,
        min_score=min_score,
        setup=setup,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    rows = payload["candidates"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CANDIDATE_EXPORT_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(_candidate_export_row(row))
    filename = f"canslim-screener-{payload['profile']}{_candidate_export_suffix(query=query, min_score=min_score, setup=setup)}.csv"
    return {
        "body": buffer.getvalue(),
        "content_type": "text/csv; charset=utf-8",
        "filename": filename,
        "profile": payload["profile"],
        "row_count": len(rows),
    }


def get_candidate_comparison(profile: str | None = None, *, tickers: Any = "") -> Dict[str, Any]:
    """Return side-by-side comparison data for requested candidate tickers."""
    requested = _comparison_tickers(tickers)
    payload = get_candidates(profile, limit=300)
    rows_by_ticker = {str(row.get("ticker") or "").upper(): row for row in payload["candidates"]}
    candidates = [_comparison_candidate(rows_by_ticker[ticker]) for ticker in requested if ticker in rows_by_ticker]
    missing = [ticker for ticker in requested if ticker not in rows_by_ticker]
    return _json_safe(
        {
            "profile": payload["profile"],
            "result_file": payload["result_file"],
            "tickers": requested,
            "missing": missing,
            "count": len(candidates),
            "max": CANDIDATE_COMPARE_LIMIT,
            "candidates": candidates,
        }
    )


def normalize_sort(sort_by: str | None, sort_dir: str | None) -> tuple[str, str]:
    """Normalize requested screener sort fields."""
    normalized_by = str(sort_by or DEFAULT_SORT_BY).strip().lower()
    if normalized_by not in SORT_FIELDS:
        normalized_by = DEFAULT_SORT_BY
    normalized_dir = str(sort_dir or DEFAULT_SORT_DIR).strip().lower()
    if normalized_dir not in {"asc", "desc"}:
        normalized_dir = DEFAULT_SORT_DIR
    return normalized_by, normalized_dir


def sort_candidates(rows: list[Dict[str, Any]], sort_by: str, sort_dir: str) -> None:
    """Sort candidate rows in-place with missing values consistently last."""
    normalized_by, normalized_dir = normalize_sort(sort_by, sort_dir)
    field = SORT_FIELDS[normalized_by]
    reverse = normalized_dir == "desc"

    numeric_sort = normalized_by not in {"ticker", "name", "setup"}
    if numeric_sort:
        rows.sort(
            key=lambda row: (
                _num(row.get(field), None) is None,
                _num(row.get(field), 0.0) or 0.0,
                str(row.get("ticker") or ""),
            ),
            reverse=reverse,
        )
        if reverse:
            missing = [row for row in rows if _num(row.get(field), None) is None]
            present = [row for row in rows if _num(row.get(field), None) is not None]
            rows[:] = present + missing
        return

    rows.sort(
        key=lambda row: (
            not str(row.get(field) or ""),
            str(row.get(field) or "").lower(),
            str(row.get("ticker") or ""),
        ),
        reverse=reverse,
    )
    if reverse:
        missing = [row for row in rows if not str(row.get(field) or "")]
        present = [row for row in rows if str(row.get(field) or "")]
        rows[:] = present + missing


def get_stock_analysis(ticker: str, profile: str | None = None) -> Dict[str, Any]:
    """Analyze one ticker through the existing CAN SLIM analyzer."""
    normalized = str(ticker or "").upper().replace(".", "-").strip()
    if not normalized:
        return {"found": False, "ticker": normalized, "error": "Ticker is required"}
    config = load_profile_config(profile)
    result = analyze_ticker(normalized, config)
    result["profile"] = config["profile_name"]
    result["price_history"] = get_price_history(normalized)
    result["research_brief"] = build_research_brief(result)
    return _json_safe(result)


def export_stock_dossier(ticker: str, profile: str | None = None) -> Dict[str, Any]:
    """Return a downloadable single-stock research dossier."""
    normalized = str(ticker or "").upper().replace(".", "-").strip()
    if not normalized:
        raise ValueError("Ticker is required")
    config = load_profile_config(profile)
    profile_name = config["profile_name"]
    analysis = get_stock_analysis(normalized, profile_name)
    if not analysis.get("found"):
        raise FileNotFoundError(f"Ticker was not found: {normalized}")

    status = collect_pipeline_status(config)
    market_direction = _load_market_direction(config)
    candidates = get_candidates(profile_name, limit=80)["candidates"]
    payload = _json_safe(
        {
            "schema_version": 1,
            "type": "stock_research_dossier",
            "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "profile": profile_name,
            "ticker": normalized,
            "research_only": True,
            "research_disclosure": research_disclosure(),
            "analysis": analysis,
            "profile_summary": _profile_summary_from_config(config),
            "data_health": summarize_data_health(status, market_direction, candidates),
            "provenance": get_data_provenance(profile_name),
        }
    )
    return {
        "body": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        "content_type": "application/json; charset=utf-8",
        "filename": f"canslim-dossier-{profile_name}-{normalized}.json",
        "payload": payload,
    }


def get_review_items_for_tickers(
    ticker_input: str | list[Any],
    profile: str | None = None,
    *,
    limit: int = TICKER_IMPORT_LIMIT,
) -> Dict[str, Any]:
    """Build review-queue items from pasted ticker symbols."""
    config = load_profile_config(profile)
    profile_name = config["profile_name"]
    parsed = parse_import_tickers(ticker_input, limit=limit)
    items: list[Dict[str, Any]] = []
    failures = list(parsed["failures"])
    for ticker in parsed["tickers"]:
        try:
            result = analyze_ticker(ticker, config)
        except Exception as exc:  # pragma: no cover - defensive per-ticker isolation
            failures.append({"ticker": ticker, "error": str(exc) or "Analysis failed"})
            continue
        if not result.get("found"):
            failures.append({"ticker": ticker, "error": "Ticker was not found in the enriched company list"})
            continue
        projected = _project_candidate(result)
        items.append(_review_item_from_projected(projected, profile_name))
    return {
        "profile": profile_name,
        "items": _json_safe(items),
        "requested": parsed["tickers"],
        "failures": failures,
        "truncated_count": parsed["truncated_count"],
        "limit": limit,
    }


def parse_import_tickers(ticker_input: str | list[Any], *, limit: int = TICKER_IMPORT_LIMIT) -> Dict[str, Any]:
    """Parse pasted watchlist text into unique normalized ticker symbols."""
    tokens = _ticker_tokens(ticker_input)
    if not tokens:
        raise ValueError("At least one ticker is required")
    tickers: list[str] = []
    seen: set[str] = set()
    failures: list[Dict[str, str]] = []
    for token in tokens:
        normalized = _normalize_import_ticker(token)
        if not normalized:
            continue
        if not _IMPORT_TICKER_RE.match(normalized):
            failures.append({"ticker": str(token).strip()[:40], "error": "Invalid ticker format"})
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        tickers.append(normalized)
    if not tickers:
        raise ValueError("At least one valid ticker is required")
    safe_limit = max(1, min(int(limit or TICKER_IMPORT_LIMIT), TICKER_IMPORT_LIMIT))
    return {
        "tickers": tickers[:safe_limit],
        "failures": failures,
        "truncated_count": max(0, len(tickers) - safe_limit),
        "limit": safe_limit,
    }


def get_market_indicators(market_direction: Mapping[str, Any] | None = None) -> list[Dict[str, Any]]:
    """Return live indicator snapshots when available."""
    indicators_by_symbol: dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(MARKET_SYMBOLS))) as executor:
        future_map = {executor.submit(_latest_quote, item["symbol"]): item for item in MARKET_SYMBOLS}
        for future in as_completed(future_map):
            item = future_map[future]
            try:
                quote = future.result()
            except Exception:
                quote = None
            if not quote:
                continue
            scale = float(item.get("scale", 1.0))
            latest = quote["latest"] * scale
            previous = quote["previous"] * scale if quote.get("previous") is not None else None
            change = latest - previous if previous not in (None, 0) else None
            change_pct = (change / previous) if previous not in (None, 0) and change is not None else None
            indicators_by_symbol[item["symbol"]] = {
                "symbol": item["symbol"],
                "label": item["label"],
                "latest": latest,
                "previous": previous,
                "change": change,
                "change_pct": change_pct,
                "suffix": item.get("suffix", ""),
                "as_of": quote.get("as_of"),
            }

    indicators: list[Dict[str, Any]] = []
    for item in MARKET_SYMBOLS:
        indicator = indicators_by_symbol.get(item["symbol"])
        if indicator:
            indicators.append(indicator)

    if not indicators and market_direction:
        latest = _num(market_direction.get("latest_close"), None)
        indicators.append(
            {
                "symbol": str(market_direction.get("benchmark", "SPY")),
                "label": "Market benchmark",
                "latest": latest,
                "previous": None,
                "change": None,
                "change_pct": market_direction.get("market_return_21d"),
                "suffix": "",
                "as_of": market_direction.get("as_of"),
            }
        )
    return indicators


def get_market_news(limit: int = 8) -> list[Dict[str, Any]]:
    """Fetch broad market headlines from a public RSS feed."""
    try:
        return _cached_market_news(_cache_bucket(300))[:limit]
    except Exception:
        return [
            {
                "title": "Live market headlines are unavailable",
                "source": "local",
                "published": None,
                "url": None,
                "summary": "Network access failed. Local market-direction and screener data are still available.",
            }
        ]


def get_price_history(ticker: str, *, period: str = "6mo") -> list[Dict[str, Any]]:
    """Return daily close history for the stock-analysis chart."""
    try:
        chart = _cached_yahoo_chart(ticker, period, "1d", _cache_bucket(300))
    except Exception:
        return []
    timestamps = chart.get("timestamps") or []
    closes = chart.get("closes") or []
    points = []
    for stamp, close in zip(timestamps, closes):
        if close is None:
            continue
        points.append(
            {
                "date": dt.datetime.fromtimestamp(stamp, dt.timezone.utc).date().isoformat(),
                "close": close,
            }
        )
    return points


def summarize_candidates(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return compact aggregates for the screener panel."""
    materialized = list(rows)
    scores = [_num(row.get("canslim_score"), None) for row in materialized]
    scores = [score for score in scores if score is not None]
    setups = Counter(str(row.get("setup_status") or "unclassified") for row in materialized)
    sectors = Counter(str(row.get("sector") or "Unknown") for row in materialized)
    return {
        "count": len(materialized),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
        "top_score": round(max(scores), 2) if scores else None,
        "exceptional": sum(1 for row in materialized if str(row.get("score_band")) == "exceptional"),
        "near_pivot": setups.get("near_pivot", 0),
        "forming_base": setups.get("forming_base", 0),
        "extended": setups.get("extended", 0),
        "setup_breakdown": dict(setups.most_common(6)),
        "sector_breakdown": dict(sectors.most_common(6)),
    }


def summarize_candidate_quality(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return field coverage and row-level quality issues for candidate data."""
    materialized = list(rows)
    row_count = len(materialized)
    if not row_count:
        return {
            "level": "blocked",
            "summary": "No candidate rows",
            "row_count": 0,
            "critical_ready": 0,
            "critical_total": sum(1 for field in CANDIDATE_QUALITY_FIELDS if field["critical"]),
            "coverage": [],
            "issue_fields": [],
            "issue_rows": [],
        }

    coverage: list[Dict[str, Any]] = []
    for field in CANDIDATE_QUALITY_FIELDS:
        present = sum(1 for row in materialized if _candidate_field_present(row, field["key"], field["kind"]))
        pct = round((present / row_count) * 100, 1)
        coverage.append(
            {
                "key": field["key"],
                "label": field["label"],
                "critical": bool(field["critical"]),
                "present": present,
                "missing": row_count - present,
                "coverage_pct": pct,
                "level": _candidate_coverage_level(pct, critical=bool(field["critical"])),
            }
        )

    critical_rows = [item for item in coverage if item["critical"]]
    critical_ready = sum(1 for item in critical_rows if item["level"] == "ready")
    worst_critical = min((float(item["coverage_pct"]) for item in critical_rows), default=0.0)
    level = "ready" if critical_ready == len(critical_rows) else "warning" if worst_critical >= 70 else "blocked"
    issue_fields = [
        item
        for item in coverage
        if item["missing"] and (item["critical"] or float(item["coverage_pct"]) < 90)
    ][:6]

    trade_plan_labels = {field["key"]: field["label"] for field in CANDIDATE_QUALITY_FIELDS}
    trade_plan_labels["buy_zone_low"] = "Buy low"
    issue_rows = []
    for row in materialized:
        if not _candidate_requires_trade_plan(row):
            continue
        missing = [
            trade_plan_labels.get(field, field.replace("_", " "))
            for field in TRADE_PLAN_QUALITY_FIELDS
            if not _candidate_field_present(row, field, "number")
        ]
        if missing:
            issue_rows.append(
                {
                    "ticker": row.get("ticker") or "",
                    "name": row.get("name") or "",
                    "missing": missing,
                    "score": _num(row.get("canslim_score"), None),
                }
            )
        if len(issue_rows) >= 8:
            break

    return _json_safe(
        {
            "level": level,
            "summary": f"{critical_ready}/{len(critical_rows)} critical fields ready",
            "row_count": row_count,
            "critical_ready": critical_ready,
            "critical_total": len(critical_rows),
            "coverage": coverage,
            "issue_fields": issue_fields,
            "issue_rows": issue_rows,
        }
    )


def summarize_action_center(
    candidates: Iterable[Mapping[str, Any]],
    market_direction: Mapping[str, Any] | None = None,
    status: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a daily operating summary for the highest-priority candidates."""
    materialized = list(candidates)
    action_counts = Counter(_candidate_action(row) for row in materialized)
    scored_count = sum(1 for row in materialized if _num(row.get("canslim_score"), None) is not None)
    high_quality_count = sum(1 for row in materialized if (_num(row.get("canslim_score"), 0) or 0) >= 85)
    exposure = _num((market_direction or {}).get("recommended_exposure"), None)
    next_action = str((status or {}).get("next_action") or "none")
    focus_candidates = sorted(
        (_action_candidate(row) for row in materialized),
        key=lambda row: (
            ACTION_PRIORITY.get(str(row.get("action") or "research"), 9),
            -(_num(row.get("canslim_score"), 0) or 0),
            abs(_num(row.get("pivot_distance_pct"), 999) or 999),
            str(row.get("ticker") or ""),
        ),
    )
    focus_candidates = [
        row
        for row in focus_candidates
        if row["action"] in {"actionable", "watch_breakout", "building_base", "extended"}
    ][:6]

    return _json_safe(
        {
            "posture": _market_posture(exposure, str((market_direction or {}).get("market_direction_status") or "")),
            "market_status": str((market_direction or {}).get("market_direction_status") or "not_collected"),
            "recommended_exposure": exposure,
            "candidate_count": len(materialized),
            "scored_count": scored_count,
            "high_quality_count": high_quality_count,
            "action_counts": {
                "actionable": action_counts.get("actionable", 0),
                "watch_breakout": action_counts.get("watch_breakout", 0),
                "building_base": action_counts.get("building_base", 0),
                "extended": action_counts.get("extended", 0),
                "research": action_counts.get("research", 0),
            },
            "focus_candidates": focus_candidates,
            "tasks": _action_tasks(action_counts, next_action, status or {}),
        }
    )


def summarize_decision_brief(
    candidates: Iterable[Mapping[str, Any]],
    market_direction: Mapping[str, Any] | None = None,
    status: Mapping[str, Any] | None = None,
    *,
    data_health: Mapping[str, Any] | None = None,
    action_center: Mapping[str, Any] | None = None,
    candidate_quality: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a first-screen trading-session decision summary."""
    materialized = list(candidates)
    health = dict(data_health or {})
    actions = dict(action_center or summarize_action_center(materialized, market_direction, status))
    quality = dict(candidate_quality or summarize_candidate_quality(materialized))
    action_counts = actions.get("action_counts") if isinstance(actions.get("action_counts"), Mapping) else {}
    actionable_count = _count_value(action_counts.get("actionable"))
    watch_count = _count_value(action_counts.get("watch_breakout"))
    base_count = _count_value(action_counts.get("building_base"))
    high_quality_count = _count_value(actions.get("high_quality_count"))
    exposure = _num(actions.get("recommended_exposure"), _num((market_direction or {}).get("recommended_exposure"), None))
    next_action = str(health.get("next_action") or (status or {}).get("next_action") or "unknown")
    health_level = str(health.get("level") or "unknown")
    quality_level = str(quality.get("level") or "warning")

    level, title, summary = _decision_brief_headline(
        candidate_count=len(materialized),
        actionable_count=actionable_count,
        watch_count=watch_count,
        high_quality_count=high_quality_count,
        exposure=exposure,
        health_level=health_level,
        quality_level=quality_level,
        next_action=next_action,
    )
    focus = [
        {
            "ticker": item.get("ticker") or "",
            "name": item.get("name") or "",
            "action": item.get("action") or "research",
            "reason": item.get("reason") or "",
            "canslim_score": item.get("canslim_score"),
            "setup_status": item.get("setup_status") or "",
            "pivot_distance_pct": item.get("pivot_distance_pct"),
        }
        for item in _as_list(actions.get("focus_candidates"))[:4]
        if isinstance(item, Mapping)
    ]
    return _json_safe(
        {
            "level": level,
            "title": title,
            "summary": summary,
            "posture": actions.get("posture") or _market_posture(exposure, str((market_direction or {}).get("market_direction_status") or "")),
            "market_status": actions.get("market_status") or str((market_direction or {}).get("market_direction_status") or "not_collected"),
            "recommended_exposure": exposure,
            "metrics": _decision_metrics(
                health,
                quality,
                exposure=exposure,
                candidate_count=len(materialized),
                actionable_count=actionable_count,
                watch_count=watch_count,
                base_count=base_count,
                high_quality_count=high_quality_count,
            ),
            "focus": focus,
            "blockers": _decision_blockers(health, quality, materialized),
            "next_steps": _decision_next_steps(
                actions,
                health,
                quality,
                actionable_count=actionable_count,
                watch_count=watch_count,
                base_count=base_count,
                candidate_count=len(materialized),
            ),
        }
    )


def summarize_data_health(
    status: Mapping[str, Any],
    market_direction: Mapping[str, Any] | None,
    candidates: Iterable[Mapping[str, Any]],
    *,
    now: dt.datetime | None = None,
) -> Dict[str, Any]:
    """Return a compact trust summary for the browser dashboard."""
    current_time = now or dt.datetime.now(dt.timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=dt.timezone.utc)

    materialized = list(candidates)
    files = status.get("files") if isinstance(status.get("files"), Mapping) else {}
    result_file = files.get("results_csv", {}) if isinstance(files, Mapping) else {}
    result_updated_at, result_age_hours = _mtime_summary(result_file.get("mtime"), current_time)
    market_as_of = (market_direction or {}).get("as_of")
    market_age_days = _date_age_days(market_as_of, current_time)
    market_session_lag = _market_session_lag(market_as_of, current_time)
    market_expected_as_of = _previous_completed_us_market_session(current_time)

    checks: list[Dict[str, Any]] = []
    for key, label, count_key, count_label in PIPELINE_CHECKS:
        value = status.get(count_key) if count_key else None
        checks.append(
            {
                "key": key,
                "label": label,
                "ready": bool(status.get(key)),
                "count": value,
                "count_label": count_label,
            }
        )

    ready_count = sum(1 for check in checks if check["ready"])
    total_count = len(checks)
    next_action = str(status.get("next_action") or "unknown")
    warnings = list(status.get("warnings") or [])
    source_findings = _data_health_source_findings(
        status,
        market_direction,
        result_file,
        result_updated_at,
        result_age_hours,
        market_age_days,
        market_session_lag,
        market_expected_as_of.isoformat() if market_expected_as_of else None,
        warnings,
    )

    if next_action != "none":
        level = "needs_pipeline"
    elif not materialized:
        level = "empty_results"
    elif result_age_hours is None:
        level = "missing_timestamp"
    elif result_age_hours > 48:
        level = "stale_results"
    elif _market_direction_stale(market_age_days, market_session_lag):
        level = "stale_market"
    elif warnings:
        level = "warning"
    else:
        level = "ready"

    return {
        "level": level,
        "candidate_count": len(materialized),
        "readiness_pct": round((ready_count / total_count) * 100, 1) if total_count else 0,
        "ready_checks": ready_count,
        "total_checks": total_count,
        "result_file": result_file.get("path"),
        "result_updated_at": result_updated_at,
        "result_age_hours": result_age_hours,
        "market_as_of": market_as_of,
        "market_age_days": market_age_days,
        "market_session_lag": market_session_lag,
        "market_expected_as_of": market_expected_as_of.isoformat() if market_expected_as_of else None,
        "next_action": next_action,
        "recommended_commands": list(status.get("recommended_commands") or []),
        "source_findings": source_findings,
        "missing_source_count": sum(1 for finding in source_findings if finding.get("level") == "missing"),
        "stale_source_count": sum(1 for finding in source_findings if finding.get("level") == "stale"),
        "warnings": warnings,
        "checks": checks,
    }


def _data_health_source_findings(
    status: Mapping[str, Any],
    market_direction: Mapping[str, Any] | None,
    result_file: Mapping[str, Any],
    result_updated_at: str | None,
    result_age_hours: float | None,
    market_age_days: int | None,
    market_session_lag: int | None,
    market_expected_as_of: str | None,
    warnings: list[Any],
) -> list[Dict[str, Any]]:
    findings: list[Dict[str, Any]] = []
    result_path = result_file.get("path")
    result_exists = bool(result_file.get("exists")) or bool(status.get("screen_ready"))
    if not result_exists or not status.get("screen_ready"):
        findings.append(
            {
                "level": "missing",
                "source_id": "results_csv",
                "label": "Screen results",
                "detail": "Result CSV is missing or empty.",
                "path": result_path,
                "next_action": "screen",
            }
        )
    elif result_age_hours is None:
        findings.append(
            {
                "level": "unknown",
                "source_id": "results_csv",
                "label": "Screen results",
                "detail": "Result CSV has no readable timestamp.",
                "path": result_path,
                "next_action": "screen",
            }
        )
    elif result_age_hours > 48:
        findings.append(
            {
                "level": "stale",
                "source_id": "results_csv",
                "label": "Screen results",
                "detail": f"Result CSV is {result_age_hours:g}h old.",
                "age_hours": result_age_hours,
                "updated_at": result_updated_at,
                "path": result_path,
                "next_action": "screen",
            }
        )

    market_as_of = (market_direction or {}).get("as_of")
    if market_direction is not None and not market_as_of:
        findings.append(
            {
                "level": "unknown",
                "source_id": "market_direction",
                "label": "Market direction",
                "detail": "Market direction has no as-of date.",
                "next_action": "enrich",
            }
        )
    elif _market_direction_stale(market_age_days, market_session_lag):
        if market_session_lag is not None:
            detail = f"Market direction is {_session_count_label(market_session_lag)} old."
        else:
            detail = f"Market direction is {market_age_days}d old."
        findings.append(
            {
                "level": "stale",
                "source_id": "market_direction",
                "label": "Market direction",
                "detail": detail,
                "age_days": market_age_days,
                "session_lag": market_session_lag,
                "as_of": market_as_of,
                "expected_as_of": market_expected_as_of,
                "next_action": "enrich",
            }
        )

    for index, warning in enumerate(warnings[:5]):
        findings.append(
            {
                "level": "warning",
                "source_id": f"pipeline_warning_{index + 1}",
                "label": "Pipeline warning",
                "detail": str(warning),
                "next_action": status.get("next_action") or "none",
            }
        )
    return findings


def _load_candidate_rows(path: Path) -> tuple[list[Dict[str, Any]], str | None]:
    if not path.exists():
        return [], f"Result file not found: {path}"
    with path.open("r", newline="") as handle:
        first_line = handle.readline()
        if not first_line.strip():
            return [], "Result file is empty."
        if first_line.startswith("No companies passed"):
            return [], first_line.strip()
        handle.seek(0)
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return [], "Result file has no CSV header."
        return [_clean_row(row) for row in reader], None


def _count_candidate_rows(path: Path) -> int:
    rows, _ = _load_candidate_rows(path)
    return len(rows)


def _clean_row(row: Mapping[str, str]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in row.items():
        cleaned[key] = _coerce_value(key, value)
    return cleaned


def _coerce_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text == "" or text.lower() in {"nan", "none", "null", "n/a"}:
            return None
        if key in STRUCTURED_FIELDS and text[:1] in {"[", "{"}:
            try:
                return ast.literal_eval(text)
            except (SyntaxError, ValueError):
                return text
        if key in BOOL_FIELDS:
            lowered = text.lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
        if key in NUMERIC_FIELDS and _NUMBER_RE.match(text):
            return _finite_float(text)
        return text
    return value


def _project_candidate(row: Mapping[str, Any]) -> Dict[str, Any]:
    output = {field: row.get(field) for field in CANDIDATE_FIELDS if field in row}
    components = row.get("component_scores")
    if isinstance(components, dict):
        output["component_scores"] = components
    else:
        output["component_scores"] = {
            "c": row.get("c_score"),
            "a": row.get("a_score"),
            "n": row.get("n_score"),
            "s": row.get("s_score"),
            "l": row.get("l_score"),
            "i": row.get("i_score"),
            "m": row.get("m_score"),
        }
    output["research_brief"] = build_research_brief({**row, "component_scores": output["component_scores"]})
    return output


def _review_item_from_projected(row: Mapping[str, Any], profile_name: str) -> Dict[str, Any]:
    brief = row.get("research_brief") if isinstance(row.get("research_brief"), Mapping) else {}
    trade_plan = brief.get("trade_plan") if isinstance(brief.get("trade_plan"), Mapping) else {}
    return {
        "ticker": str(row.get("ticker") or "").upper(),
        "name": row.get("name") or "",
        "sector": row.get("sector") or "",
        "industry": row.get("industry") or "",
        "canslim_score": row.get("canslim_score"),
        "score_band": row.get("score_band"),
        "setup_status": row.get("setup_status"),
        "current_price": row.get("current_price"),
        "pivot_price": trade_plan.get("pivot_price", row.get("pivot_price")),
        "pivot_distance_pct": trade_plan.get("pivot_distance_pct", row.get("pivot_distance_pct")),
        "buy_zone_low": trade_plan.get("buy_zone_low", row.get("buy_zone_low")),
        "buy_zone_high": trade_plan.get("buy_zone_high", row.get("buy_zone_high")),
        "stop_loss_price": trade_plan.get("stop_loss_price", row.get("stop_loss_price")),
        "profit_target_low": trade_plan.get("profit_target_low", row.get("profit_target_low")),
        "profit_target_high": trade_plan.get("profit_target_high", row.get("profit_target_high")),
        "profile": profile_name,
    }


def _candidate_action(row: Mapping[str, Any]) -> str:
    brief = row.get("research_brief") if isinstance(row.get("research_brief"), Mapping) else {}
    action = str(brief.get("action") or "").strip()
    if action in ACTION_PRIORITY:
        return action
    return str(build_research_brief(row).get("action") or "research")


def _action_candidate(row: Mapping[str, Any]) -> Dict[str, Any]:
    brief = row.get("research_brief") if isinstance(row.get("research_brief"), Mapping) else {}
    trade_plan = brief.get("trade_plan") if isinstance(brief.get("trade_plan"), Mapping) else {}
    action = _candidate_action(row)
    return {
        "ticker": str(row.get("ticker") or "").upper(),
        "name": row.get("name") or "",
        "action": action,
        "reason": _action_reason(action),
        "canslim_score": _num(row.get("canslim_score"), None),
        "score_band": row.get("score_band") or "",
        "setup_status": row.get("setup_status") or "",
        "pivot_distance_pct": trade_plan.get("pivot_distance_pct", row.get("pivot_distance_pct")),
        "current_price": trade_plan.get("current_price", row.get("current_price")),
        "buy_zone_low": trade_plan.get("buy_zone_low", row.get("buy_zone_low")),
        "buy_zone_high": trade_plan.get("buy_zone_high", row.get("buy_zone_high")),
        "stop_loss_price": trade_plan.get("stop_loss_price", row.get("stop_loss_price")),
    }


def _comparison_candidate(row: Mapping[str, Any]) -> Dict[str, Any]:
    brief = row.get("research_brief") if isinstance(row.get("research_brief"), Mapping) else {}
    trade_plan = brief.get("trade_plan") if isinstance(brief.get("trade_plan"), Mapping) else {}
    setup = brief.get("setup") if isinstance(brief.get("setup"), Mapping) else {}
    reasons = brief.get("reasons") if isinstance(brief.get("reasons"), Mapping) else {}
    return {
        "ticker": str(row.get("ticker") or "").upper(),
        "name": row.get("name") or "",
        "sector": row.get("sector") or "",
        "industry": row.get("industry") or "",
        "action": _candidate_action(row),
        "canslim_score": _num(row.get("canslim_score"), None),
        "score_band": row.get("score_band") or "",
        "setup_status": row.get("setup_status") or setup.get("status") or "",
        "setup_type": row.get("setup_type") or setup.get("type") or "",
        "current_price": trade_plan.get("current_price", row.get("current_price")),
        "rs_rating": _num(row.get("rs_rating"), None),
        "quarterly_eps_growth": _num(row.get("quarterly_eps_growth"), None),
        "annual_eps_cagr": _num(row.get("annual_eps_cagr"), None),
        "revenue_growth": _num(row.get("revenue_growth"), None),
        "roe": _num(row.get("roe"), None),
        "market_cap": _num(row.get("market_cap"), None),
        "pivot_price": trade_plan.get("pivot_price", row.get("pivot_price")),
        "pivot_distance_pct": trade_plan.get("pivot_distance_pct", row.get("pivot_distance_pct")),
        "buy_zone_low": trade_plan.get("buy_zone_low", row.get("buy_zone_low")),
        "buy_zone_high": trade_plan.get("buy_zone_high", row.get("buy_zone_high")),
        "stop_loss_price": trade_plan.get("stop_loss_price", row.get("stop_loss_price")),
        "risk_reward_low": trade_plan.get("risk_reward_low"),
        "risk_reward_high": trade_plan.get("risk_reward_high"),
        "pass_count": len(_as_list(reasons.get("pass") or row.get("pass_reasons"))),
        "watch_count": len(_as_list(reasons.get("watch") or row.get("fail_reasons"))),
    }


def _action_reason(action: str) -> str:
    reasons = {
        "actionable": "Inside buy zone",
        "watch_breakout": "Near pivot",
        "building_base": "Base forming",
        "extended": "Extended",
        "research": "Research only",
    }
    return reasons.get(action, "Research only")


def _market_posture(exposure: float | None, status: str) -> str:
    normalized = status.lower()
    if exposure is None:
        return "unknown"
    if exposure >= 0.75 or "confirmed" in normalized:
        return "risk_on"
    if exposure <= 0.25 or "correction" in normalized:
        return "defensive"
    return "selective"


def _action_tasks(
    action_counts: Counter[str],
    next_action: str,
    status: Mapping[str, Any],
) -> list[Dict[str, Any]]:
    tasks: list[Dict[str, Any]] = []
    if next_action and next_action != "none":
        command = (status.get("recommended_commands") or [""])[0]
        tasks.append(
            {
                "type": "pipeline",
                "severity": "warning",
                "label": f"Run {next_action.replace('_', ' ')}",
                "detail": command,
            }
        )
    if action_counts.get("actionable", 0):
        tasks.append(
            {
                "type": "review",
                "severity": "ready",
                "label": f"{action_counts['actionable']} candidate(s) in buy zone",
                "detail": "Prioritize chart validation and entry/stop confirmation",
            }
        )
    if action_counts.get("watch_breakout", 0):
        tasks.append(
            {
                "type": "watch",
                "severity": "watch",
                "label": f"{action_counts['watch_breakout']} near pivot",
                "detail": "Watch volume and breakout confirmation",
            }
        )
    if action_counts.get("extended", 0):
        tasks.append(
            {
                "type": "avoid",
                "severity": "muted",
                "label": f"{action_counts['extended']} extended",
                "detail": "Wait for a new base or pullback",
            }
        )
    if not tasks:
        tasks.append(
            {
                "type": "idle",
                "severity": "muted",
                "label": "No immediate setup",
                "detail": "Keep the current profile on watch",
            }
        )
    return tasks[:4]


def _decision_brief_headline(
    *,
    candidate_count: int,
    actionable_count: int,
    watch_count: int,
    high_quality_count: int,
    exposure: float | None,
    health_level: str,
    quality_level: str,
    next_action: str,
) -> tuple[str, str, str]:
    if next_action and next_action != "none":
        return (
            "blocked",
            "Pipeline first",
            f"{next_action.replace('_', ' ')} is required before using this session output.",
        )
    if health_level in {"needs_pipeline", "empty_results"} or candidate_count <= 0:
        return ("blocked", "Build the candidate list", "Run the pipeline until the active profile has usable rows.")
    if health_level in {"stale_market", "stale_results", "missing_timestamp", "warning", "unknown"}:
        return ("warning", "Refresh stale inputs", "Review data freshness before ranking the shortlist.")
    if quality_level == "blocked":
        return ("warning", "Fix candidate gaps", "Critical score, price, setup, or trade-plan fields are incomplete.")
    if actionable_count and (exposure is None or exposure >= 0.5):
        return (
            "ready",
            "Validate entries",
            f"{actionable_count} buy-zone setup(s) need chart, volume, and risk confirmation.",
        )
    if watch_count:
        return (
            "watch",
            "Set breakout alerts",
            f"{watch_count} near-pivot setup(s) are closest to the next decision point.",
        )
    if high_quality_count:
        return ("watch", "Build the watchlist", f"{high_quality_count} high-quality candidate(s) remain under review.")
    return ("muted", "Research only", "No immediate setup outranks the current risk and freshness checks.")


def _decision_metrics(
    health: Mapping[str, Any],
    quality: Mapping[str, Any],
    *,
    exposure: float | None,
    candidate_count: int,
    actionable_count: int,
    watch_count: int,
    base_count: int,
    high_quality_count: int,
) -> list[Dict[str, Any]]:
    health_level = str(health.get("level") or "unknown")
    quality_level = str(quality.get("level") or "warning")
    setup_total = actionable_count + watch_count + base_count
    return [
        {
            "label": "Data",
            "value": _decision_health_label(health_level),
            "detail": f"{_count_value(health.get('ready_checks'))}/{_count_value(health.get('total_checks'))} checks",
            "level": _decision_data_level(health_level),
        },
        {
            "label": "Tape",
            "value": _decision_exposure_label(exposure),
            "detail": "recommended exposure",
            "level": "ready" if exposure is not None and exposure >= 0.5 else "warning" if exposure is not None else "muted",
        },
        {
            "label": "Setups",
            "value": str(setup_total),
            "detail": f"{actionable_count} buy zone · {watch_count} pivot · {base_count} base",
            "level": "ready" if actionable_count else "watch" if setup_total else "muted",
        },
        {
            "label": "Quality",
            "value": str(high_quality_count),
            "detail": str(quality.get("summary") or "candidate fields"),
            "level": _decision_quality_level(quality_level),
        },
        {
            "label": "Rows",
            "value": str(candidate_count),
            "detail": "active profile candidates",
            "level": "ready" if candidate_count else "blocked",
        },
    ]


def _decision_blockers(
    health: Mapping[str, Any],
    quality: Mapping[str, Any],
    candidates: list[Mapping[str, Any]],
) -> list[Dict[str, Any]]:
    blockers: list[Dict[str, Any]] = []
    for finding in _as_list(health.get("source_findings"))[:3]:
        if not isinstance(finding, Mapping):
            continue
        blockers.append(
            {
                "level": _decision_finding_level(str(finding.get("level") or "warning")),
                "label": finding.get("label") or "Data source",
                "detail": finding.get("detail") or "",
                "action": finding.get("next_action") or "",
            }
        )
    for row in _as_list(quality.get("issue_rows"))[:2]:
        if not isinstance(row, Mapping):
            continue
        missing = ", ".join(str(item) for item in _as_list(row.get("missing"))[:4])
        blockers.append(
            {
                "level": "warning",
                "label": f"{row.get('ticker') or 'Ticker'} gaps",
                "detail": missing,
                "action": "review",
            }
        )
    if not candidates and not blockers:
        blockers.append(
            {
                "level": "blocked",
                "label": "No candidates",
                "detail": "Active profile result file has no usable rows.",
                "action": "screen",
            }
        )
    return blockers[:5]


def _decision_next_steps(
    actions: Mapping[str, Any],
    health: Mapping[str, Any],
    quality: Mapping[str, Any],
    *,
    actionable_count: int,
    watch_count: int,
    base_count: int,
    candidate_count: int,
) -> list[Dict[str, Any]]:
    steps: list[Dict[str, Any]] = []
    next_action = str(health.get("next_action") or "")
    if next_action and next_action != "none":
        command = (_as_list(health.get("recommended_commands")) or [""])[0]
        steps.append(
            {
                "kind": "pipeline",
                "label": f"Run {next_action.replace('_', ' ')}",
                "detail": command,
                "action": _diagnostic_next_action(next_action),
                "priority": "high",
            }
        )
    if actionable_count:
        steps.append(
            {
                "kind": "review",
                "label": "Validate buy-zone setups",
                "detail": f"{actionable_count} candidate(s) require chart and risk checks.",
                "action": "queue",
                "priority": "high",
            }
        )
    if watch_count:
        steps.append(
            {
                "kind": "alerts",
                "label": "Prepare breakout alerts",
                "detail": f"{watch_count} candidate(s) sit near pivot.",
                "action": "review",
                "priority": "normal",
            }
        )
    if base_count:
        steps.append(
            {
                "kind": "watch",
                "label": "Monitor base builders",
                "detail": f"{base_count} candidate(s) are forming bases.",
                "action": "review",
                "priority": "normal",
            }
        )
    if str(quality.get("level") or "") == "blocked":
        steps.append(
            {
                "kind": "quality",
                "label": "Resolve candidate data gaps",
                "detail": str(quality.get("summary") or "Critical fields are incomplete."),
                "action": "quality",
                "priority": "high",
            }
        )
    if not candidate_count and not steps:
        steps.append(
            {
                "kind": "pipeline",
                "label": "Run screen",
                "detail": "Create a fresh ranked candidate file.",
                "action": "screen",
                "priority": "high",
            }
        )
    if not steps:
        for task in _as_list(actions.get("tasks"))[:3]:
            if not isinstance(task, Mapping):
                continue
            steps.append(
                {
                    "kind": task.get("type") or "task",
                    "label": task.get("label") or "Review session",
                    "detail": task.get("detail") or "",
                    "action": task.get("type") or "review",
                    "priority": "normal",
                }
            )
    return steps[:4]


def _decision_health_label(level: str) -> str:
    labels = {
        "ready": "Ready",
        "warning": "Warning",
        "stale_market": "Stale tape",
        "stale_results": "Stale results",
        "missing_timestamp": "No timestamp",
        "empty_results": "Empty",
        "needs_pipeline": "Pipeline",
        "unknown": "Unknown",
    }
    return labels.get(level, "Check")


def _decision_data_level(level: str) -> str:
    if level == "ready":
        return "ready"
    if level in {"needs_pipeline", "empty_results"}:
        return "blocked"
    if level in {"stale_market", "stale_results", "missing_timestamp", "warning"}:
        return "warning"
    return "muted"


def _decision_quality_level(level: str) -> str:
    if level == "ready":
        return "ready"
    if level == "blocked":
        return "blocked"
    return "warning"


def _decision_finding_level(level: str) -> str:
    if level == "missing":
        return "blocked"
    if level in {"stale", "unknown", "warning"}:
        return "warning"
    return "muted"


def _decision_exposure_label(exposure: float | None) -> str:
    if exposure is None:
        return "-"
    return f"{round(max(0.0, min(1.0, exposure)) * 100):.0f}%"


def _count_value(value: Any) -> int:
    number = _num(value, None)
    return int(number) if number is not None else 0


def build_research_brief(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Build a compact research and trade-plan summary for a candidate."""
    current_price = _num(row.get("current_price"), None)
    pivot_price = _num(row.get("pivot_price"), None)
    stop_loss = _num(row.get("stop_loss_price"), None)
    profit_low = _num(row.get("profit_target_low"), None)
    profit_high = _num(row.get("profit_target_high"), None)
    setup_status = str(row.get("setup_status") or "unclassified")
    components = row.get("component_scores") if isinstance(row.get("component_scores"), Mapping) else {}

    risk_amount = _positive_delta(current_price, stop_loss, inverse=True)
    reward_low = _positive_delta(current_price, profit_low)
    reward_high = _positive_delta(current_price, profit_high)
    risk_pct = (risk_amount / current_price) if current_price and risk_amount is not None else None
    reward_low_pct = (reward_low / current_price) if current_price and reward_low is not None else None
    reward_high_pct = (reward_high / current_price) if current_price and reward_high is not None else None

    if row.get("in_buy_zone"):
        action = "actionable"
    elif row.get("extended_from_pivot") or setup_status == "extended":
        action = "extended"
    elif setup_status == "near_pivot":
        action = "watch_breakout"
    elif setup_status == "forming_base":
        action = "building_base"
    else:
        action = "research"

    strongest = [
        key
        for key, value in sorted(
            ((_component_label(key), _num(value, None)) for key, value in components.items()),
            key=lambda item: item[1] if item[1] is not None else -1,
            reverse=True,
        )
        if value is not None and value >= 85
    ][:3]

    return {
        "action": action,
        "trade_plan": {
            "current_price": current_price,
            "pivot_price": pivot_price,
            "pivot_distance_pct": _num(row.get("pivot_distance_pct"), None),
            "buy_zone_low": _num(row.get("buy_zone_low"), None),
            "buy_zone_high": _num(row.get("buy_zone_high"), None),
            "in_buy_zone": bool(row.get("in_buy_zone")),
            "extended_from_pivot": bool(row.get("extended_from_pivot")),
            "stop_loss_price": stop_loss,
            "profit_target_low": profit_low,
            "profit_target_high": profit_high,
            "risk_pct": risk_pct,
            "reward_low_pct": reward_low_pct,
            "reward_high_pct": reward_high_pct,
            "risk_reward_low": (reward_low / risk_amount) if risk_amount and reward_low is not None else None,
            "risk_reward_high": (reward_high / risk_amount) if risk_amount and reward_high is not None else None,
        },
        "setup": {
            "status": setup_status,
            "type": row.get("setup_type"),
            "reasons": _as_list(row.get("setup_reasons")),
        },
        "score": {
            "total": _num(row.get("canslim_score"), None),
            "band": row.get("score_band"),
            "strongest_components": strongest,
        },
        "reasons": {
            "pass": _as_list(row.get("pass_reasons")),
            "watch": _as_list(row.get("fail_reasons")),
        },
    }


def _source_snapshot(
    source_id: str,
    label: str,
    path: Path,
    *,
    now: dt.datetime,
    required: bool,
    stale_after_hours: float | None,
) -> Dict[str, Any]:
    exists = path.exists()
    snapshot: Dict[str, Any] = {
        "id": source_id,
        "label": label,
        "path": _relative_path(path),
        "exists": exists,
        "required": required,
    }
    if not exists:
        return snapshot
    stat = path.stat()
    updated_at, age_hours = _mtime_summary(stat.st_mtime, now)
    snapshot.update(
        {
            "size": stat.st_size,
            "updated_at": updated_at,
            "age_hours": age_hours,
            "stale": age_hours is not None and stale_after_hours is not None and age_hours > stale_after_hours,
            "stale_after_hours": stale_after_hours,
            "sha256_12": _sha256_prefix(path) if path.is_file() else None,
        }
    )
    return snapshot


def _profile_threshold_rule(
    section: Mapping[str, Any],
    key: str,
    label: str,
    comparator: str,
    value_type: str,
    group: str,
) -> Dict[str, Any] | None:
    number = _num(section.get(key), None)
    if number is None:
        return None
    return {
        "group": group,
        "label": label,
        "value": f"{comparator} {_format_profile_threshold(number, value_type)}",
        "source": f"{key}",
    }


def _profile_requirement(config: Mapping[str, Any], section_name: str, key: str, label: str) -> Dict[str, Any]:
    section = config.get(section_name) if isinstance(config.get(section_name), Mapping) else {}
    required = bool(section.get(key))
    return {
        "label": label,
        "value": "Required" if required else "Optional",
        "required": required,
        "source": f"{section_name}.{key}",
    }


def _format_profile_threshold(value: float, value_type: str) -> str:
    if value_type == "percent":
        return f"{value * 100:g}%"
    if value_type == "money":
        return _compact_money(value)
    return f"{value:g}"


def _compact_money(value: float) -> str:
    abs_value = abs(value)
    for threshold, suffix in [(1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")]:
        if abs_value >= threshold:
            return f"${value / threshold:g}{suffix}"
    return f"${value:g}"


def _result_path(config: Mapping[str, Any]) -> Path:
    output_file = config.get("data_paths", {}).get("output_file", "data/processed/results.csv")
    return _resolve_project_path(output_file)


def _artifact_definition(artifact_id: str) -> Mapping[str, str]:
    normalized = str(artifact_id or "").strip()
    for definition in ARTIFACT_DEFINITIONS:
        if definition["id"] == normalized:
            return definition
    allowed = ", ".join(definition["id"] for definition in ARTIFACT_DEFINITIONS)
    raise ValueError(f"artifact id must be one of: {allowed}")


def _artifact_path(output_path: Path, artifact_id: str) -> Path:
    output_path = output_path.resolve()
    if artifact_id == "results_csv":
        return output_path
    if artifact_id == "results_md":
        return output_path.with_suffix(".md")
    if artifact_id == "tradingview_watchlist":
        return output_path.with_name(f"{output_path.stem}_tradingview_watchlist.txt")
    if artifact_id == "tradingview_review_plan":
        return output_path.with_name(f"{output_path.stem}_tradingview_review_plan.json")
    raise ValueError(f"Unknown artifact: {artifact_id}")


def _artifact_snapshot(
    definition: Mapping[str, str],
    path: Path,
    *,
    now: dt.datetime,
    profile: str,
) -> Dict[str, Any]:
    _ensure_project_artifact_path(path)
    exists = path.exists() and path.is_file()
    artifact_id = definition["id"]
    snapshot: Dict[str, Any] = {
        "id": artifact_id,
        "label": definition["label"],
        "description": definition["description"],
        "path": _relative_path(path),
        "filename": path.name,
        "exists": exists,
        "content_type": definition["content_type"],
        "download_url": (
            "/api/artifacts/download?"
            f"profile={urllib.parse.quote(profile)}&id={urllib.parse.quote(artifact_id)}"
        ),
    }
    if not exists:
        return snapshot
    stat = path.stat()
    updated_at, age_hours = _mtime_summary(stat.st_mtime, now)
    snapshot.update(
        {
            "size": stat.st_size,
            "updated_at": updated_at,
            "age_hours": age_hours,
            "sha256_12": _sha256_prefix(path),
        }
    )
    if artifact_id == "results_csv":
        snapshot["rows"] = _count_candidate_rows(path)
    return snapshot


def _ensure_project_artifact_path(path: Path) -> None:
    try:
        path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("artifact path must be inside the project workspace") from exc


def _diagnostic_level(level: str) -> str:
    normalized = str(level or "").strip().lower()
    return normalized if normalized in {"ready", "warning", "blocked"} else "warning"


def _diagnostic_rollup_level(checks: Iterable[Mapping[str, Any]]) -> str:
    levels = {_diagnostic_level(str(check.get("level") or "")) for check in checks}
    if "blocked" in levels:
        return "blocked"
    if "warning" in levels:
        return "warning"
    return "ready"


def _release_readiness(
    checks: Iterable[Mapping[str, Any]],
    security: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize the gates an operator should verify before relying on the web app."""
    checks_by_id = {str(check.get("id") or ""): check for check in checks}
    items = [_release_readiness_item(checks_by_id[check_id]) for check_id in RELEASE_READINESS_CHECK_IDS if check_id in checks_by_id]
    access_control = _security_control(security, "access_control")
    if access_control:
        access_level = _diagnostic_level(str(access_control.get("level") or ""))
        items.insert(
            3,
            {
                "id": "access_control",
                "label": str(access_control.get("label") or "Dashboard access control"),
                "level": access_level,
                "detail": str(access_control.get("detail") or ""),
                "next_action": "configure-auth" if access_level in {"warning", "blocked"} else "",
                "path": "",
            },
        )

    counts = {
        "ready": sum(1 for item in items if item["level"] == "ready"),
        "warning": sum(1 for item in items if item["level"] == "warning"),
        "blocked": sum(1 for item in items if item["level"] == "blocked"),
    }
    level = _diagnostic_rollup_level(items)
    needs_attention = counts["blocked"] + counts["warning"]
    return {
        "level": level,
        "summary": f"{counts['ready']}/{len(items)} release gates ready",
        "recommendation": _release_readiness_recommendation(level, needs_attention, items),
        "counts": counts,
        "next_actions": _release_readiness_next_actions(items),
        "items": items,
    }


def _release_readiness_item(check: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(check.get("id") or ""),
        "label": str(check.get("label") or "Readiness gate"),
        "level": _diagnostic_level(str(check.get("level") or "")),
        "detail": str(check.get("detail") or ""),
        "next_action": str(check.get("next_action") or ""),
        "path": str(check.get("path") or ""),
    }


def _security_control(security: Mapping[str, Any] | None, control_id: str) -> Mapping[str, Any] | None:
    controls = security.get("controls") if isinstance(security, Mapping) else []
    if not isinstance(controls, list):
        return None
    for control in controls:
        if isinstance(control, Mapping) and control.get("id") == control_id:
            return control
    return None


def _release_readiness_next_actions(items: Iterable[Mapping[str, Any]]) -> list[str]:
    actions: list[str] = []
    for item in items:
        action = str(item.get("next_action") or "").strip()
        if action and action not in actions:
            actions.append(action)
    return actions


def _release_readiness_recommendation(level: str, needs_attention: int, items: Iterable[Mapping[str, Any]]) -> str:
    if level == "ready":
        return "Ready for a single-user trading research session."
    first_attention = next((item for item in items if item.get("level") == "blocked"), None)
    if first_attention is None:
        first_attention = next((item for item in items if item.get("level") == "warning"), None)
    label = str((first_attention or {}).get("label") or "release gate")
    if level == "blocked":
        return f"{needs_attention} gate(s) need attention before operator use; start with {label}."
    return f"{needs_attention} gate(s) need attention before release; start with {label}."


def _deployment_guide(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return operator-safe launch guidance without embedding secrets."""
    context = access_context or {}
    auth_env = str(context.get("auth_env") or security_posture.DEFAULT_AUTH_ENV)
    allow_remote = bool(context.get("allow_remote"))
    auth_enabled = bool(context.get("auth_enabled"))
    require_auth = bool(context.get("require_auth"))
    return {
        "auth_env": auth_env,
        "current_access": {
            "allow_remote": allow_remote,
            "auth_enabled": auth_enabled,
            "require_auth": require_auth,
        },
        "probe": {
            "path": "/api/readiness",
            "method": "GET",
            "success": "HTTP 200 with ok=true; HTTP 503 when a release gate is blocked",
            "detail": "uses the same release gates shown in Data Operations and support bundles",
        },
        "commands": [
            {
                "id": "local",
                "label": "Local workstation",
                "command": "./screener web --open",
                "detail": "loopback-only browser session",
            },
            {
                "id": "remote",
                "label": "Remote private network",
                "command": f"{auth_env}='USER:PASSWORD' ./screener web --host 0.0.0.0 --allow-remote --require-auth",
                "detail": "requires network controls plus Basic Auth",
            },
            {
                "id": "container",
                "label": "Container",
                "command": f"docker run --rm -p 8765:8765 -e {auth_env}='USER:PASSWORD' -v \"$PWD/data:/app/data\" canslim-sepa",
                "detail": "persists processed data and workspace backups through the data mount",
            },
        ],
        "notes": [
            "Use an environment variable for credentials so secrets are not stored in shell history.",
            "Keep the dashboard off the public internet; place remote runs behind private network controls.",
            "Use --require-auth for remote/container launches so startup fails closed when credentials are missing.",
        ],
    }


def _diagnostic_directory_readiness(path: Path) -> tuple[str, str]:
    if path.exists():
        if not path.is_dir():
            return "blocked", "path exists but is not a directory"
        if os.access(path, os.W_OK):
            return "ready", "directory writable"
        return "blocked", "directory is not writable"
    parent = _nearest_existing_parent(path)
    if parent and os.access(parent, os.W_OK):
        return "warning", "directory missing; parent is writable"
    return "blocked", "directory missing and parent is not writable"


def _diagnostic_browser_security_policy_level() -> str:
    headers = security_headers.security_header_map()
    required_headers = {
        "Content-Security-Policy",
        "Permissions-Policy",
        "Cross-Origin-Opener-Policy",
        "Cross-Origin-Resource-Policy",
        "Referrer-Policy",
        "X-Frame-Options",
        "X-Content-Type-Options",
    }
    return "ready" if required_headers <= set(headers) and all(headers.get(key) for key in required_headers) else "blocked"


def _diagnostic_browser_security_policy_detail() -> str:
    headers = security_headers.security_header_map()
    policies = []
    if "frame-ancestors 'none'" in headers.get("Content-Security-Policy", ""):
        policies.append("CSP")
    if "camera=()" in headers.get("Permissions-Policy", ""):
        policies.append("Permissions")
    if headers.get("Cross-Origin-Opener-Policy") == "same-origin":
        policies.append("COOP")
    if headers.get("Cross-Origin-Resource-Policy") == "same-origin":
        policies.append("CORP")
    return f"{len(policies)}/4 browser isolation policies configured"


def _diagnostic_workspace_disk_space(workspace_dir: Path) -> tuple[str, str, Path]:
    target = workspace_dir if workspace_dir.exists() else _nearest_existing_parent(workspace_dir)
    if target is None:
        return "warning", "free space unavailable; workspace path is missing", workspace_dir
    try:
        usage = shutil.disk_usage(target)
    except OSError as exc:
        return "warning", f"free space unavailable: {exc}", target
    free_bytes = int(usage.free)
    formatted = _format_bytes(free_bytes)
    if free_bytes < WORKSPACE_DISK_BLOCKED_BYTES:
        return "blocked", f"{formatted} free; workspace writes may fail", target
    if free_bytes < WORKSPACE_DISK_WARNING_BYTES:
        return "warning", f"{formatted} free; backups may fail", target
    return "ready", f"{formatted} free", target


def _diagnostic_workspace_store_integrity(workspace_dir: Path) -> tuple[str, str, Path]:
    stores = [
        ("preferences", workspace_dir / "preferences.json"),
        ("review queue", workspace_dir / "review_queue.json"),
        ("session journal", workspace_dir / "session_journal.json"),
        ("workspace audit", workspace_dir / "workspace_audit.json"),
    ]
    missing = 0
    for label, path in stores:
        if not path.exists():
            missing += 1
            continue
        if not path.is_file():
            return "blocked", f"{label} store path is not a file", path
        if path.stat().st_size == 0:
            continue
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return "blocked", f"{label} store is not valid JSON", path
        if not isinstance(payload, dict):
            return "blocked", f"{label} store root must be a JSON object", path
        if label in {"review queue", "session journal"}:
            profiles = payload.get("profiles")
            if profiles is not None and not isinstance(profiles, dict):
                return "blocked", f"{label} profiles must be a JSON object", path
        if label == "workspace audit":
            events = payload.get("events")
            if events is not None and not isinstance(events, list):
                return "blocked", f"{label} events must be a JSON array", path
    present = len(stores) - missing
    if not workspace_dir.exists():
        return "warning", "workspace stores not created yet", workspace_dir
    return "ready", f"{present}/{len(stores)} store file(s) present and readable", workspace_dir


def _diagnostic_atomic_temp_files(workspace_dir: Path) -> tuple[str, str, Path]:
    temp_files = _workspace_atomic_temp_files(workspace_dir)
    if not temp_files:
        return "ready", "no interrupted write temp files", workspace_dir
    return "warning", f"{len(temp_files)} interrupted write temp file(s) present", temp_files[0]


def _workspace_atomic_temp_files(workspace_dir: Path) -> list[Path]:
    if not workspace_dir.exists() or not workspace_dir.is_dir():
        return []
    return sorted(path for path in workspace_dir.rglob(".*.tmp") if path.is_file())


def _nearest_existing_parent(path: Path) -> Path | None:
    current = path.resolve()
    for candidate in [current, *current.parents]:
        if candidate.exists():
            return candidate
    return None


def _format_bytes(value: int | float) -> str:
    size = float(value)
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if abs(size) < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024


def _diagnostic_next_action(action: str) -> str:
    normalized = str(action or "").strip().replace("_", "-")
    aliases = {
        "none": "",
        "institutional-data": "enrich",
        "update": "enrich",
    }
    if normalized in aliases:
        return aliases[normalized]
    return normalized if normalized in {"download", "parse", "enrich", "screen", "tv-export", "profile-sweep"} else ""


def _candidate_field_present(row: Mapping[str, Any], key: str, kind: Any) -> bool:
    value = row.get(key)
    if kind == "number":
        return _num(value, None) is not None
    if isinstance(value, str):
        return bool(value.strip())
    return value not in (None, "")


def _candidate_coverage_level(coverage_pct: float, *, critical: bool) -> str:
    if coverage_pct >= 90:
        return "ready"
    if critical and coverage_pct < 70:
        return "blocked"
    return "warning"


def _candidate_requires_trade_plan(row: Mapping[str, Any]) -> bool:
    brief = row.get("research_brief") if isinstance(row.get("research_brief"), Mapping) else {}
    action = str(brief.get("action") or _candidate_action(row))
    setup = str(row.get("setup_status") or "")
    return bool(
        row.get("in_buy_zone")
        or action == "actionable"
        or setup in {"breakout_confirmed", "breakout_unconfirmed"}
        or _candidate_field_present(row, "buy_zone_low", "number")
        or _candidate_field_present(row, "stop_loss_price", "number")
    )


def _candidate_export_row(row: Mapping[str, Any]) -> dict[str, Any]:
    exported: dict[str, Any] = {}
    for field in CANDIDATE_EXPORT_FIELDS:
        if field == "action":
            brief = row.get("research_brief") if isinstance(row.get("research_brief"), Mapping) else {}
            value = brief.get("action") or _candidate_action(row)
        else:
            value = row.get(field)
        exported[field] = _candidate_csv_value(value)
    return exported


def _candidate_csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict, tuple)):
        return _escape_csv_formula(json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True))
    if isinstance(value, str):
        return _escape_csv_formula(value)
    return value


def _escape_csv_formula(value: str) -> str:
    text = str(value)
    if text and text[0] in {"=", "+", "-", "@", "\t", "\r"}:
        return f"'{text}"
    return text


def _comparison_tickers(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        source = [token for token in re.split(r"[\s,;|]+", value) if token.strip()]
    elif isinstance(value, list):
        source = value
    else:
        source = [value]
    tickers: list[str] = []
    seen: set[str] = set()
    for raw in source:
        ticker = str(raw or "").strip().upper().replace(".", "-")
        if not _IMPORT_TICKER_RE.match(ticker) or ticker in seen:
            continue
        tickers.append(ticker)
        seen.add(ticker)
        if len(tickers) >= CANDIDATE_COMPARE_LIMIT:
            break
    return tickers


def _candidate_export_suffix(*, query: str = "", min_score: float | None = None, setup: str = "") -> str:
    parts: list[str] = []
    if setup:
        parts.append(_filename_token(setup))
    if min_score is not None:
        parts.append(f"score{int(min_score) if float(min_score).is_integer() else str(min_score).replace('.', '_')}")
    if str(query or "").strip():
        parts.append("search")
    return f"-{'-'.join(part for part in parts if part)}" if parts else ""


def _filename_token(value: Any) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "").strip()).strip("-")
    return token[:40] or "view"


def _ticker_tokens(ticker_input: str | list[Any]) -> list[str]:
    if isinstance(ticker_input, str):
        return [token for token in re.split(r"[\s,;|]+", ticker_input) if token.strip()]
    if isinstance(ticker_input, list):
        return [str(token) for token in ticker_input if str(token).strip()]
    raise ValueError("tickers must be text or a JSON array")


def _normalize_import_ticker(token: Any) -> str:
    normalized = str(token or "").strip().upper()
    if ":" in normalized:
        normalized = normalized.rsplit(":", 1)[1]
    return normalized.lstrip("$").replace(".", "-").strip()


def _resolve_project_path(path_value: Any) -> Path:
    path = Path(str(path_value))
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


def _sha256_prefix(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_PROVENANCE_HASH_BYTES:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()[:12]
    except OSError:
        return None


def _load_market_direction(config: Mapping[str, Any]) -> Dict[str, Any]:
    processed_dir = PROJECT_ROOT / str(config.get("data_paths", {}).get("processed_data_dir", "data/processed"))
    path = processed_dir / "market_direction.json"
    if not path.exists():
        return {}
    try:
        with path.open("r") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return {}


def _latest_quote(symbol: str) -> Dict[str, Any] | None:
    try:
        chart = _cached_yahoo_chart(symbol, "5d", "1d", _cache_bucket(180))
    except Exception:
        return None
    closes = [close for close in chart.get("closes", []) if close is not None]
    timestamps = chart.get("timestamps") or []
    if not closes:
        return None
    latest = closes[-1]
    previous = closes[-2] if len(closes) >= 2 else chart.get("previous_close")
    as_of = None
    if timestamps:
        as_of = dt.datetime.fromtimestamp(timestamps[-1], dt.timezone.utc).date().isoformat()
    return {"latest": latest, "previous": previous, "as_of": as_of}


@lru_cache(maxsize=256)
def _cached_yahoo_chart(symbol: str, period: str, interval: str, bucket: int) -> Dict[str, Any]:
    del bucket
    encoded = urllib.parse.quote(symbol, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
        f"?range={urllib.parse.quote(period)}&interval={urllib.parse.quote(interval)}"
    )
    payload = json.loads(_read_url(url, timeout=5).decode("utf-8"))
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise ValueError(f"No Yahoo chart data for {symbol}")
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    meta = result.get("meta") or {}
    return {
        "timestamps": result.get("timestamp") or [],
        "closes": closes,
        "previous_close": meta.get("chartPreviousClose") or meta.get("regularMarketPreviousClose"),
    }


@lru_cache(maxsize=8)
def _cached_market_news(bucket: int) -> list[Dict[str, Any]]:
    del bucket
    url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC,%5EIXIC,%5EDJI&region=US&lang=en-US"
    xml = _read_url(url, timeout=5).decode("utf-8", errors="replace")
    root = ET.fromstring(xml)
    items: list[Dict[str, Any]] = []
    for item in root.findall(".//item"):
        published_raw = item.findtext("pubDate")
        published = None
        if published_raw:
            try:
                published = email.utils.parsedate_to_datetime(published_raw).isoformat()
            except (TypeError, ValueError):
                published = published_raw
        items.append(
            {
                "title": item.findtext("title"),
                "source": "Yahoo Finance",
                "published": published,
                "url": _safe_external_url(item.findtext("link")),
                "summary": item.findtext("description"),
            }
        )
    return items


def _safe_external_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return text
    return None


def _read_url(url: str, *, timeout: int = 5) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (CANSLIM-SEPA local dashboard)",
            "Accept": "application/json, application/rss+xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _cache_bucket(seconds: int) -> int:
    return int(time.time() // seconds)


def _num(value: Any, default: float | None = 0.0) -> float | None:
    try:
        if value is None:
            return default
        number = float(value)
        if not math.isfinite(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def _finite_float(value: Any) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None


def _positive_delta(base: float | None, target: float | None, *, inverse: bool = False) -> float | None:
    if base is None or target is None:
        return None
    delta = (base - target) if inverse else (target - base)
    return delta if delta > 0 else None


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def _component_label(key: Any) -> str:
    labels = {
        "c": "Current earnings",
        "a": "Annual growth",
        "n": "New highs/setup",
        "s": "Supply demand",
        "l": "Leadership",
        "i": "Institutional",
        "m": "Market",
    }
    return labels.get(str(key).lower(), str(key))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _mtime_summary(mtime: Any, now: dt.datetime) -> tuple[str | None, float | None]:
    timestamp = _num(mtime, None)
    if timestamp is None:
        return None, None
    updated_at = dt.datetime.fromtimestamp(timestamp, dt.timezone.utc)
    age_hours = max((now - updated_at).total_seconds() / 3600, 0)
    return updated_at.isoformat(), round(age_hours, 2)


def _date_age_days(value: Any, now: dt.datetime) -> int | None:
    if not value:
        return None
    try:
        as_of = dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
    return max((now.date() - as_of).days, 0)


def _market_direction_stale(market_age_days: int | None, market_session_lag: int | None) -> bool:
    if market_session_lag is not None:
        return market_session_lag > 0
    return market_age_days is not None and market_age_days > 3


def _session_count_label(value: int) -> str:
    return f"{value} completed market session" if value == 1 else f"{value} completed market sessions"


def _market_session_lag(value: Any, now: dt.datetime) -> int | None:
    as_of = _parse_iso_date(value)
    expected = _previous_completed_us_market_session(now)
    if as_of is None or expected is None:
        return None
    if as_of >= expected:
        return 0
    lag = 0
    cursor = as_of + dt.timedelta(days=1)
    while cursor <= expected:
        if _is_us_market_session(cursor):
            lag += 1
        cursor += dt.timedelta(days=1)
    return lag


def _previous_completed_us_market_session(now: dt.datetime) -> dt.date | None:
    market_now = _to_us_market_time(now)
    candidate = market_now.date()
    if _is_us_market_session(candidate) and market_now.time() >= US_MARKET_CLOSE:
        return candidate
    candidate -= dt.timedelta(days=1)
    for _ in range(14):
        if _is_us_market_session(candidate):
            return candidate
        candidate -= dt.timedelta(days=1)
    return None


def _to_us_market_time(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    try:
        return value.astimezone(ZoneInfo(US_MARKET_TIMEZONE))
    except ZoneInfoNotFoundError:
        return value.astimezone(dt.timezone.utc)


def _parse_iso_date(value: Any) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _is_us_market_session(value: dt.date) -> bool:
    if value.weekday() >= 5:
        return False
    return value not in _us_market_holidays(value.year)


@lru_cache(maxsize=16)
def _us_market_holidays(year: int) -> frozenset[dt.date]:
    holidays: set[dt.date] = set()
    for current_year in range(year - 1, year + 2):
        holidays.update(
            {
                _observed_fixed_holiday(current_year, 1, 1),
                _nth_weekday(current_year, 1, 0, 3),
                _nth_weekday(current_year, 2, 0, 3),
                _easter_date(current_year) - dt.timedelta(days=2),
                _last_weekday(current_year, 5, 0),
                _observed_fixed_holiday(current_year, 6, 19),
                _observed_fixed_holiday(current_year, 7, 4),
                _nth_weekday(current_year, 9, 0, 1),
                _nth_weekday(current_year, 11, 3, 4),
                _observed_fixed_holiday(current_year, 12, 25),
            }
        )
    return frozenset(holidays)


def _observed_fixed_holiday(year: int, month: int, day: int) -> dt.date:
    holiday = dt.date(year, month, day)
    if holiday.weekday() == 5:
        return holiday - dt.timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + dt.timedelta(days=1)
    return holiday


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> dt.date:
    current = dt.date(year, month, 1)
    days_until = (weekday - current.weekday()) % 7
    return current + dt.timedelta(days=days_until + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    if month == 12:
        current = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        current = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    while current.weekday() != weekday:
        current -= dt.timedelta(days=1)
    return current


def _easter_date(year: int) -> dt.date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l_value = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_value) // 451
    month = (h + l_value - 7 * m + 114) // 31
    day = ((h + l_value - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)
