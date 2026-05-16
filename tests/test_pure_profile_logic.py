"""
Focused tests for profile-based pure CANSLIM logic.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.growth_stock_screener import (
    _check_institutional,
    _check_pattern,
    _check_supply_demand,
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

    def test_pattern_requires_real_new_high_or_breakout_signal(self):
        criteria = {
            "require_new_high_or_breakout": True,
            "allow_near_pivot_setup": True,
            "price_vs_52w_high_hard_min": 0.90,
            "breakout_pct_min": -0.02,
        }
        self.assertTrue(_check_pattern({"new_52w_high": True}, criteria))
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
