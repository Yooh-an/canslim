"""Tests for CAN SLIM leadership and industry ranking metrics."""

import pandas as pd
import pytest

from src.enrichers import market_data_enricher
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


def test_single_leadership_metrics_tracks_recent_52w_high_separately_from_latest_close():
    enricher = MarketDataEnricher({"market_data": {"recent_new_high_lookback_days": 10}})
    dates = pd.date_range("2025-01-01", periods=260, freq="B")
    close_values = list(range(100, 350)) + [360, 355, 352, 350, 348, 346, 344, 342, 340, 338]
    high_values = close_values.copy()
    high_values[-10] = 365
    history = pd.DataFrame(
        {"Close": close_values, "High": high_values, "Volume": [1_000_000] * 260},
        index=dates,
    )

    metrics = enricher._calculate_single_leadership_metrics(history, None)

    assert metrics["new_52w_high"] is False
    assert metrics["recent_new_52w_high"] is True
    assert metrics["recent_new_52w_high_days_ago"] == 9


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
    enricher._fetch_sec_metadata_for_tickers = lambda tickers: {}
    enricher._calculate_leadership_metrics = lambda companies: {"HWM": {"ticker": "HWM", "price_vs_52w_high": 0.99}}
    enricher._save_market_data_file = lambda ticker, data: None

    enriched = enricher.enrich_companies_with_market_data(max_companies=10)

    assert requested == ["HWM"]
    assert enriched[0]["market_cap"] == 111_000_000_000
    assert enriched[0]["market_cap_source"] == "yfinance"
    assert enriched[0]["rs_rating"] == 79.0
    assert enriched[0]["price_vs_52w_high"] == 0.99


def test_market_enrichment_fetches_sec_metadata_even_when_yfinance_industry_exists(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    companies_file = processed / "companies_list.json"
    companies_file.write_text('[{"ticker": "NVDA", "name": "NVIDIA", "cik": "1045810"}]')
    enricher = MarketDataEnricher({
        "_quiet": True,
        "data_paths": {"raw_data_dir": str(tmp_path / "raw"), "processed_data_dir": str(processed)},
        "market_data": {"enrich_only_screenable_candidates": False},
    })
    sec_requested = []
    saved = {}

    enricher._load_market_data_files = lambda directory: {
        "NVDA": {
            "ticker": "NVDA",
            "market_cap": 1_000_000_000,
            "rs_rating": 80.0,
            "industry": "Semiconductors",
            "sector": "Technology",
        }
    }
    enricher._fetch_yfinance_market_data = lambda tickers: {}

    def fake_sec_fetch(tickers):
        sec_requested.extend(tickers)
        return {"NVDA": {"ticker": "NVDA", "sic": "3674", "sicDescription": "Semiconductors & Related Devices"}}

    enricher._fetch_sec_metadata_for_tickers = fake_sec_fetch
    enricher._calculate_leadership_metrics = lambda companies: {}
    enricher._save_market_data_file = lambda ticker, data: saved.setdefault(ticker, dict(data))

    enriched = enricher.enrich_companies_with_market_data(max_companies=10)

    assert sec_requested == ["NVDA"]
    assert saved["NVDA"]["sicDescription"] == "Semiconductors & Related Devices"
    assert enriched[0]["sicDescription"] == "Semiconductors & Related Devices"


def test_industry_group_prefers_sec_sic_description_over_yfinance_industry():
    enricher = MarketDataEnricher({})

    group = enricher._industry_group_for_company({
        "industry": "Semiconductors",
        "sector": "Technology",
        "sic": "3674",
        "sicDescription": "Semiconductors & Related Devices",
    })

    assert group == "Semiconductors & Related Devices"


def test_yfinance_info_rate_limit_disables_info_fallback_but_preserves_fast_info(monkeypatch):
    class FakeFastInfo:
        def get(self, key):
            return {"market_cap": 123_000_000, "last_price": 12.3, "shares": 10_000_000}.get(key)

    class FakeTicker:
        info_calls = 0

        def __init__(self, ticker):
            self.fast_info = FakeFastInfo()

        def get_info(self):
            FakeTicker.info_calls += 1
            raise Exception("Too Many Requests. Rate limited. Try after a while.")

    monkeypatch.setattr(market_data_enricher.yf, "Ticker", FakeTicker)
    enricher = MarketDataEnricher({"market_data": {"use_yfinance_info_fallback": True}})
    enricher._fetch_sec_company_metadata_for_ticker = lambda ticker: {}

    first = enricher._fetch_single_yfinance_ticker("AAA")
    second = enricher._fetch_single_yfinance_ticker("BBB")

    assert first["market_cap"] == 123_000_000
    assert second["market_cap"] == 123_000_000
    assert FakeTicker.info_calls == 1
    assert enricher._yfinance_info_rate_limited is True


def test_bulk_yfinance_market_data_stops_after_global_rate_limit(monkeypatch, tmp_path):
    class FakeFastInfo:
        def get(self, key):
            raise Exception("Too Many Requests. Rate limited. Try after a while.")

    class FakeTicker:
        init_calls = 0

        def __init__(self, ticker):
            FakeTicker.init_calls += 1
            self.fast_info = FakeFastInfo()

        def get_info(self):
            raise AssertionError("get_info should be skipped in bulk")

    monkeypatch.setattr(market_data_enricher.yf, "Ticker", FakeTicker)
    enricher = MarketDataEnricher({
        "data_paths": {"raw_data_dir": str(tmp_path / "raw"), "processed_data_dir": str(tmp_path)},
        "market_data": {"use_yfinance_info_fallback": True},
    })
    enricher._save_market_data_file = lambda ticker, data: None
    enricher._fetch_sec_company_metadata_for_ticker = lambda ticker: {}

    data = enricher._fetch_yfinance_market_data(["AAA", "BBB", "CCC"])

    assert data == {}
    assert FakeTicker.init_calls == 1
    assert enricher._yfinance_rate_limited is True


def test_bulk_yfinance_market_data_uses_get_info_with_sequential_rate_limit_control(monkeypatch, tmp_path):
    class FakeFastInfo:
        def get(self, key):
            return {"market_cap": 123_000_000, "last_price": 12.3, "shares": 10_000_000}.get(key)

    class FakeTicker:
        info_calls = 0

        def __init__(self, ticker):
            self.fast_info = FakeFastInfo()

        def get_info(self):
            FakeTicker.info_calls += 1
            return {"industry": "Software"}

    monkeypatch.setattr(market_data_enricher.yf, "Ticker", FakeTicker)
    enricher = MarketDataEnricher({
        "data_paths": {"raw_data_dir": str(tmp_path / "raw"), "processed_data_dir": str(tmp_path)},
        "market_data": {"use_yfinance_info_fallback": True},
    })
    enricher._save_market_data_file = lambda ticker, data: None
    enricher._fetch_sec_company_metadata_for_ticker = lambda ticker: {}

    data = enricher._fetch_yfinance_market_data(["AAA", "BBB"])

    assert data["AAA"]["market_cap"] == 123_000_000
    assert data["AAA"]["industry"] == "Software"
    assert data["BBB"]["market_cap"] == 123_000_000
    assert data["BBB"]["industry"] == "Software"
    assert FakeTicker.info_calls == 2


def test_calculate_leadership_metrics_uses_cached_industry_for_ranking(tmp_path):
    enricher = MarketDataEnricher({
        "data_paths": {"raw_data_dir": str(tmp_path / "raw"), "processed_data_dir": str(tmp_path)},
        "market_data": {"leadership_universe_size": None, "leadership_period": "15mo", "leadership_chunk_size": 25},
    })
    companies = [
        {"ticker": "AAA", "quarterly_eps_growth": 0.30},
        {"ticker": "BBB", "quarterly_eps_growth": 0.30},
        {"ticker": "CCC", "quarterly_eps_growth": 0.30},
    ]
    cached_market_data = {
        "AAA": {"ticker": "AAA", "industry": "Software"},
        "BBB": {"ticker": "BBB", "sector": "Retail"},
        "CCC": {"ticker": "CCC", "industry": "Software"},
    }

    dates = pd.date_range("2025-01-01", periods=2, freq="B")
    benchmark = pd.DataFrame({"Close": [100, 101]}, index=dates)
    score_inputs = {"AAA": {"score": 0.60}, "BBB": {"score": 0.10}, "CCC": {"score": 0.30}}
    enricher._load_market_data_files = lambda directory: cached_market_data
    enricher._download_price_history = lambda tickers, period, chunk_size, cached_only=False: score_inputs
    enricher._download_single_history = lambda ticker, period: benchmark
    enricher._calculate_single_leadership_metrics = lambda history, benchmark_close: {"rs_score": history["score"]}
    enricher._save_market_data_file = lambda ticker, data: None

    metrics = enricher._calculate_leadership_metrics(companies)

    assert metrics["AAA"]["industry_group"] == "Software"
    assert metrics["BBB"]["industry_group"] == "Retail"
    assert metrics["AAA"]["industry_rs_rank"] > metrics["BBB"]["industry_rs_rank"]
    assert metrics["AAA"]["industry_stock_leader"] is True
    assert metrics["CCC"]["industry_stock_leader"] is False


def test_calculate_leadership_metrics_fetches_sec_metadata_when_industry_is_missing(tmp_path):
    enricher = MarketDataEnricher({
        "data_paths": {"raw_data_dir": str(tmp_path / "raw"), "processed_data_dir": str(tmp_path)},
        "market_data": {"leadership_universe_size": None, "leadership_period": "15mo", "leadership_chunk_size": 25},
    })
    companies = [
        {"ticker": "NVDA", "cik": "1045810", "quarterly_eps_growth": 0.30},
        {"ticker": "VRT", "cik": "1674101", "quarterly_eps_growth": 0.30},
    ]
    dates = pd.date_range("2025-01-01", periods=2, freq="B")
    benchmark = pd.DataFrame({"Close": [100, 101]}, index=dates)
    score_inputs = {"NVDA": {"score": 0.60}, "VRT": {"score": 0.10}}
    requested = []
    saved = {}

    enricher._load_market_data_files = lambda directory: {}
    enricher._download_price_history = lambda tickers, period, chunk_size, cached_only=False: score_inputs
    enricher._download_single_history = lambda ticker, period: benchmark
    enricher._calculate_single_leadership_metrics = lambda history, benchmark_close: {"rs_score": history["score"]}
    enricher._save_market_data_file = lambda ticker, data: saved.setdefault(ticker, dict(data))

    def fake_sec_fetch(tickers):
        requested.extend(tickers)
        return {
            "NVDA": {"ticker": "NVDA", "sicDescription": "Semiconductors & Related Devices"},
            "VRT": {"ticker": "VRT", "sicDescription": "Electronic Components, NEC"},
        }

    enricher._fetch_sec_metadata_for_tickers = fake_sec_fetch

    metrics = enricher._calculate_leadership_metrics(companies)

    assert requested == ["NVDA", "VRT"]
    assert metrics["NVDA"]["industry_group"] == "Semiconductors & Related Devices"
    assert metrics["VRT"]["industry_group"] == "Electronic Components, NEC"
    assert saved["NVDA"]["sicDescription"] == "Semiconductors & Related Devices"


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

