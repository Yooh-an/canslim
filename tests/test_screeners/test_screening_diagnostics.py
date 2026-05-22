"""Tests for screening coverage/diagnostic helpers."""

from src.growth_stock_screener import (
    _calculate_metric_coverage,
    _collect_data_quality_warnings,
    _refresh_profile_breakout_signals,
    _score_companies_for_diagnostics,
)


def test_metric_coverage_counts_zero_and_false_values_as_available():
    companies = [
        {
            "ticker": "AAA",
            "market_cap": 0,
            "quarterly_eps_growth": 0,
            "new_52w_high": False,
            "valid_breakout": False,
            "insider_buy_count_90d": 0,
        },
        {
            "ticker": "BBB",
            "market_cap": 10_000_000,
            "quarterly_eps_growth": 0.25,
            "new_52w_high": True,
            "valid_breakout": False,
            "insider_buy_count_90d": 2,
        },
        {"ticker": "CCC"},
    ]

    coverage, signal_counts = _calculate_metric_coverage(companies)

    assert coverage["market_cap"] == 1
    assert coverage["quarterly_eps_growth"] == 2
    assert coverage["new_52w_high"] == 2
    assert coverage["valid_breakout"] == 2
    assert coverage["insider_buy_count_90d"] == 2
    assert signal_counts["new_52w_high"] == 1
    assert signal_counts["valid_breakout"] == 0


def test_refresh_profile_breakout_signals_uses_active_profile_threshold():
    companies = [
        {
            "ticker": "WATCH",
            "breakout_pct": 0.03,
            "breakout_volume_ratio": 1.25,
            "valid_breakout": False,
        },
        {
            "ticker": "WEAKVOL",
            "breakout_pct": 0.03,
            "breakout_volume_ratio": 1.10,
            "valid_breakout": True,
        },
        {
            "ticker": "NODATA",
            "valid_breakout": True,
        },
    ]

    refreshed = _refresh_profile_breakout_signals(
        companies,
        {"breakout_volume_ratio_min": 1.20},
    )

    assert refreshed[0]["valid_breakout"] is True
    assert refreshed[1]["valid_breakout"] is False
    assert "valid_breakout" not in refreshed[2]


def test_score_companies_for_diagnostics_populates_canslim_score_before_filtering():
    companies = [
        {
            "ticker": "AAA",
            "name": "Alpha",
            "quarterly_eps_growth": 0.2,
            "annual_eps_cagr": 0.2,
            "revenue_growth": 0.2,
            "roe": 0.2,
            "debt_to_equity": 0.5,
            "rs_rating": 80,
            "price_vs_52w_high": 0.9,
        }
    ]

    scored = _score_companies_for_diagnostics(
        companies,
        {"quarterly_eps_growth": 0.25, "annual_eps_cagr": 0.25, "revenue_growth": 0.25, "roe": 0.17, "debt_to_equity": 2.0},
        {"rs_rating_min": 80, "price_vs_52w_high_min": 0.85},
        {"up_down_volume_ratio_min": 1.0, "volume_trend_50_200_min": 0.9},
        {},
        {},
        True,
    )

    assert scored[0]["canslim_score"] > 0
    assert scored[0]["score_band"]


def test_collect_data_quality_warnings_omits_insider_when_disabled():
    warnings = _collect_data_quality_warnings(
        {"market_cap": 10, "insider_buy_count_90d": 0, "net_insider_buy_value_90d": 0},
        total=10,
        config={"insider_data": {"enabled": False}},
    )

    assert not any("내부자 Form 4" in warning for warning in warnings)


def test_collect_data_quality_warnings_flags_low_market_cap_and_missing_insider_data():
    warnings = _collect_data_quality_warnings(
        {"market_cap": 1, "insider_buy_count_90d": 0, "net_insider_buy_value_90d": 0},
        total=10,
        config={
            "data_quality": {"market_cap_min_coverage": 0.5},
            "insider_data": {"enabled": True},
        },
    )

    joined = "\n".join(warnings)
    assert "시가총액 커버리지 낮음" in joined
    assert "내부자 Form 4 데이터 없음" in joined
