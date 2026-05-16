"""CAN SLIM component scoring and explanation helpers."""

from __future__ import annotations

from typing import Any, Dict, Mapping

import pandas as pd


WEIGHTS = {"c": 0.20, "a": 0.20, "n": 0.15, "s": 0.15, "l": 0.15, "i": 0.10, "m": 0.05}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or not pd.notna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _ratio_score(value: Any, threshold: Any, *, cap: float = 1.5) -> float:
    threshold_value = _num(threshold)
    value_num = _num(value)
    if threshold_value <= 0:
        return 100.0 if value_num > 0 else 0.0
    return max(0.0, min(100.0, value_num / (threshold_value * cap) * 100.0))


def _score_band(score: float) -> str:
    if score >= 90:
        return "exceptional"
    if score >= 80:
        return "strong"
    if score >= 70:
        return "watchlist"
    if score >= 60:
        return "developing"
    return "weak"


def _score_current_earnings(company: Mapping[str, Any], criteria: Mapping[str, Any]) -> tuple[float, list[str], list[str]]:
    pass_reasons: list[str] = []
    fail_reasons: list[str] = []
    eps = _num(company.get("quarterly_eps_growth"))
    eps_min = _num(criteria.get("quarterly_eps_growth"))
    revenue = _num(company.get("revenue_growth"))
    revenue_min = _num(criteria.get("revenue_growth"))
    score = 0.7 * _ratio_score(eps, eps_min) + 0.3 * _ratio_score(revenue, revenue_min)
    if eps >= eps_min:
        pass_reasons.append("C: current quarterly earnings growth")
    else:
        fail_reasons.append("C: current quarterly earnings growth below threshold")
    return score, pass_reasons, fail_reasons


def _score_annual_earnings(company: Mapping[str, Any], criteria: Mapping[str, Any]) -> tuple[float, list[str], list[str]]:
    pass_reasons: list[str] = []
    fail_reasons: list[str] = []
    annual = _num(company.get("annual_eps_cagr"))
    annual_min = _num(criteria.get("annual_eps_cagr"))
    roe = _num(company.get("roe"))
    roe_min = _num(criteria.get("roe"))
    debt = _num(company.get("debt_to_equity"), default=float("inf"))
    debt_max = _num(criteria.get("debt_to_equity"), default=float("inf"))
    debt_ok = debt <= 0 or debt <= debt_max
    score = 0.5 * _ratio_score(annual, annual_min) + 0.3 * _ratio_score(roe, roe_min) + 20.0 * int(debt_ok)
    if annual >= annual_min:
        pass_reasons.append("A: annual EPS growth")
    else:
        fail_reasons.append("A: annual EPS growth below threshold")
    if not debt_ok:
        fail_reasons.append("A: debt-to-equity above threshold")
    return min(100.0, score), pass_reasons, fail_reasons


def _score_new(company: Mapping[str, Any], pattern_criteria: Mapping[str, Any]) -> tuple[float, list[str], list[str]]:
    if company.get("new_52w_high"):
        return 100.0, ["N: new 52-week high"], []
    if company.get("valid_breakout"):
        return 90.0, ["N: valid breakout"], []
    price_vs_high = _num(company.get("price_vs_52w_high"))
    hard_min = _num(pattern_criteria.get("price_vs_52w_high_hard_min", 0.90), 0.90)
    if company.get("near_pivot") and price_vs_high >= hard_min:
        return 75.0, ["N: near pivot close to highs"], []
    score = max(0.0, min(60.0, price_vs_high / hard_min * 60.0 if hard_min > 0 else 0.0))
    return score, [], ["N: no new-high, pivot, or breakout signal"]


def _score_supply_demand(company: Mapping[str, Any], criteria: Mapping[str, Any]) -> tuple[float, list[str], list[str]]:
    pass_reasons: list[str] = []
    fail_reasons: list[str] = []
    up_down = _num(company.get("up_down_volume_ratio_50d"))
    up_down_min = _num(criteria.get("up_down_volume_ratio_min", 1.0), 1.0)
    volume_trend = _num(company.get("volume_trend_50_200"))
    volume_min = _num(criteria.get("volume_trend_50_200_min", 0.9), 0.9)
    breakout_volume = _num(company.get("breakout_volume_ratio"))
    breakout_min = _num(criteria.get("breakout_volume_ratio_min", 1.3), 1.3)
    score = 0.45 * _ratio_score(up_down, up_down_min, cap=1.4) + 0.35 * _ratio_score(volume_trend, volume_min, cap=1.4)
    score += 20.0 if breakout_volume <= 0 else 0.20 * _ratio_score(breakout_volume, breakout_min, cap=1.5)
    if up_down >= up_down_min:
        pass_reasons.append("S: accumulation volume")
    else:
        fail_reasons.append("S: up/down volume below threshold")
    return min(100.0, score), pass_reasons, fail_reasons


def _score_leader(company: Mapping[str, Any], criteria: Mapping[str, Any]) -> tuple[float, list[str], list[str]]:
    pass_reasons: list[str] = []
    fail_reasons: list[str] = []
    rs = _num(company.get("rs_rating"))
    rs_min = _num(criteria.get("rs_rating_min", 80), 80)
    near_high = _num(company.get("price_vs_52w_high"))
    near_high_min = _num(criteria.get("price_vs_52w_high_min", 0.85), 0.85)
    rs_line = bool(company.get("rs_line_near_high", False))
    score = 0.6 * _ratio_score(rs, rs_min, cap=1.25) + 0.25 * _ratio_score(near_high, near_high_min, cap=1.15) + 15.0 * int(rs_line)
    if rs >= rs_min:
        pass_reasons.append("L: RS rating leadership")
    else:
        fail_reasons.append("L: RS rating below threshold")
    return min(100.0, score), pass_reasons, fail_reasons


def _score_institutional(company: Mapping[str, Any], criteria: Mapping[str, Any]) -> tuple[float, list[str], list[str]]:
    pass_reasons: list[str] = []
    fail_reasons: list[str] = []
    ownership = _num(company.get("institutional_ownership"))
    holders = _num(company.get("institutional_holders"))
    holders_min = _num(criteria.get("institutional_holders_min", 3), 3)
    holder_change = _num(company.get("institutional_holders_qoq_change"))
    value_change = _num(company.get("institutional_value_qoq_change"))
    accumulation = _num(company.get("institutional_accumulation_score"))
    score = max(
        _ratio_score(ownership, criteria.get("institutional_ownership_min", 0.05), cap=4.0),
        _ratio_score(holders, holders_min, cap=4.0),
        65.0 if holder_change >= 0 and value_change >= 0 and (holder_change != 0 or value_change != 0) else 0.0,
        accumulation,
    )
    if score >= 50:
        pass_reasons.append("I: institutional sponsorship")
    else:
        fail_reasons.append("I: insufficient institutional sponsorship")
    return min(100.0, score), pass_reasons, fail_reasons


def calculate_canslim_score(
    company: Mapping[str, Any],
    criteria: Mapping[str, Any],
    leadership_criteria: Mapping[str, Any],
    supply_demand_criteria: Mapping[str, Any],
    institutional_criteria: Mapping[str, Any],
    pattern_criteria: Mapping[str, Any],
    market_direction_ok: bool,
) -> Dict[str, Any]:
    """Return a company copy with CAN SLIM scores and explanatory reasons."""
    output = dict(company)
    scorers = {
        "c": _score_current_earnings(output, criteria),
        "a": _score_annual_earnings(output, criteria),
        "n": _score_new(output, pattern_criteria),
        "s": _score_supply_demand(output, supply_demand_criteria),
        "l": _score_leader(output, leadership_criteria),
        "i": _score_institutional(output, institutional_criteria),
        "m": (100.0 if market_direction_ok else 0.0, ["M: market direction supportive"] if market_direction_ok else [], [] if market_direction_ok else ["M: market direction not supportive"]),
    }
    component_scores: Dict[str, float] = {}
    pass_reasons: list[str] = []
    fail_reasons: list[str] = []
    for component, (score, passes, fails) in scorers.items():
        rounded = round(float(score), 2)
        component_scores[component] = rounded
        output[f"{component}_score"] = rounded
        pass_reasons.extend(passes)
        fail_reasons.extend(fails)

    total = sum(component_scores[component] * WEIGHTS[component] for component in WEIGHTS)
    output["component_scores"] = component_scores
    output["canslim_score"] = round(total, 2)
    output["score_band"] = _score_band(total)
    output["pass_reasons"] = pass_reasons
    output["fail_reasons"] = fail_reasons
    return output
