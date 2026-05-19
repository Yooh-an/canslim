"""Candidate filtering helpers for CAN SLIM/SEPA screening."""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from src.screeners.canslim_scoring import calculate_canslim_score
from src.screeners.trade_rules import add_trade_rules

def _passes_min_threshold(value: Any, threshold: Any) -> bool:
    """Return True when a numeric value passes a minimum threshold or the threshold is disabled."""
    if threshold is None:
        return True
    return pd.notna(value) and value >= threshold


def _passes_max_threshold(value: Any, threshold: Any) -> bool:
    """Return True when a numeric value passes a maximum threshold or the threshold is disabled."""
    if threshold is None:
        return True
    return pd.notna(value) and value <= threshold


def _passes_security_profile_filter(company: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
    """Return True when company is allowed by optional security-profile filters."""
    profile = company.get("security_profile", "standard")
    include_profiles = criteria.get("include_security_profiles")
    if include_profiles and profile not in include_profiles:
        return False
    exclude_profiles = criteria.get("exclude_security_profiles") or []
    if profile in exclude_profiles:
        return False
    return True


def _check_supply_demand(company: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
    """Evaluate CANSLIM supply/demand using accumulation and optional breakout confirmation."""
    if not criteria.get("require_supply_demand", False):
        return True

    accumulation_ok = _passes_min_threshold(
        company.get("up_down_volume_ratio_50d"),
        criteria.get("up_down_volume_ratio_min", 1.0),
    )
    volume_trend_ok = _passes_min_threshold(
        company.get("volume_trend_50_200"),
        criteria.get("volume_trend_50_200_min", 0.9),
    )

    breakout_confirmation_ok = True
    if criteria.get("require_breakout_volume_confirmation", False):
        near_action = bool(company.get("valid_breakout", False))
        if criteria.get("confirm_volume_for_near_pivot", False):
            near_action = near_action or bool(company.get("near_pivot", False))
        if near_action:
            breakout_confirmation_ok = _passes_min_threshold(
                company.get("breakout_volume_ratio"),
                criteria.get("breakout_volume_ratio_min", 1.3),
            )

    volume_dry_up_ok = True
    if criteria.get("require_volume_dry_up", False):
        volume_dry_up_ok = _passes_max_threshold(
            company.get("volume_dry_up_ratio_10_50"),
            criteria.get("volume_dry_up_ratio_max", 0.8),
        )

    return accumulation_ok and volume_trend_ok and breakout_confirmation_ok and volume_dry_up_ok


def _check_institutional(company: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
    """Evaluate CANSLIM institutional sponsorship with support for ownership or holder-count proxies."""
    if not criteria.get("require_institutional_sponsorship", False):
        return True

    ownership = company.get("institutional_ownership")
    holders = company.get("institutional_holders")

    ownership_ok = (
        _passes_min_threshold(ownership, criteria.get("institutional_ownership_min"))
        and _passes_max_threshold(ownership, criteria.get("institutional_ownership_max"))
    )
    holders_ok = _passes_min_threshold(
        holders,
        criteria.get("institutional_holders_min"),
    )
    holders_trend_ok = _passes_min_threshold(
        company.get("institutional_holders_qoq_change"),
        criteria.get("institutional_holders_qoq_min"),
    )
    value_trend_ok = _passes_min_threshold(
        company.get("institutional_value_qoq_change"),
        criteria.get("institutional_value_qoq_min"),
    )
    trend_ok = holders_trend_ok and value_trend_ok
    accumulation_threshold = criteria.get("institutional_accumulation_score_min")
    accumulation_ok = (
        accumulation_threshold is not None
        and _passes_min_threshold(company.get("institutional_accumulation_score"), accumulation_threshold)
    )

    mode = criteria.get("sponsorship_mode", "ownership")
    if mode == "ownership_and_holders":
        return ownership_ok and holders_ok
    if mode == "ownership_or_holders":
        return ownership_ok or holders_ok
    if mode == "ownership_or_holders_or_trend":
        return ownership_ok or holders_ok or trend_ok or accumulation_ok
    if mode == "trend":
        return trend_ok or accumulation_ok
    if mode == "holders":
        return holders_ok
    return ownership_ok


def _check_market_cap_or_liquidity(company: Dict[str, Any], criteria: Dict[str, Any], leadership_criteria: Dict[str, Any]) -> bool:
    """Pass market-size floor using market cap when known, otherwise liquidity proxy."""
    market_cap_threshold = criteria.get("min_market_cap", 0)
    market_cap = company.get("market_cap")
    if pd.notna(market_cap) and market_cap and market_cap > 0:
        return _passes_min_threshold(market_cap, market_cap_threshold)
    return _passes_min_threshold(
        company.get("avg_dollar_volume_50d"),
        leadership_criteria.get("avg_dollar_volume_min", 0),
    )


def _check_pattern(company: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
    """Evaluate CANSLIM N using high proximity, pivot setup, and breakout signals."""
    if criteria.get("require_hybrid_setup", False):
        price_vs_high = company.get("price_vs_52w_high")
        base_depth = company.get("base_depth_65d")
        breakout_ok = bool(company.get("valid_breakout", False))
        pivot_ok = bool(company.get("near_pivot", False))
        high_ok = _passes_min_threshold(
            price_vs_high,
            criteria.get("price_vs_52w_high_min", 0.85),
        )
        base_ok = pd.notna(base_depth) and base_depth <= criteria.get("base_depth_max", 0.35)
        rs_line_ok = True
        if criteria.get("require_rs_line_near_high_for_setup", False):
            rs_line_ok = bool(company.get("rs_line_near_high", False))

        setup_ok = breakout_ok
        if criteria.get("allow_hybrid_breakout", True):
            setup_ok = setup_ok or (pivot_ok and high_ok and base_ok)
        else:
            setup_ok = pivot_ok and high_ok and base_ok
        return setup_ok and rs_line_ok

    new_high_ok = True
    if criteria.get("require_new_high_or_breakout", False):
        price_vs_high = company.get("price_vs_52w_high", 0)
        breakout_pct = company.get("breakout_pct")
        pivot_ready = (
            bool(company.get("near_pivot", False))
            and price_vs_high >= criteria.get("price_vs_52w_high_hard_min", 0.90)
            and pd.notna(breakout_pct)
            and breakout_pct >= criteria.get("breakout_pct_min", -0.02)
        )
        new_high_ok = (
            bool(company.get("valid_breakout", False))
            or (criteria.get("allow_near_pivot_setup", False) and pivot_ready)
        )
    elif criteria.get("require_new_52w_high", False):
        new_high_ok = bool(company.get("recent_new_52w_high", False))

    base_ok = True
    base_depth = company.get("base_depth_65d")
    if criteria.get("require_base_depth", False):
        base_ok = (
            pd.notna(base_depth)
            and base_depth <= criteria.get("base_depth_max", 0.35)
        )

    breakout_ok = True
    if criteria.get("require_near_pivot", False):
        breakout_ok = breakout_ok and bool(company.get("near_pivot", False))
    if criteria.get("require_valid_breakout", False):
        breakout_ok = breakout_ok and bool(company.get("valid_breakout", False))

    return new_high_ok and base_ok and breakout_ok


def _sort_screen_results(filtered_companies: list[Dict[str, Any]], profile_name: str) -> None:
    """Sort results in-place using a profile-aware ranking."""
    if profile_name == "canslim_hybrid":
        filtered_companies.sort(
            key=lambda x: (
                int(bool(x.get("valid_breakout", False))),
                int(bool(x.get("near_pivot", False))),
                x.get("breakout_volume_ratio", 0) or 0,
                x.get("rs_rating", 0) or 0,
                int(bool(x.get("rs_line_near_high", False))),
                x.get("price_vs_52w_high", 0) or 0,
                -((x.get("volume_dry_up_ratio_10_50", 999) or 999)),
                x.get("quarterly_eps_growth", 0) or 0,
                x.get("annual_eps_cagr", 0) or 0,
            ),
            reverse=True,
        )
        return

    filtered_companies.sort(
        key=lambda x: (
            x.get("canslim_score", 0) or 0,
            (x.get("quarterly_eps_growth", 0) or 0)
            + (x.get("annual_eps_cagr", 0) or 0)
            + (x.get("revenue_growth", 0) or 0),
            x.get("rs_rating", 0) or 0,
            x.get("price_vs_52w_high", 0) or 0,
        ),
        reverse=True,
    )

def _evaluate_screening_candidate(
    company: Dict[str, Any],
    criteria: Dict[str, Any],
    leadership_criteria: Dict[str, Any],
    supply_demand_criteria: Dict[str, Any],
    institutional_criteria: Dict[str, Any],
    pattern_criteria: Dict[str, Any],
    market_direction_ok: bool,
    test_mode: bool,
) -> tuple[bool, Dict[str, bool]]:
    """Evaluate one company and return overall pass plus per-criterion results."""
    if not all(key in company for key in ['ticker', 'name']):
        return False, {}
    if not _passes_security_profile_filter(company, criteria):
        return False, {}

    if any(key not in company for key in ["quarterly_eps_growth", "annual_eps_cagr", "revenue_growth", "profit_margin", "roe"]):
        if test_mode:
            company.setdefault("quarterly_eps_growth", 0.05)
            company.setdefault("annual_eps_cagr", 0.07)
            company.setdefault("revenue_growth", 0.06)
            company.setdefault("profit_margin", 0.04)
            company.setdefault("roe", 0.08)
            company.setdefault("debt_to_equity", 1.2)

    debt_to_equity = company.get("debt_to_equity", float('inf'))
    debt_ok = True if debt_to_equity <= 0 else _passes_max_threshold(
        debt_to_equity,
        criteria.get("debt_to_equity", float('inf')),
    )

    base_depth = company.get("base_depth_65d")
    base_signal = (
        pd.notna(base_depth)
        and base_depth <= pattern_criteria.get("base_depth_max", 0.35)
    )
    breakout_signal = bool(company.get("valid_breakout", False))

    results = {
        "eps": _passes_min_threshold(company.get("quarterly_eps_growth"), criteria.get("quarterly_eps_growth", 0)),
        "eps_cagr": _passes_min_threshold(company.get("annual_eps_cagr"), criteria.get("annual_eps_cagr", 0)),
        "revenue": _passes_min_threshold(company.get("revenue_growth"), criteria.get("revenue_growth", 0)),
        "margin": _passes_min_threshold(company.get("profit_margin"), criteria.get("profit_margin", 0)),
        "roe": _passes_min_threshold(company.get("roe"), criteria.get("roe", 0)),
        "debt": debt_ok,
        "mktcap": _check_market_cap_or_liquidity(company, criteria, leadership_criteria),
        "sp500": True,
        "rs": _passes_min_threshold(company.get("rs_rating"), leadership_criteria.get("rs_rating_min", 80)),
        "near_high": _passes_min_threshold(company.get("price_vs_52w_high"), leadership_criteria.get("price_vs_52w_high_min", 0.85)),
        "liquidity": _passes_min_threshold(company.get("avg_dollar_volume_50d"), leadership_criteria.get("avg_dollar_volume_min", 0)),
        "rs_line": True,
        "industry": True,
        "market_direction": market_direction_ok,
        "supply_demand": _check_supply_demand(company, supply_demand_criteria),
        "institutional": _check_institutional(company, institutional_criteria),
        "new_high": _check_pattern(company, pattern_criteria),
        "base": base_signal,
        "breakout": breakout_signal,
    }

    if criteria.get("outperform_sp500", False):
        results["sp500"] = company.get("market_outperformance_12m", float("-inf")) > 0
    if leadership_criteria.get("rs_line_near_high", False):
        results["rs_line"] = bool(company.get("rs_line_near_high", False))
    if leadership_criteria.get("require_industry_leadership", False):
        results["industry"] = (
            company.get("industry_rs_rank", 0) >= leadership_criteria.get("industry_rs_rank_min", 80)
            and company.get("industry_stock_rank", 0) >= leadership_criteria.get("industry_stock_rank_min", 80)
        )
    pass_results = {
        key: value
        for key, value in results.items()
        if key not in {"base", "breakout"}
    }

    if test_mode:
        return results["mktcap"], results

    return all(pass_results.values()), results


def _filter_screening_candidates(
    companies: list[Dict[str, Any]],
    criteria: Dict[str, Any],
    leadership_criteria: Dict[str, Any],
    supply_demand_criteria: Dict[str, Any],
    institutional_criteria: Dict[str, Any],
    pattern_criteria: Dict[str, Any],
    market_direction_ok: bool,
    test_mode: bool,
) -> tuple[list[Dict[str, Any]], Dict[str, int]]:
    """Filter companies and collect per-criterion pass counts."""
    criteria_counts = {criterion: 0 for criterion in [
        "eps", "eps_cagr", "revenue", "margin", "roe", "debt", "mktcap",
        "sp500", "rs", "near_high", "liquidity", "rs_line", "industry",
        "market_direction", "supply_demand", "institutional", "new_high", "base", "breakout"
    ]}
    filtered_companies = []

    for company in companies:
        passed, criterion_results = _evaluate_screening_candidate(
            company,
            criteria,
            leadership_criteria,
            supply_demand_criteria,
            institutional_criteria,
            pattern_criteria,
            market_direction_ok,
            test_mode,
        )
        if not criterion_results:
            continue
        for criterion, criterion_passed in criterion_results.items():
            if criterion_passed:
                criteria_counts[criterion] += 1
        if passed:
            scored_company = calculate_canslim_score(
                company,
                criteria,
                leadership_criteria,
                supply_demand_criteria,
                institutional_criteria,
                pattern_criteria,
                market_direction_ok,
            )
            filtered_companies.append(add_trade_rules(scored_company))

    return filtered_companies, criteria_counts
