"""Tests for CAN SLIM leadership and industry ranking metrics."""

import pandas as pd

from src.enrichers.market_data_enricher import MarketDataEnricher


def test_single_leadership_metrics_flags_rs_line_new_high():
    enricher = MarketDataEnricher({"leadership_criteria": {"rs_line_high_threshold": 0.95}})
    dates = pd.date_range("2025-01-01", periods=260, freq="B")
    benchmark = pd.Series([100 + i * 0.1 for i in range(260)], index=dates)
    close = pd.Series([50 + i * 0.3 for i in range(260)], index=dates)
    history = pd.DataFrame({"Close": close, "Volume": [1_000_000] * 260}, index=dates)

    metrics = enricher._calculate_single_leadership_metrics(history, benchmark)

    assert metrics["rs_line_near_high"] is True
    assert metrics["rs_line_new_high"] is True
    assert metrics["rs_line_pct_from_high"] == 0


def test_enrich_single_ticker_market_data_uses_price_history_and_market_cap_fallback(tmp_path):
    enricher = MarketDataEnricher({
        "data_paths": {"raw_data_dir": str(tmp_path), "processed_data_dir": str(tmp_path)},
        "market_data": {"leadership_period": "15mo", "leadership_chunk_size": 25},
    })
    dates = pd.date_range("2025-01-01", periods=260, freq="B")
    history = pd.DataFrame({"Close": range(100, 360), "Volume": [1_000_000] * 260}, index=dates)
    benchmark = pd.DataFrame({"Close": [100] * 260, "Volume": [1_000_000] * 260}, index=dates)
    enricher._fetch_yfinance_market_data = lambda tickers: {"TEST": {"ticker": "TEST", "shares_outstanding": 10}}
    enricher._download_price_history = lambda tickers, period, chunk_size, cached_only=False: {"TEST": history}
    enricher._download_single_history = lambda ticker, period: benchmark
    enricher._load_market_data_files = lambda directory: {"AAA": {"ticker": "AAA", "rs_score": -1.0}}

    enriched = enricher.enrich_single_ticker_market_data({"ticker": "TEST", "name": "Test"})

    assert enriched["current_price"] == 359
    assert enriched["market_cap"] == 3590
    assert enriched["market_cap_source"] == "price_history_x_shares"
    assert enriched["price_vs_52w_high"] == 1.0
    assert enriched["rs_rating"] == 99.0


def test_market_enrichment_refetches_cached_ticker_missing_market_cap_and_preserves_metrics(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    companies_file = processed / "companies_list.json"
    companies_file.write_text('[{"ticker": "HWM", "name": "Howmet"}]')
    enricher = MarketDataEnricher({
        "_quiet": True,
        "data_paths": {"raw_data_dir": str(tmp_path / "raw"), "processed_data_dir": str(processed)},
        "market_data": {"enrich_only_screenable_candidates": False},
    })
    requested = []

    enricher._load_market_data_files = lambda directory: {"HWM": {"ticker": "HWM", "rs_rating": 79.0}}

    def fake_fetch(tickers):
        requested.extend(tickers)
        return {"HWM": {"ticker": "HWM", "market_cap": 111_000_000_000, "market_cap_source": "yfinance"}}

    enricher._fetch_yfinance_market_data = fake_fetch
    enricher._calculate_leadership_metrics = lambda companies: {"HWM": {"ticker": "HWM", "price_vs_52w_high": 0.99}}
    enricher._save_market_data_file = lambda ticker, data: None

    enriched = enricher.enrich_companies_with_market_data(max_companies=10)

    assert requested == ["HWM"]
    assert enriched[0]["market_cap"] == 111_000_000_000
    assert enriched[0]["market_cap_source"] == "yfinance"
    assert enriched[0]["rs_rating"] == 79.0
    assert enriched[0]["price_vs_52w_high"] == 0.99


def test_add_industry_ranks_marks_top_groups_and_leaders():
    enricher = MarketDataEnricher({})
    results = {
        "AAA": {"industry_group": "Software", "rs_score": 0.50},
        "BBB": {"industry_group": "Software", "rs_score": 0.25},
        "CCC": {"industry_group": "Retail", "rs_score": 0.10},
    }

    enricher._add_industry_ranks(results)

    assert results["AAA"]["industry_group_leader"] is True
    assert results["AAA"]["industry_stock_leader"] is True
    assert results["BBB"]["industry_group_leader"] is True
    assert results["BBB"]["industry_stock_leader"] is False
    assert results["CCC"]["industry_group_leader"] is False
