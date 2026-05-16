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
