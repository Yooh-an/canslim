from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.enrichers.fundamental_fallback import enrich_company_fundamentals, enrich_missing_fundamentals


def test_enrich_missing_fundamentals_only_fills_missing_fields():
    df = pd.DataFrame(
        [
            {
                "ticker": "MISS",
                "name": "Missing Corp",
                "quarterly_eps_growth": None,
                "revenue_growth": None,
            },
            {
                "ticker": "FULL",
                "name": "Full Corp",
                "quarterly_eps_growth": 0.40,
                "annual_eps_cagr": 0.30,
                "revenue_growth": 0.25,
                "profit_margin": 0.20,
                "roe": 0.30,
                "debt_to_equity": 0.10,
            },
        ]
    )
    config = {"fundamental_data": {"enabled": True, "provider": "simfin", "only_missing_sec_metrics": True}}

    with patch("src.enrichers.fundamental_fallback.SimFinClient") as client_cls:
        client = client_cls.return_value
        client.has_api_key.return_value = True
        client.get_fundamental_metrics.return_value = {
            "quarterly_eps_growth": 0.20,
            "annual_eps_cagr": 0.15,
            "revenue_growth": 0.30,
            "profit_margin": 0.12,
            "roe": 0.18,
            "debt_to_equity": 0.50,
            "financial_data_source": "simfin",
        }

        enriched = enrich_missing_fundamentals(df, config)

    miss = enriched.loc[enriched["ticker"] == "MISS"].iloc[0]
    full = enriched.loc[enriched["ticker"] == "FULL"].iloc[0]
    assert miss["quarterly_eps_growth"] == pytest.approx(0.20)
    assert miss["financial_data_source"] == "simfin"
    assert full["quarterly_eps_growth"] == pytest.approx(0.40)
    client.get_fundamental_metrics.assert_called_once_with("MISS")


def test_enrich_company_fundamentals_fills_missing_values_only():
    company = {"ticker": "MISS", "quarterly_eps_growth": 0.40, "revenue_growth": None}
    config = {"fundamental_data": {"enabled": True, "provider": "simfin"}}

    with patch("src.enrichers.fundamental_fallback.SimFinClient") as client_cls:
        client = client_cls.return_value
        client.has_api_key.return_value = True
        client.get_fundamental_metrics.return_value = {
            "quarterly_eps_growth": 0.20,
            "revenue_growth": 0.30,
            "financial_data_source": "simfin",
        }

        enriched = enrich_company_fundamentals(company, config)

    assert enriched["quarterly_eps_growth"] == pytest.approx(0.40)
    assert enriched["revenue_growth"] == pytest.approx(0.30)
    assert enriched["financial_data_source"] == "simfin"


def test_enrich_missing_fundamentals_noops_without_key():
    df = pd.DataFrame([{"ticker": "MISS", "quarterly_eps_growth": None}])
    config = {"fundamental_data": {"enabled": True, "provider": "simfin"}}

    with patch("src.enrichers.fundamental_fallback.SimFinClient") as client_cls:
        client_cls.return_value.has_api_key.return_value = False
        enriched = enrich_missing_fundamentals(df, config)

    assert enriched.equals(df)
