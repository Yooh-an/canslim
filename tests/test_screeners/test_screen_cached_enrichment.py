from unittest.mock import patch

from src.growth_stock_screener import _hydrate_cached_enrichment


def test_hydrate_cached_enrichment_applies_market_cache_and_local_13f():
    companies = [{"ticker": "FIX", "name": "Comfort"}]
    config = {"institutional_data": {"enabled": True}, "insider_data": {"enabled": False}}

    with patch("src.growth_stock_screener.MarketDataEnricher") as enricher_cls, patch(
        "src.growth_stock_screener.enrich_companies_with_13f_data"
    ) as enrich_13f:
        enricher = enricher_cls.return_value
        enricher.market_data_dir = "market-cache"
        enricher._normalize_yahoo_ticker.side_effect = lambda ticker: ticker
        enricher._load_market_data_files.return_value = {
            "FIX": {"ticker": "FIX", "rs_rating": 95.2, "institutional_ownership": 0.96}
        }
        enrich_13f.return_value = [
            {
                "ticker": "FIX",
                "name": "Comfort",
                "rs_rating": 95.2,
                "institutional_ownership": 0.96,
                "institutional_holders": 7,
                "institutional_data_source": "sec_13f",
            }
        ]

        hydrated = _hydrate_cached_enrichment(companies, config)

    assert hydrated[0]["rs_rating"] == 95.2
    assert hydrated[0]["institutional_ownership"] == 0.96
    assert hydrated[0]["institutional_holders"] == 7
    assert hydrated[0]["institutional_data_source"] == "sec_13f"
    enrich_13f.assert_called_once()
