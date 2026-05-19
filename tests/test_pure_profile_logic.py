"""
Focused tests for profile-based pure CANSLIM logic.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from src.growth_stock_screener import (
    _check_institutional,
    _check_pattern,
    _check_supply_demand,
    _filter_screening_candidates,
)
from src.enrichers.market_data_enricher import MarketDataEnricher
from src.utils.config_loader import load_config_file


class TestPureProfileLogic(unittest.TestCase):
    def test_supply_demand_only_requires_breakout_volume_on_real_breakout(self):
        criteria = {
            "require_supply_demand": True,
            "up_down_volume_ratio_min": 1.0,
            "volume_trend_50_200_min": 0.9,
            "require_breakout_volume_confirmation": True,
            "breakout_volume_ratio_min": 1.3,
        }
        company = {
            "up_down_volume_ratio_50d": 1.2,
            "volume_trend_50_200": 0.95,
            "near_pivot": True,
            "valid_breakout": False,
            "breakout_volume_ratio": 0.6,
        }
        self.assertTrue(_check_supply_demand(company, criteria))

    def test_institutional_support_accepts_ownership_or_holder_count(self):
        criteria = {
            "require_institutional_sponsorship": True,
            "sponsorship_mode": "ownership_or_holders",
            "institutional_ownership_min": 0.05,
            "institutional_ownership_max": 0.95,
            "institutional_holders_min": 3,
        }
        self.assertTrue(_check_institutional({"institutional_ownership": 0.10}, criteria))
        self.assertTrue(_check_institutional({"institutional_holders": 5}, criteria))
        self.assertFalse(_check_institutional({"institutional_ownership": 0.01, "institutional_holders": 1}, criteria))

    def test_institutional_support_accepts_positive_13f_trend(self):
        criteria = {
            "require_institutional_sponsorship": True,
            "sponsorship_mode": "ownership_or_holders_or_trend",
            "institutional_ownership_min": 0.05,
            "institutional_ownership_max": 0.95,
            "institutional_holders_min": 3,
            "institutional_holders_qoq_min": 0,
            "institutional_value_qoq_min": 0,
        }

        self.assertTrue(
            _check_institutional(
                {
                    "institutional_holders_qoq_change": 4,
                    "institutional_value_qoq_change": 0.12,
                },
                criteria,
            )
        )
        self.assertFalse(
            _check_institutional(
                {
                    "institutional_holders_qoq_change": -2,
                    "institutional_value_qoq_change": -0.05,
                },
                criteria,
            )
        )

    def test_institutional_support_accepts_13f_accumulation_score(self):
        criteria = {
            "require_institutional_sponsorship": True,
            "sponsorship_mode": "ownership_or_holders_or_trend",
            "institutional_ownership_min": 0.05,
            "institutional_ownership_max": 0.95,
            "institutional_holders_min": 3,
            "institutional_holders_qoq_min": 0,
            "institutional_value_qoq_min": 0,
            "institutional_accumulation_score_min": 60,
        }

        self.assertTrue(_check_institutional({"institutional_accumulation_score": 75}, criteria))
        self.assertFalse(_check_institutional({"institutional_accumulation_score": 40}, criteria))

    def test_pattern_requires_actionable_setup_not_new_high_alone(self):
        criteria = {
            "require_new_high_or_breakout": True,
            "allow_near_pivot_setup": True,
            "price_vs_52w_high_hard_min": 0.90,
            "breakout_pct_min": -0.02,
        }
        self.assertFalse(_check_pattern({"new_52w_high": True}, criteria))
        self.assertTrue(_check_pattern({"valid_breakout": True}, criteria))
        self.assertTrue(
            _check_pattern(
                {
                    "near_pivot": True,
                    "price_vs_52w_high": 0.95,
                    "breakout_pct": -0.01,
                },
                criteria,
            )
        )
        self.assertFalse(
            _check_pattern(
                {
                    "near_pivot": True,
                    "price_vs_52w_high": 0.82,
                    "breakout_pct": -0.01,
                },
                criteria,
            )
        )

    def test_config_loader_merges_base_and_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "profiles").mkdir()

            (temp_path / "base.json").write_text(
                json.dumps(
                    {
                        "data_paths": {"output_file": "base.csv"},
                        "market_data": {"use_yfinance_info_fallback": False},
                    }
                )
            )
            (temp_path / "profiles" / "pure.json").write_text(
                json.dumps(
                    {
                        "extends": "../base.json",
                        "data_paths": {"output_file": "pure.csv"},
                        "market_data": {"use_yfinance_info_fallback": True},
                    }
                )
            )

            config = load_config_file(str(temp_path / "base.json"), profile="pure")

        self.assertEqual(config["profile_name"], "pure")
        self.assertEqual(config["data_paths"]["output_file"], "pure.csv")
        self.assertTrue(config["market_data"]["use_yfinance_info_fallback"])

    def test_hybrid_supply_demand_checks_near_pivot_volume_and_dry_up(self):
        criteria = {
            "require_supply_demand": True,
            "up_down_volume_ratio_min": 1.1,
            "volume_trend_50_200_min": 0.85,
            "require_breakout_volume_confirmation": True,
            "confirm_volume_for_near_pivot": False,
            "breakout_volume_ratio_min": 1.4,
            "require_volume_dry_up": True,
            "volume_dry_up_ratio_max": 0.95,
        }
        company = {
            "up_down_volume_ratio_50d": 1.3,
            "volume_trend_50_200": 1.05,
            "near_pivot": True,
            "valid_breakout": False,
            "breakout_volume_ratio": 0.9,
            "volume_dry_up_ratio_10_50": 0.7,
        }
        self.assertTrue(_check_supply_demand(company, criteria))
        company["volume_dry_up_ratio_10_50"] = 0.95
        self.assertTrue(_check_supply_demand(company, criteria))
        company["volume_dry_up_ratio_10_50"] = 0.96
        self.assertFalse(_check_supply_demand(company, criteria))
        company["volume_dry_up_ratio_10_50"] = 0.70
        company["valid_breakout"] = True
        self.assertFalse(_check_supply_demand(company, criteria))
        company["breakout_volume_ratio"] = 1.5
        self.assertTrue(_check_supply_demand(company, criteria))

    def test_hybrid_pattern_requires_constructive_setup_or_breakout(self):
        criteria = {
            "require_hybrid_setup": True,
            "price_vs_52w_high_min": 0.85,
            "base_depth_max": 0.35,
            "require_rs_line_near_high_for_setup": True,
            "allow_hybrid_breakout": True,
        }
        self.assertTrue(
            _check_pattern(
                {
                    "near_pivot": True,
                    "price_vs_52w_high": 0.92,
                    "base_depth_65d": 0.22,
                    "rs_line_near_high": True,
                },
                criteria,
            )
        )
        self.assertTrue(
            _check_pattern(
                {
                    "valid_breakout": True,
                    "rs_line_near_high": True,
                },
                criteria,
            )
        )
        self.assertFalse(
            _check_pattern(
                {
                    "near_pivot": True,
                    "price_vs_52w_high": 0.80,
                    "base_depth_65d": 0.22,
                    "rs_line_near_high": True,
                },
                criteria,
            )
        )
        self.assertFalse(
            _check_pattern(
                {
                    "near_pivot": True,
                    "price_vs_52w_high": 0.92,
                    "base_depth_65d": 0.22,
                    "rs_line_near_high": False,
                },
                criteria,
            )
        )

    def test_unknown_market_cap_can_pass_when_liquidity_is_strong(self):
        company = {
            "ticker": "LIQ",
            "name": "Liquid Corp",
            "quarterly_eps_growth": 0.30,
            "annual_eps_cagr": 0.30,
            "revenue_growth": 0.25,
            "profit_margin": 0.10,
            "roe": 0.20,
            "debt_to_equity": 1.0,
            "market_cap": 0,
            "rs_rating": 90,
            "price_vs_52w_high": 0.93,
            "avg_dollar_volume_50d": 50_000_000,
            "market_outperformance_12m": 0.05,
            "up_down_volume_ratio_50d": 1.2,
            "volume_trend_50_200": 1.0,
            "near_pivot": True,
            "breakout_pct": -0.01,
        }

        filtered, counts = _filter_screening_candidates(
            [company],
            {
                "quarterly_eps_growth": 0.25,
                "annual_eps_cagr": 0.25,
                "revenue_growth": 0.20,
                "profit_margin": 0.05,
                "roe": 0.17,
                "debt_to_equity": 2.0,
                "outperform_sp500": True,
                "min_market_cap": 300_000_000,
            },
            {"rs_rating_min": 80, "price_vs_52w_high_min": 0.85, "avg_dollar_volume_min": 15_000_000},
            {"require_supply_demand": True, "up_down_volume_ratio_min": 1.0, "volume_trend_50_200_min": 0.9},
            {"require_institutional_sponsorship": False},
            {"require_new_high_or_breakout": True, "allow_near_pivot_setup": True},
            market_direction_ok=True,
            test_mode=False,
        )

        self.assertEqual([row["ticker"] for row in filtered], ["LIQ"])
        self.assertEqual(counts["mktcap"], 1)

    def test_profile_filter_and_optional_fundamentals_support_special_universes(self):
        ipo_company = {
            "ticker": "IPO",
            "name": "IPO Corp",
            "security_profile": "ipo_spinoff",
            "revenue_growth": 0.30,
            "market_cap": 1_000_000_000,
            "rs_rating": 90,
            "price_vs_52w_high": 0.95,
            "avg_dollar_volume_50d": 40_000_000,
            "market_outperformance_12m": 0.10,
            "up_down_volume_ratio_50d": 1.4,
            "volume_trend_50_200": 1.1,
            "near_pivot": True,
            "breakout_pct": -0.01,
        }
        standard_company = {**ipo_company, "ticker": "STD", "security_profile": "standard"}

        filtered, _ = _filter_screening_candidates(
            [ipo_company, standard_company],
            {
                "include_security_profiles": ["ipo_spinoff"],
                "quarterly_eps_growth": None,
                "annual_eps_cagr": None,
                "revenue_growth": 0.15,
                "profit_margin": None,
                "roe": None,
                "debt_to_equity": None,
                "outperform_sp500": True,
                "min_market_cap": 300_000_000,
            },
            {"rs_rating_min": 80, "price_vs_52w_high_min": 0.85, "avg_dollar_volume_min": 10_000_000},
            {"require_supply_demand": True, "up_down_volume_ratio_min": 1.0, "volume_trend_50_200_min": 0.8},
            {"require_institutional_sponsorship": False},
            {"require_new_high_or_breakout": True, "allow_near_pivot_setup": True},
            market_direction_ok=True,
            test_mode=False,
        )

        self.assertEqual([stock["ticker"] for stock in filtered], ["IPO"])

    def test_summary_counts_base_and_breakout_as_distinct_signals(self):
        company = {
            "ticker": "SETUP",
            "name": "Setup Corp",
            "quarterly_eps_growth": 0.30,
            "annual_eps_cagr": 0.30,
            "revenue_growth": 0.25,
            "profit_margin": 0.10,
            "roe": 0.20,
            "debt_to_equity": 1.0,
            "market_cap": 1_000_000_000,
            "rs_rating": 90,
            "price_vs_52w_high": 0.93,
            "avg_dollar_volume_50d": 50_000_000,
            "market_outperformance_12m": 0.05,
            "rs_line_near_high": True,
            "up_down_volume_ratio_50d": 1.2,
            "volume_trend_50_200": 1.0,
            "near_pivot": True,
            "valid_breakout": False,
            "breakout_pct": -0.01,
            "base_depth_65d": 0.20,
        }

        filtered, counts = _filter_screening_candidates(
            [company],
            {
                "quarterly_eps_growth": 0.25,
                "annual_eps_cagr": 0.25,
                "revenue_growth": 0.20,
                "profit_margin": 0.05,
                "roe": 0.17,
                "debt_to_equity": 2.0,
                "outperform_sp500": True,
                "min_market_cap": 300_000_000,
            },
            {
                "rs_rating_min": 80,
                "price_vs_52w_high_min": 0.85,
                "avg_dollar_volume_min": 15_000_000,
                "rs_line_near_high": True,
            },
            {
                "require_supply_demand": True,
                "up_down_volume_ratio_min": 1.0,
                "volume_trend_50_200_min": 0.9,
            },
            {"require_institutional_sponsorship": False},
            {
                "require_new_high_or_breakout": True,
                "allow_near_pivot_setup": True,
                "price_vs_52w_high_hard_min": 0.90,
                "breakout_pct_min": -0.02,
                "base_depth_max": 0.35,
            },
            market_direction_ok=True,
            test_mode=False,
        )

        self.assertEqual([stock["ticker"] for stock in filtered], ["SETUP"])
        self.assertEqual(counts["new_high"], 1)
        self.assertEqual(counts["base"], 1)
        self.assertEqual(counts["breakout"], 0)

    @patch('src.enrichers.market_data_enricher.requests.get')
    @patch('src.enrichers.market_data_enricher.yf.download')
    def test_price_history_download_falls_back_to_yahoo_chart_api(self, mock_download, mock_get):
        """The live pipeline should still get prices when yfinance download returns empty data."""
        mock_download.return_value = pd.DataFrame()
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "chart": {
                "result": [{
                    "timestamp": [1640995200, 1641081600],
                    "indicators": {"quote": [{
                        "open": [100, 101],
                        "high": [102, 103],
                        "low": [99, 100],
                        "close": [101, 102],
                        "volume": [1000, 1200],
                    }]},
                }],
                "error": None,
            }
        }
        mock_get.return_value = mock_response

        with tempfile.TemporaryDirectory() as temp_dir:
            enricher = MarketDataEnricher(
                {
                    "data_paths": {
                        "processed_data_dir": temp_dir,
                        "raw_data_dir": temp_dir,
                    }
                }
            )
            histories = enricher._download_price_history(["AAPL"], "15mo", chunk_size=25)

        self.assertIn("AAPL", histories)
        self.assertEqual(histories["AAPL"]["Close"].tolist(), [101, 102])

    def test_up_down_volume_ratio_treats_no_down_volume_as_strong_accumulation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            enricher = MarketDataEnricher(
                {
                    "data_paths": {
                        "processed_data_dir": temp_dir,
                        "raw_data_dir": temp_dir,
                    },
                    "pattern_criteria": {},
                }
            )
            history = pd.DataFrame(
                {
                    "Close": range(100, 160),
                    "Volume": [1_000_000] * 60,
                },
                index=pd.date_range("2025-01-01", periods=60, freq="B"),
            )

            metrics = enricher._calculate_single_leadership_metrics(history, None)

        self.assertGreater(metrics["up_down_volume_ratio_50d"], 1.0)
        self.assertTrue(
            _check_supply_demand(
                {**metrics, "volume_trend_50_200": 1.0},
                {
                    "require_supply_demand": True,
                    "up_down_volume_ratio_min": 1.0,
                    "volume_trend_50_200_min": 0.9,
                },
            )
        )

    def test_market_enrich_prioritizes_screenable_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            enricher = MarketDataEnricher(
                {
                    "data_paths": {
                        "processed_data_dir": temp_dir,
                        "raw_data_dir": temp_dir,
                    },
                    "screening_criteria": {
                        "quarterly_eps_growth": 0.25,
                        "annual_eps_cagr": 0.25,
                        "revenue_growth": 0.20,
                        "profit_margin": 0.05,
                        "roe": 0.17,
                        "debt_to_equity": 2.0,
                    },
                    "market_data": {
                        "enrich_only_screenable_candidates": True,
                    },
                }
            )
            companies = [
                {
                    "ticker": "PASS",
                    "quarterly_eps_growth": 0.30,
                    "annual_eps_cagr": 0.30,
                    "revenue_growth": 0.25,
                    "profit_margin": 0.10,
                    "roe": 0.20,
                    "debt_to_equity": 1.0,
                },
                {
                    "ticker": "FAIL",
                    "quarterly_eps_growth": 0.10,
                    "annual_eps_cagr": 0.10,
                    "revenue_growth": 0.10,
                    "profit_margin": 0.02,
                    "roe": 0.05,
                    "debt_to_equity": 3.0,
                },
            ]

            prioritized = enricher._prioritize_market_data_candidates(companies, None)

        self.assertEqual([company["ticker"] for company in prioritized], ["PASS"])

    def test_market_enrich_keeps_full_universe_when_prefilter_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            enricher = MarketDataEnricher(
                {
                    "data_paths": {
                        "processed_data_dir": temp_dir,
                        "raw_data_dir": temp_dir,
                    },
                    "screening_criteria": {
                        "quarterly_eps_growth": 0.25,
                        "annual_eps_cagr": 0.25,
                        "revenue_growth": 0.20,
                        "profit_margin": 0.05,
                        "roe": 0.17,
                        "debt_to_equity": 2.0,
                    },
                    "market_data": {
                        "enrich_only_screenable_candidates": False,
                    },
                }
            )
            companies = [
                {
                    "ticker": "PASS",
                    "quarterly_eps_growth": 0.30,
                    "annual_eps_cagr": 0.30,
                    "revenue_growth": 0.25,
                    "profit_margin": 0.10,
                    "roe": 0.20,
                    "debt_to_equity": 1.0,
                },
                {
                    "ticker": "FAIL",
                    "quarterly_eps_growth": 0.10,
                    "annual_eps_cagr": 0.10,
                    "revenue_growth": 0.10,
                    "profit_margin": 0.02,
                    "roe": 0.05,
                    "debt_to_equity": 3.0,
                },
            ]

            prioritized = enricher._prioritize_market_data_candidates(companies, None)

        self.assertEqual([company["ticker"] for company in prioritized], ["PASS", "FAIL"])


if __name__ == "__main__":
    unittest.main()
