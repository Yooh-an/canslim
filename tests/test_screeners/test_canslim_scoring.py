"""Tests for CAN SLIM component scoring and explanation fields."""

from src.screeners.canslim_scoring import calculate_canslim_score
from src.screeners.candidate_filter import _filter_screening_candidates, _sort_screen_results


CRITERIA = {
    "quarterly_eps_growth": 0.25,
    "annual_eps_cagr": 0.25,
    "revenue_growth": 0.20,
    "profit_margin": 0.05,
    "roe": 0.17,
    "debt_to_equity": 2.0,
    "outperform_sp500": True,
    "min_market_cap": 300_000_000,
}
LEADERSHIP = {
    "rs_rating_min": 80,
    "price_vs_52w_high_min": 0.85,
    "avg_dollar_volume_min": 15_000_000,
    "rs_line_near_high": True,
}
SUPPLY = {
    "require_supply_demand": True,
    "up_down_volume_ratio_min": 1.0,
    "volume_trend_50_200_min": 0.9,
}
INSTITUTIONAL = {
    "require_institutional_sponsorship": True,
    "sponsorship_mode": "ownership_or_holders_or_trend",
    "institutional_ownership_min": 0.05,
    "institutional_ownership_max": 0.95,
    "institutional_holders_min": 3,
    "institutional_holders_qoq_min": 0,
    "institutional_value_qoq_min": 0,
}
PATTERN = {
    "require_new_high_or_breakout": True,
    "allow_near_pivot_setup": True,
    "price_vs_52w_high_hard_min": 0.9,
    "breakout_pct_min": -0.02,
}


PASSING_COMPANY = {
    "ticker": "TEST",
    "name": "Test Corp",
    "quarterly_eps_growth": 0.50,
    "annual_eps_cagr": 0.35,
    "revenue_growth": 0.30,
    "profit_margin": 0.12,
    "roe": 0.25,
    "debt_to_equity": 0.5,
    "market_cap": 5_000_000_000,
    "market_outperformance_12m": 0.20,
    "rs_rating": 92,
    "price_vs_52w_high": 0.96,
    "avg_dollar_volume_50d": 50_000_000,
    "rs_line_near_high": True,
    "up_down_volume_ratio_50d": 1.4,
    "volume_trend_50_200": 1.1,
    "institutional_holders": 25,
    "institutional_value_qoq_change": 0.15,
    "institutional_holders_qoq_change": 3,
    "new_52w_high": True,
    "valid_breakout": True,
    "pivot_price": 100,
    "current_price": 103,
}


def test_calculate_canslim_score_adds_component_scores_band_and_reasons():
    scored = calculate_canslim_score(
        PASSING_COMPANY,
        CRITERIA,
        LEADERSHIP,
        SUPPLY,
        INSTITUTIONAL,
        PATTERN,
        market_direction_ok=True,
    )

    assert scored["canslim_score"] >= 80
    assert scored["score_band"] in {"exceptional", "strong"}
    assert set(scored["component_scores"]) == {"c", "a", "n", "s", "l", "i", "m"}
    assert scored["c_score"] == scored["component_scores"]["c"]
    assert "C: current quarterly earnings growth" in scored["pass_reasons"]
    assert scored["fail_reasons"] == []


def test_institutional_score_respects_max_ownership_overowned_names():
    scored = calculate_canslim_score(
        dict(PASSING_COMPANY, institutional_ownership=0.97, institutional_holders=None, institutional_value_qoq_change=None, institutional_holders_qoq_change=None),
        CRITERIA,
        LEADERSHIP,
        SUPPLY,
        INSTITUTIONAL,
        PATTERN,
        market_direction_ok=True,
    )

    assert scored["component_scores"]["i"] == 0
    assert "I: institutional ownership above maximum" in scored["fail_reasons"]


def test_calculate_canslim_score_does_not_treat_new_high_alone_as_actionable_n():
    scored = calculate_canslim_score(
        dict(PASSING_COMPANY, new_52w_high=True, recent_new_52w_high=True, valid_breakout=False, near_pivot=False),
        CRITERIA,
        LEADERSHIP,
        SUPPLY,
        INSTITUTIONAL,
        PATTERN,
        market_direction_ok=True,
    )

    assert scored["n_score"] < 80
    assert "N: recent high but no actionable pivot/breakout setup" in scored["fail_reasons"]


def test_calculate_canslim_score_records_fail_reasons_for_weak_candidate():
    weak = dict(PASSING_COMPANY, quarterly_eps_growth=-0.10, rs_rating=55, new_52w_high=False, valid_breakout=False)

    scored = calculate_canslim_score(
        weak,
        CRITERIA,
        LEADERSHIP,
        SUPPLY,
        INSTITUTIONAL,
        PATTERN,
        market_direction_ok=False,
    )

    assert scored["c_score"] < 50
    assert scored["l_score"] < 80
    assert scored["m_score"] == 0
    assert "C: current quarterly earnings growth below threshold" in scored["fail_reasons"]
    assert "M: market direction not supportive" in scored["fail_reasons"]


def test_sort_screen_results_prefers_canslim_score_when_available():
    rows = [
        {"ticker": "LOW", "canslim_score": 70, "quarterly_eps_growth": 1.0, "annual_eps_cagr": 1.0, "revenue_growth": 1.0},
        {"ticker": "HIGH", "canslim_score": 90, "quarterly_eps_growth": 0.1, "annual_eps_cagr": 0.1, "revenue_growth": 0.1},
    ]

    _sort_screen_results(rows, "canslim_pure")

    assert rows[0]["ticker"] == "HIGH"


def test_filter_screening_candidates_enriches_passed_rows_with_scores():
    filtered, _ = _filter_screening_candidates(
        [dict(PASSING_COMPANY)],
        CRITERIA,
        LEADERSHIP,
        SUPPLY,
        INSTITUTIONAL,
        PATTERN,
        market_direction_ok=True,
        test_mode=False,
    )

    assert len(filtered) == 1
    assert filtered[0]["canslim_score"] >= 80
    assert filtered[0]["buy_zone_high"] == 105
