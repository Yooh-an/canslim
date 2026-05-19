"""Single ticker CAN SLIM analysis helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping

import pandas as pd

from src.collectors.institutional_collector import enrich_companies_with_13f_data
from src.enrichers.fundamental_fallback import enrich_company_fundamentals
from src.enrichers.market_data_enricher import MarketDataEnricher
from src.screeners.candidate_filter import _evaluate_screening_candidate
from src.screeners.canslim_scoring import calculate_canslim_score
from src.screeners.trade_rules import add_trade_rules


def _load_companies(config: Mapping[str, Any]) -> list[Dict[str, Any]]:
    data_paths = config.get("data_paths", {})
    processed_dir = Path(data_paths.get("processed_data_dir", "data/processed"))
    enriched_file = processed_dir / "companies_list_enriched.json"
    companies_file = processed_dir / "companies_list.json"
    raw_companies_file = Path(data_paths.get("raw_data_dir", "data/raw")) / "submissions_extracted" / "companies.json"

    companies_by_ticker: dict[str, Dict[str, Any]] = {}
    for source in (enriched_file, companies_file):
        if not source.exists():
            continue
        with source.open("r") as f:
            payload = json.load(f)
        if not isinstance(payload, list):
            continue
        for row in payload:
            ticker = str(row.get("ticker") or "").upper().replace(".", "-")
            if ticker:
                companies_by_ticker.setdefault(ticker, row)

    if raw_companies_file.exists():
        with raw_companies_file.open("r") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            for cik, row in payload.items():
                tickers = row.get("tickers") or []
                if not tickers:
                    continue
                exchanges = row.get("exchanges") or []
                company = {
                    "cik": str(cik).lstrip("0") or "0",
                    "cik_padded": str(cik).zfill(10),
                    "ticker": tickers[0],
                    "exchange": exchanges[0] if exchanges else "",
                    "name": row.get("name", ""),
                    "market_cap": row.get("marketCap", 0) or 0,
                    "sic": row.get("sic", ""),
                    "category": row.get("category", ""),
                }
                ticker = str(company["ticker"]).upper().replace(".", "-")
                companies_by_ticker.setdefault(ticker, company)

    return list(companies_by_ticker.values())


def _needs_market_enrichment(company: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> bool:
    fields = [
        "current_price",
        "rs_rating",
        "price_vs_52w_high",
        "avg_dollar_volume_50d",
        "up_down_volume_ratio_50d",
        "volume_trend_50_200",
    ]
    if not company.get("market_cap"):
        return True
    if any(field not in company or not pd.notna(company.get(field)) for field in fields):
        return True

    institutional_criteria = (config or {}).get("institutional_criteria", {})
    market_data = (config or {}).get("market_data", {})
    wants_institutional = institutional_criteria.get("require_institutional_sponsorship", False) or market_data.get("use_yfinance_info_fallback", False)
    if wants_institutional and not company.get("institutional_data_source"):
        ownership_missing = "institutional_ownership" not in company or not pd.notna(company.get("institutional_ownership"))
        holders_missing = "institutional_holders" not in company or not pd.notna(company.get("institutional_holders"))
        if ownership_missing and holders_missing:
            return True

    return False


def _needs_13f_enrichment(company: Mapping[str, Any], config: Mapping[str, Any]) -> bool:
    if not config.get("institutional_data", {}).get("enabled", False):
        return False
    fields = ["institutional_holders", "institutional_accumulation_score"]
    return any(field not in company or not pd.notna(company.get(field)) for field in fields)


def _enrich_single_ticker_institutional(company: Dict[str, Any], config: Mapping[str, Any]) -> Dict[str, Any]:
    if not _needs_13f_enrichment(company, config):
        return company
    try:
        enriched = enrich_companies_with_13f_data([company], config, sec_client=None)
    except Exception:
        return company
    if enriched:
        return dict(enriched[0])
    return company


def _market_direction_ok(config: Mapping[str, Any]) -> tuple[bool, Dict[str, Any]]:
    market_criteria = config.get("market_direction", {})
    if not market_criteria.get("required", False):
        return True, {}
    processed_dir = Path(config.get("data_paths", {}).get("processed_data_dir", "data/processed"))
    market_file = processed_dir / "market_direction.json"
    if not market_file.exists():
        return False, {}
    try:
        with market_file.open("r") as f:
            market_direction = json.load(f)
    except Exception:
        return False, {}
    allowed = market_criteria.get("allowed_statuses", ["confirmed_uptrend"])
    return market_direction.get("market_direction_status") in allowed, market_direction


def analyze_ticker(ticker: str, config: Mapping[str, Any]) -> Dict[str, Any]:
    """Analyze one ticker with the active CAN SLIM profile and return score/pass diagnostics."""
    normalized = str(ticker or "").upper().replace(".", "-")
    companies = _load_companies(config)
    company = next(
        (row for row in companies if str(row.get("ticker") or "").upper().replace(".", "-") == normalized),
        None,
    )
    if company is None:
        return {"found": False, "ticker": normalized}
    company = enrich_company_fundamentals(dict(company), dict(config))
    if _needs_market_enrichment(company, config) and config.get("market_data", {}).get("on_demand_ticker_enrichment", True):
        market_config = dict(config)
        market_config["_quiet"] = True
        company = MarketDataEnricher(market_config).enrich_single_ticker_market_data(company)
    company = _enrich_single_ticker_institutional(company, config)

    criteria = config.get("screening_criteria", {})
    leadership_criteria = config.get("leadership_criteria", {})
    supply_demand_criteria = config.get("supply_demand_criteria", {})
    institutional_criteria = config.get("institutional_criteria", {})
    pattern_criteria = config.get("pattern_criteria", {})
    market_ok, market_direction = _market_direction_ok(config)
    test_mode = config.get("download_settings", {}).get("test_mode", False)

    passed, criterion_results = _evaluate_screening_candidate(
        dict(company),
        criteria,
        leadership_criteria,
        supply_demand_criteria,
        institutional_criteria,
        pattern_criteria,
        market_ok,
        test_mode,
    )
    scored = calculate_canslim_score(
        company,
        criteria,
        leadership_criteria,
        supply_demand_criteria,
        institutional_criteria,
        pattern_criteria,
        market_ok,
    )
    enriched = add_trade_rules(scored)
    enriched.update(
        {
            "found": True,
            "ticker": normalized,
            "passed": bool(passed),
            "criterion_results": criterion_results,
            "market_direction": market_direction,
        }
    )
    return enriched


def _pct(value: Any) -> str:
    try:
        value = float(value)
        if not pd.notna(value):
            return "N/A"
        return f"{value * 100:.1f}%"
    except Exception:
        return "N/A"


def _money(value: Any) -> str:
    try:
        value = float(value)
        if not pd.notna(value):
            return "N/A"
    except Exception:
        return "N/A"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.0f}"


def _fmt_num(value: Any, digits: int = 2) -> str:
    try:
        value = float(value)
        if not pd.notna(value):
            return "N/A"
    except Exception:
        return "N/A"
    text = f"{value:.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _fmt_price(value: Any) -> str:
    return _fmt_num(value, 2)


def _fmt_rating(value: Any) -> str:
    return _fmt_num(value, 1)


def _fmt_ratio(value: Any) -> str:
    formatted = _fmt_num(value, 2)
    return "N/A" if formatted == "N/A" else f"{formatted}x"


def _score_color(score: Any, max_val: int = 20) -> str:
    """Return a rich color tag for a component score."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "dim"
    ratio = s / max_val if max_val else 0
    if ratio >= 0.8:
        return "bold bright_green"
    if ratio >= 0.6:
        return "green"
    if ratio >= 0.4:
        return "yellow"
    if ratio >= 0.2:
        return "bright_red"
    return "red"


def _band_style(band: str) -> str:
    """Return a color for the CAN SLIM score band."""
    band_upper = str(band).upper()
    if band_upper in ("A+", "A"):
        return "bold bright_green"
    if band_upper in ("B+", "B"):
        return "green"
    if band_upper in ("C+", "C"):
        return "yellow"
    return "red"


def format_ticker_analysis(result: Mapping[str, Any], *, rich_mode: bool = False) -> str:
    """Format a single ticker analysis as readable text.

    When *rich_mode* is True the output contains Rich markup tags for
    coloured terminal display.
    """
    if not result.get("found"):
        msg = f"Ticker {result.get('ticker')} was not found in the enriched company list. Run parse/enrich first."
        if rich_mode:
            return f"[bold red]✗[/bold red] {msg}"
        return msg

    if not rich_mode:
        return _format_plain(result)
    return _format_rich(result)


def _format_plain(result: Mapping[str, Any]) -> str:
    """Original plain-text formatter (backward compatible)."""
    components = result.get("component_scores", {})
    component_text = "/".join(str(components.get(key, "N/A")) for key in ["c", "a", "n", "s", "l", "i", "m"])
    lines = [
        f"Ticker: {result.get('ticker')}",
        f"Name: {result.get('name', 'Unknown')}",
        f"Verdict: {'PASS' if result.get('passed') else 'FAIL/WATCH'}",
        f"CAN SLIM Score: {result.get('canslim_score', 'N/A')} ({result.get('score_band', 'N/A')})",
        f"C/A/N/S/L/I/M: {component_text}",
        "",
        "Key metrics:",
        f"- Quarterly EPS growth: {_pct(result.get('quarterly_eps_growth'))}",
        f"- Annual EPS CAGR: {_pct(result.get('annual_eps_cagr'))}",
        f"- Revenue growth: {_pct(result.get('revenue_growth'))}",
        f"- ROE: {_pct(result.get('roe'))}",
        f"- RS rating: {_fmt_rating(result.get('rs_rating'))}",
        f"- Price vs 52w high: {_pct(result.get('price_vs_52w_high'))}",
        f"- Market cap: {_money(result.get('market_cap'))}",
        "",
        "Setup:",
        f"- Status: {result.get('setup_status', 'N/A')}",
        f"- Type: {result.get('setup_type', 'N/A')}",
        f"- Pivot: {_fmt_price(result.get('pivot_price'))}",
        f"- Current price: {_fmt_price(result.get('current_price'))}",
        f"- Pivot distance: {_fmt_num(result.get('pivot_distance_pct'), 2)}%",
        f"- Breakout volume: {_fmt_ratio(result.get('breakout_volume_ratio'))}",
        "",
        "Trade plan:",
        f"- Buy zone: {result.get('buy_zone_low', 'N/A')} ~ {result.get('buy_zone_high', 'N/A')}",
        f"- Stop loss: {result.get('stop_loss_price', 'N/A')}",
        f"- Profit target: {result.get('profit_target_low', 'N/A')} ~ {result.get('profit_target_high', 'N/A')}",
        "",
        "Institutional / insider:",
        f"- Institutional ownership: {_pct(result.get('institutional_ownership'))}",
        f"- Institutional holders: {_fmt_num(result.get('institutional_holders'), 0)}",
        f"- Institutional data source: {result.get('institutional_data_source', 'N/A')}",
        f"- 13F accumulation score: {_fmt_num(result.get('institutional_accumulation_score'), 1)}",
        f"- Insider signal: {result.get('insider_signal', 'N/A')}",
    ]
    if result.get("setup_reasons"):
        lines.extend(["", "Setup reasons:", *[f"- {reason}" for reason in result["setup_reasons"]]])
    if result.get("pass_reasons"):
        lines.extend(["", "Pass reasons:", *[f"- {reason}" for reason in result["pass_reasons"]]])
    if result.get("fail_reasons"):
        lines.extend(["", "Watch/fail reasons:", *[f"- {reason}" for reason in result["fail_reasons"]]])
    if result.get("criterion_results"):
        lines.extend(["", "Criteria:"])
        for key, value in result["criterion_results"].items():
            lines.append(f"- {key}: {'✅' if value else '❌'}")
    return "\n".join(lines)


def _format_rich(result: Mapping[str, Any]) -> str:
    """Rich-markup formatted output for beautiful terminal display."""
    ticker = result.get("ticker", "???")
    name = result.get("name", "Unknown")
    passed = result.get("passed", False)
    score = result.get("canslim_score", "N/A")
    band = result.get("score_band", "N/A")
    band_color = _band_style(band)
    verdict_text = "[bold bright_green]✓ PASS[/bold bright_green]" if passed else "[bold red]✗ FAIL / WATCH[/bold red]"

    # ── Header ─────────────────────────────────────────────────────
    lines = [
        f"[bold bright_white]{ticker}[/bold bright_white]  [dim]—[/dim]  [italic]{name}[/italic]",
        f"  판정: {verdict_text}",
        f"  CAN SLIM 점수: [bold]{score}[/bold]  [{band_color}]({band})[/{band_color}]",
        "",
    ]

    # ── Component score bar ────────────────────────────────────────
    components = result.get("component_scores", {})
    labels = ["C", "A", "N", "S", "L", "I", "M"]
    keys = ["c", "a", "n", "s", "l", "i", "m"]
    score_parts = []
    for label, key in zip(labels, keys):
        val = components.get(key, "N/A")
        color = _score_color(val)
        score_parts.append(f"[bold bright_white]{label}[/bold bright_white]=[{color}]{val}[/{color}]")
    lines.append("  " + "  ".join(score_parts))
    lines.append("")

    # ── Key metrics ────────────────────────────────────────────────
    lines.append("  [bold underline bright_cyan]핵심 지표[/bold underline bright_cyan]")
    metrics = [
        ("분기 EPS 성장", _pct(result.get("quarterly_eps_growth"))),
        ("연간 EPS CAGR", _pct(result.get("annual_eps_cagr"))),
        ("매출 성장률", _pct(result.get("revenue_growth"))),
        ("ROE", _pct(result.get("roe"))),
        ("RS Rating", _fmt_rating(result.get("rs_rating"))),
        ("52주 고가 대비", _pct(result.get("price_vs_52w_high"))),
        ("시가총액", _money(result.get("market_cap"))),
    ]
    for label, val in metrics:
        val_display = f"[bright_white]{val}[/bright_white]" if val != "N/A" else "[dim]N/A[/dim]"
        lines.append(f"    [dim]•[/dim] {label:<16} {val_display}")
    lines.append("")

    # ── Setup ──────────────────────────────────────────────────────
    lines.append("  [bold underline bright_cyan]셋업 상태[/bold underline bright_cyan]")
    setup_status = result.get("setup_status", "N/A")
    setup_type = result.get("setup_type", "N/A")
    pivot = _fmt_price(result.get("pivot_price"))
    current = _fmt_price(result.get("current_price"))
    distance = _fmt_num(result.get("pivot_distance_pct"), 2)
    volume_ratio = _fmt_ratio(result.get("breakout_volume_ratio"))
    lines.append(f"    [dim]•[/dim] 상태             [bright_white]{setup_status}[/bright_white]")
    lines.append(f"    [dim]•[/dim] 유형             [bright_white]{setup_type}[/bright_white]")
    lines.append(f"    [dim]•[/dim] Pivot 후보       [bright_white]{pivot}[/bright_white]")
    lines.append(f"    [dim]•[/dim] 현재가           [bright_white]{current}[/bright_white]")
    lines.append(f"    [dim]•[/dim] Pivot 대비       [bright_white]{distance}%[/bright_white]")
    lines.append(f"    [dim]•[/dim] 돌파 거래량       [bright_white]{volume_ratio}[/bright_white]")
    for reason in result.get("setup_reasons", [])[:3]:
        lines.append(f"      [dim]- {reason}[/dim]")
    lines.append("")

    # ── Trade plan ─────────────────────────────────────────────────
    lines.append("  [bold underline bright_cyan]트레이드 플랜[/bold underline bright_cyan]")
    buy_low = result.get("buy_zone_low", "N/A")
    buy_high = result.get("buy_zone_high", "N/A")
    stop = result.get("stop_loss_price", "N/A")
    profit_low = result.get("profit_target_low", "N/A")
    profit_high = result.get("profit_target_high", "N/A")
    if buy_low is None and buy_high is None:
        lines.append("    [dim]•[/dim] 현재 유효한 매수 구간 없음")
    else:
        lines.append(f"    [dim]•[/dim] 매수 구간       [bright_green]{buy_low}[/bright_green] ~ [bright_green]{buy_high}[/bright_green]")
    lines.append(f"    [dim]•[/dim] 손절가          [bright_red]{stop}[/bright_red]")
    lines.append(f"    [dim]•[/dim] 목표 수익       [bright_yellow]{profit_low}[/bright_yellow] ~ [bright_yellow]{profit_high}[/bright_yellow]")
    lines.append("")

    # ── Institutional / insider ────────────────────────────────────
    lines.append("  [bold underline bright_cyan]기관/내부자[/bold underline bright_cyan]")
    inst_ownership = _pct(result.get("institutional_ownership"))
    inst_holders = _fmt_num(result.get("institutional_holders"), 0)
    inst_source = result.get("institutional_data_source", "N/A")
    accum = _fmt_num(result.get("institutional_accumulation_score"), 1)
    insider = result.get("insider_signal", "N/A")
    lines.append(f"    [dim]•[/dim] 기관 보유율      {inst_ownership}")
    lines.append(f"    [dim]•[/dim] 기관 보유자      {inst_holders}")
    lines.append(f"    [dim]•[/dim] 기관 데이터 출처  {inst_source}")
    lines.append(f"    [dim]•[/dim] 13F 축적 점수    {accum}")
    lines.append(f"    [dim]•[/dim] 내부자 신호      {insider}")

    # ── Pass / fail reasons ────────────────────────────────────────
    if result.get("pass_reasons"):
        lines.extend(["", "  [bold underline bright_green]통과 사유[/bold underline bright_green]"])
        for reason in result["pass_reasons"]:
            lines.append(f"    [green]✓[/green] {reason}")

    if result.get("fail_reasons"):
        lines.extend(["", "  [bold underline bright_red]주의/실패 사유[/bold underline bright_red]"])
        for reason in result["fail_reasons"]:
            lines.append(f"    [red]✗[/red] {reason}")

    # ── Criteria grid ──────────────────────────────────────────────
    if result.get("criterion_results"):
        lines.extend(["", "  [bold underline bright_cyan]기준 판정[/bold underline bright_cyan]"])
        for key, value in result["criterion_results"].items():
            icon = "[bright_green]✓[/bright_green]" if value else "[bright_red]✗[/bright_red]"
            lines.append(f"    {icon} {key}")

    return "\n".join(lines)
