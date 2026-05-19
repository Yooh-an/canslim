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


def test_analyze_ticker_falls_back_to_raw_company_list_when_enriched_is_stale(tmp_path):
    cfg = _config(tmp_path)
    processed_dir = Path(cfg["data_paths"]["processed_data_dir"])
    processed_dir.mkdir(parents=True, exist_ok=True)
    (processed_dir / "companies_list_enriched.json").write_text(json.dumps([]))
    (processed_dir / "companies_list.json").write_text(json.dumps([_company()]))
    (processed_dir / "market_direction.json").write_text(json.dumps({"market_direction_status": "confirmed_uptrend"}))

    result = analyze_ticker("TEST", cfg)

    assert result["found"] is True
    assert result["ticker"] == "TEST"


def test_analyze_ticker_can_use_raw_companies_json_as_last_resort(tmp_path):
    cfg = _config(tmp_path)
    raw_dir = tmp_path / "raw"
    cfg["data_paths"]["raw_data_dir"] = str(raw_dir)
    (Path(cfg["data_paths"]["processed_data_dir"]) / "companies_list_enriched.json").write_text(json.dumps([]))
    extracted_dir = raw_dir / "submissions_extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    (extracted_dir / "companies.json").write_text(json.dumps({
        "0002023554": {
            "name": "Sandisk Corporation",
            "tickers": ["SNDK"],
            "exchanges": ["Nasdaq"],
            "marketCap": 0,
        }
    }))
    (Path(cfg["data_paths"]["processed_data_dir"]) / "market_direction.json").write_text(json.dumps({"market_direction_status": "confirmed_uptrend"}))

    result = analyze_ticker("SNDK", cfg)

    assert result["found"] is True
    assert result["ticker"] == "SNDK"
    assert result["name"] == "Sandisk Corporation"


def test_analyze_ticker_reports_missing_ticker(tmp_path):
    cfg = _config(tmp_path)
    (Path(cfg["data_paths"]["processed_data_dir"]) / "companies_list_enriched.json").write_text(json.dumps([]))

    result = analyze_ticker("NOPE", cfg)

    assert result == {"found": False, "ticker": "NOPE"}


def test_analyze_ticker_enriches_missing_market_data_on_demand(tmp_path):
    cfg = _config(tmp_path)
    company = _company()
    company.pop("rs_rating")
    company.pop("price_vs_52w_high")
    company["market_cap"] = 0
    (Path(cfg["data_paths"]["processed_data_dir"]) / "companies_list_enriched.json").write_text(json.dumps([company]))
    (Path(cfg["data_paths"]["processed_data_dir"]) / "market_direction.json").write_text(json.dumps({"market_direction_status": "confirmed_uptrend"}))

    from unittest.mock import patch
    with patch("src.screeners.ticker_analysis.MarketDataEnricher") as enricher_cls:
        enricher = enricher_cls.return_value
        enriched_company = {**company, "rs_rating": 91, "price_vs_52w_high": 0.94, "market_cap": 10_000_000_000}
        enricher.enrich_single_ticker_market_data.return_value = enriched_company
        result = analyze_ticker("TEST", cfg)

    assert result["rs_rating"] == 91
    assert result["price_vs_52w_high"] == 0.94
    assert result["market_cap"] == 10_000_000_000
    enricher.enrich_single_ticker_market_data.assert_called_once()


def test_analyze_ticker_applies_local_13f_institutional_enrichment(tmp_path):
    cfg = _config(tmp_path)
    cfg["institutional_data"] = {"enabled": True}
    company = _company()
    company.pop("institutional_holders")
    company.pop("institutional_accumulation_score")
    company["institutional_ownership"] = None
    (Path(cfg["data_paths"]["processed_data_dir"]) / "companies_list_enriched.json").write_text(json.dumps([company]))
    (Path(cfg["data_paths"]["processed_data_dir"]) / "market_direction.json").write_text(json.dumps({"market_direction_status": "confirmed_uptrend"}))

    from unittest.mock import patch
    with patch("src.screeners.ticker_analysis.enrich_companies_with_13f_data") as enrich_13f:
        enrich_13f.return_value = [{**company, "institutional_holders": 7, "institutional_accumulation_score": 81, "institutional_data_source": "sec_13f"}]
        result = analyze_ticker("TEST", cfg)

    assert result["institutional_holders"] == 7
    assert result["institutional_accumulation_score"] == 81
    assert result["institutional_data_source"] == "sec_13f"
    enrich_13f.assert_called_once()


def test_analyze_ticker_enriches_when_current_price_or_institutional_data_missing(tmp_path):
    cfg = _config(tmp_path)
    company = _company()
    company.pop("current_price")
    company.pop("institutional_holders")
    company.pop("institutional_accumulation_score")
    company["institutional_ownership"] = None
    (Path(cfg["data_paths"]["processed_data_dir"]) / "companies_list_enriched.json").write_text(json.dumps([company]))
    (Path(cfg["data_paths"]["processed_data_dir"]) / "market_direction.json").write_text(json.dumps({"market_direction_status": "confirmed_uptrend"}))

    from unittest.mock import patch
    with patch("src.screeners.ticker_analysis.MarketDataEnricher") as enricher_cls:
        enricher = enricher_cls.return_value
        enriched_company = {
            **company,
            "current_price": 103,
            "institutional_ownership": 0.55,
            "institutional_data_source": "yfinance_info",
        }
        enricher.enrich_single_ticker_market_data.return_value = enriched_company
        result = analyze_ticker("TEST", cfg)

    assert result["current_price"] == 103
    assert result["institutional_ownership"] == 0.55
    assert result["institutional_data_source"] == "yfinance_info"
    enricher.enrich_single_ticker_market_data.assert_called_once()


def test_analyze_ticker_uses_simfin_fallback_for_missing_fundamentals(tmp_path):
    cfg = _config(tmp_path)
    cfg["fundamental_data"] = {"enabled": True, "provider": "simfin"}
    company = _company()
    company["quarterly_eps_growth"] = None
    company["revenue_growth"] = None
    (Path(cfg["data_paths"]["processed_data_dir"]) / "companies_list_enriched.json").write_text(json.dumps([company]))
    (Path(cfg["data_paths"]["processed_data_dir"]) / "market_direction.json").write_text(json.dumps({"market_direction_status": "confirmed_uptrend"}))

    from unittest.mock import patch
    with patch("src.enrichers.fundamental_fallback.SimFinClient") as client_cls:
        client = client_cls.return_value
        client.has_api_key.return_value = True
        client.get_fundamental_metrics.return_value = {
            "quarterly_eps_growth": 0.55,
            "revenue_growth": 0.35,
            "financial_data_source": "simfin",
        }
        result = analyze_ticker("TEST", cfg)

    assert result["quarterly_eps_growth"] == 0.55
    assert result["revenue_growth"] == 0.35
    assert result["financial_data_source"] == "simfin"


def test_format_ticker_analysis_rounds_noisy_decimal_values():
    text = format_ticker_analysis(
        {
            "found": True,
            "ticker": "SNDK",
            "name": "Sandisk Corporation",
            "passed": False,
            "canslim_score": 64.9,
            "score_band": "developing",
            "component_scores": {},
            "rs_rating": 98.3475037073653,
            "current_price": 1333.010009765625,
            "pivot_price": 1562.34,
            "pivot_distance_pct": -14.682342,
            "breakout_volume_ratio": 0.8075481793390077,
            "setup_status": "below_pivot_not_actionable",
            "setup_type": "no_setup",
        },
        rich_mode=True,
    )

    assert "98.3" in text
    assert "1333.01" in text
    assert "-14.68%" in text
    assert "0.81x" in text
    assert "81.01" not in text
    assert "98.3475037073653" not in text
    assert "1333.010009765625" not in text
    assert "0.8075481793390077" not in text


def test_format_ticker_analysis_includes_key_sections(tmp_path):
    cfg = _config(tmp_path)
    (Path(cfg["data_paths"]["processed_data_dir"]) / "companies_list_enriched.json").write_text(json.dumps([_company()]))
    (Path(cfg["data_paths"]["processed_data_dir"]) / "market_direction.json").write_text(json.dumps({"market_direction_status": "confirmed_uptrend"}))

    text = format_ticker_analysis(analyze_ticker("TEST", cfg))

    assert "Ticker: TEST" in text
    assert "CAN SLIM Score" in text
    assert "C/A/N/S/L/I/M" in text
    assert "Setup:" in text
    assert "Pivot distance" in text
    assert "Buy zone" in text
