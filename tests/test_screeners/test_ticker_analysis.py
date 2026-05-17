"""Tests for single-ticker CAN SLIM analysis."""

import json
from pathlib import Path

from src.screeners.ticker_analysis import analyze_ticker, format_ticker_analysis


def _config(tmp_path):
    return {
        "data_paths": {
            "processed_data_dir": str(tmp_path),
            "output_file": str(tmp_path / "results.csv"),
        },
        "screening_criteria": {
            "quarterly_eps_growth": 0.25,
            "annual_eps_cagr": 0.25,
            "revenue_growth": 0.20,
            "profit_margin": 0.05,
            "roe": 0.17,
            "debt_to_equity": 2.0,
            "outperform_sp500": True,
            "min_market_cap": 300_000_000,
        },
        "leadership_criteria": {
            "rs_rating_min": 80,
            "price_vs_52w_high_min": 0.85,
            "avg_dollar_volume_min": 15_000_000,
            "rs_line_near_high": True,
        },
        "market_direction": {"required": True, "allowed_statuses": ["confirmed_uptrend"]},
        "supply_demand_criteria": {
            "require_supply_demand": True,
            "up_down_volume_ratio_min": 1.0,
            "volume_trend_50_200_min": 0.9,
        },
        "institutional_criteria": {
            "require_institutional_sponsorship": True,
            "sponsorship_mode": "ownership_or_holders_or_trend",
            "institutional_holders_min": 3,
            "institutional_holders_qoq_min": 0,
            "institutional_value_qoq_min": 0,
            "institutional_accumulation_score_min": 60,
        },
        "pattern_criteria": {
            "require_new_high_or_breakout": True,
            "allow_near_pivot_setup": True,
            "price_vs_52w_high_hard_min": 0.9,
            "breakout_pct_min": -0.02,
        },
        "profile_name": "canslim_pure",
    }


def _company():
    return {
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
        "institutional_accumulation_score": 75,
        "new_52w_high": True,
        "valid_breakout": True,
        "pivot_price": 100,
        "current_price": 103,
    }


def test_analyze_ticker_scores_and_evaluates_one_company(tmp_path):
    cfg = _config(tmp_path)
    (Path(cfg["data_paths"]["processed_data_dir"]) / "companies_list_enriched.json").write_text(json.dumps([_company()]))
    (Path(cfg["data_paths"]["processed_data_dir"]) / "market_direction.json").write_text(json.dumps({"market_direction_status": "confirmed_uptrend"}))

    result = analyze_ticker("test", cfg)

    assert result["found"] is True
    assert result["ticker"] == "TEST"
    assert result["passed"] is True
    assert result["canslim_score"] >= 80
    assert result["criterion_results"]["eps"] is True
    assert result["buy_zone_high"] == 105


def test_analyze_ticker_reports_missing_ticker(tmp_path):
    cfg = _config(tmp_path)
    (Path(cfg["data_paths"]["processed_data_dir"]) / "companies_list_enriched.json").write_text(json.dumps([]))

    result = analyze_ticker("NOPE", cfg)

    assert result == {"found": False, "ticker": "NOPE"}


def test_format_ticker_analysis_includes_key_sections(tmp_path):
    cfg = _config(tmp_path)
    (Path(cfg["data_paths"]["processed_data_dir"]) / "companies_list_enriched.json").write_text(json.dumps([_company()]))
    (Path(cfg["data_paths"]["processed_data_dir"]) / "market_direction.json").write_text(json.dumps({"market_direction_status": "confirmed_uptrend"}))

    text = format_ticker_analysis(analyze_ticker("TEST", cfg))

    assert "Ticker: TEST" in text
    assert "CAN SLIM Score" in text
    assert "C/A/N/S/L/I/M" in text
    assert "Buy zone" in text
