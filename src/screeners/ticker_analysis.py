"""Single ticker CAN SLIM analysis helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping

from src.screeners.candidate_filter import _evaluate_screening_candidate
from src.screeners.canslim_scoring import calculate_canslim_score
from src.screeners.trade_rules import add_trade_rules


def _load_companies(config: Mapping[str, Any]) -> list[Dict[str, Any]]:
    processed_dir = Path(config.get("data_paths", {}).get("processed_data_dir", "data/processed"))
    enriched_file = processed_dir / "companies_list_enriched.json"
    companies_file = processed_dir / "companies_list.json"
    source = enriched_file if enriched_file.exists() else companies_file
    if not source.exists():
        return []
    with source.open("r") as f:
        payload = json.load(f)
    return payload if isinstance(payload, list) else []


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
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "N/A"


def _money(value: Any) -> str:
    try:
        value = float(value)
    except Exception:
        return "N/A"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.0f}"


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
        f"- RS rating: {result.get('rs_rating', 'N/A')}",
        f"- Price vs 52w high: {_pct(result.get('price_vs_52w_high'))}",
        f"- Market cap: {_money(result.get('market_cap'))}",
        "",
        "Trade plan:",
        f"- Buy zone: {result.get('buy_zone_low', 'N/A')} ~ {result.get('buy_zone_high', 'N/A')}",
        f"- Stop loss: {result.get('stop_loss_price', 'N/A')}",
        f"- Profit target: {result.get('profit_target_low', 'N/A')} ~ {result.get('profit_target_high', 'N/A')}",
        "",
        "Institutional / insider:",
        f"- Institutional holders: {result.get('institutional_holders', 'N/A')}",
        f"- 13F accumulation score: {result.get('institutional_accumulation_score', 'N/A')}",
        f"- Insider signal: {result.get('insider_signal', 'N/A')}",
    ]
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
        ("RS Rating", str(result.get("rs_rating", "N/A"))),
        ("52주 고가 대비", _pct(result.get("price_vs_52w_high"))),
        ("시가총액", _money(result.get("market_cap"))),
    ]
    for label, val in metrics:
        val_display = f"[bright_white]{val}[/bright_white]" if val != "N/A" else "[dim]N/A[/dim]"
        lines.append(f"    [dim]•[/dim] {label:<16} {val_display}")
    lines.append("")

    # ── Trade plan ─────────────────────────────────────────────────
    lines.append("  [bold underline bright_cyan]트레이드 플랜[/bold underline bright_cyan]")
    buy_low = result.get("buy_zone_low", "N/A")
    buy_high = result.get("buy_zone_high", "N/A")
    stop = result.get("stop_loss_price", "N/A")
    profit_low = result.get("profit_target_low", "N/A")
    profit_high = result.get("profit_target_high", "N/A")
    lines.append(f"    [dim]•[/dim] 매수 구간       [bright_green]{buy_low}[/bright_green] ~ [bright_green]{buy_high}[/bright_green]")
    lines.append(f"    [dim]•[/dim] 손절가          [bright_red]{stop}[/bright_red]")
    lines.append(f"    [dim]•[/dim] 목표 수익       [bright_yellow]{profit_low}[/bright_yellow] ~ [bright_yellow]{profit_high}[/bright_yellow]")
    lines.append("")

    # ── Institutional / insider ────────────────────────────────────
    lines.append("  [bold underline bright_cyan]기관/내부자[/bold underline bright_cyan]")
    inst_holders = result.get("institutional_holders", "N/A")
    accum = result.get("institutional_accumulation_score", "N/A")
    insider = result.get("insider_signal", "N/A")
    lines.append(f"    [dim]•[/dim] 기관 보유자      {inst_holders}")
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
