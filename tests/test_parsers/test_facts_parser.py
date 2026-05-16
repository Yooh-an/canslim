"""
Unit tests for XBRLFactsParser.
"""

import os
import unittest
import tempfile
import json
import pandas as pd
import numpy as np
from unittest.mock import patch, Mock, MagicMock
import shutil
import sys

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import XBRLFactsParser from src.parsers.facts_parser
from src.parsers.facts_parser import XBRLFactsParser

class TestXBRLFactsParser(unittest.TestCase):
    """Test cases for the XBRLFactsParser class."""
    
    def setUp(self):
        """Set up test environment."""
        # Create a temp directory for tests
        self.temp_dir = tempfile.mkdtemp()
        
        # Create config with temp paths
        self.config = {
            "data_paths": {
                "raw_data_dir": os.path.join(self.temp_dir, "raw"),
                "processed_data_dir": os.path.join(self.temp_dir, "processed"),
                "company_facts_dir": os.path.join(self.temp_dir, "raw/company_facts"),
            }
        }
        
        # Create parser
        self.parser = XBRLFactsParser(self.config)
        
        # Create directory structure
        os.makedirs(self.config["data_paths"]["raw_data_dir"], exist_ok=True)
        os.makedirs(self.config["data_paths"]["processed_data_dir"], exist_ok=True)
        os.makedirs(self.config["data_paths"]["company_facts_dir"], exist_ok=True)
    
    def tearDown(self):
        """Clean up after tests."""
        shutil.rmtree(self.temp_dir)
    
    def test_initialization(self):
        """Test that parser initializes with correct parameters."""
        print("Running facts parser test_initialization")
        self.assertEqual(self.parser.raw_data_dir, os.path.join(self.temp_dir, "raw"))
        self.assertEqual(self.parser.processed_data_dir, os.path.join(self.temp_dir, "processed"))
        self.assertTrue(os.path.isdir(self.parser.processed_data_dir), "Processed directory should be created")

    def test_empty_result_when_no_files(self):
        """Test that an empty DataFrame is returned when no files exist."""
        print("Running facts parser test_empty_result_when_no_files")
        result = self.parser.process_all()
        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue(result.empty)

    def test_load_company_facts(self):
        """Test loading company facts from a file."""
        print("Running facts parser test_load_company_facts")
        # Create a test facts file
        test_data = {
            "cik": "0000123456",
            "entityName": "Test Company",
            "tickers": ["TEST"]
        }
        
        file_path = os.path.join(self.config["data_paths"]["company_facts_dir"], "CIK0000123456.json")
        with open(file_path, 'w') as f:
            json.dump(test_data, f)
        
        # Load the facts
        facts = self.parser.load_company_facts(file_path)
        
        # Verify
        self.assertEqual(facts["cik"], "0000123456")
        self.assertEqual(facts["entityName"], "Test Company")
        self.assertEqual(facts["tickers"], ["TEST"])

    def test_quarterly_flow_uses_fact_period_year_for_derived_q4(self):
        """Historical annual facts from newer filings should not create fake latest-year Q4 values."""
        concept_data = {
            "units": {
                "USD": [
                    {"form": "10-Q", "fy": 2023, "fp": "Q1", "start": "2023-01-01", "end": "2023-03-31", "filed": "2023-05-01", "val": 10},
                    {"form": "10-Q", "fy": 2023, "fp": "Q2", "start": "2023-04-01", "end": "2023-06-30", "filed": "2023-08-01", "val": 20},
                    {"form": "10-Q", "fy": 2023, "fp": "Q3", "start": "2023-07-01", "end": "2023-09-30", "filed": "2023-11-01", "val": 30},
                    {"form": "10-K", "fy": 2025, "fp": "FY", "start": "2023-01-01", "end": "2023-12-31", "filed": "2026-02-01", "val": 100},
                ]
            }
        }

        series = self.parser._quarterly_flow_series(concept_data, ["USD"])
        values = {item["period_key"]: item["val"] for item in series}

        self.assertEqual(values["2023Q4"], 40)
        self.assertNotIn("2025Q4", values)

    def test_quarterly_flow_uses_fiscal_year_for_non_calendar_year_companies(self):
        """Fiscal years ending in January should group Q1-Q4 under SEC fy, not calendar year."""
        concept_data = {
            "units": {
                "USD": [
                    {"form": "10-Q", "fy": 2026, "fp": "Q1", "start": "2025-01-27", "end": "2025-04-27", "filed": "2025-05-28", "val": 10},
                    {"form": "10-Q", "fy": 2026, "fp": "Q2", "start": "2025-04-28", "end": "2025-07-27", "filed": "2025-08-27", "val": 20},
                    {"form": "10-Q", "fy": 2026, "fp": "Q3", "start": "2025-07-28", "end": "2025-10-26", "filed": "2025-11-19", "val": 30},
                    {"form": "10-K", "fy": 2026, "fp": "FY", "start": "2025-01-27", "end": "2026-01-25", "filed": "2026-02-25", "val": 100},
                ]
            }
        }

        series = self.parser._quarterly_flow_series(concept_data, ["USD"])
        values = {item["period_key"]: item["val"] for item in series}

        self.assertEqual(values["2026Q4"], 40)
        self.assertNotIn("2025Q4", values)

    def test_profit_margin_uses_quarterly_income_not_ytd_income(self):
        """Profit margin should compare quarterly revenue with quarterly net income."""
        us_gaap_facts = {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {
                    "USD": [
                        {"form": "10-Q", "fy": 2025, "fp": "Q2", "start": "2025-04-01", "end": "2025-06-30", "filed": "2025-08-01", "val": 200},
                    ]
                }
            },
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {"form": "10-Q", "fy": 2025, "fp": "Q2", "start": "2025-01-01", "end": "2025-06-30", "filed": "2025-08-01", "val": 50},
                        {"form": "10-Q", "fy": 2025, "fp": "Q2", "start": "2025-04-01", "end": "2025-06-30", "filed": "2025-08-01", "val": 20},
                    ]
                }
            },
        }
        metrics = {}

        self.parser._extract_revenue_metrics(us_gaap_facts, metrics)
        self.parser._extract_income_metrics(us_gaap_facts, metrics)
        self.parser._calculate_derived_metrics(metrics)

        self.assertAlmostEqual(metrics["profit_margin"], 0.10)

    def test_revenue_extraction_prefers_newest_available_tag(self):
        """A stale high-priority revenue tag should not override a newer revenue tag."""
        us_gaap_facts = {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {
                    "USD": [
                        {"form": "10-Q", "fy": 2017, "fp": "Q1", "start": "2017-01-01", "end": "2017-03-31", "filed": "2017-05-01", "val": 100},
                        {"form": "10-Q", "fy": 2018, "fp": "Q1", "start": "2018-01-01", "end": "2018-03-31", "filed": "2018-05-01", "val": 150},
                    ]
                }
            },
            "Revenues": {
                "units": {
                    "USD": [
                        {"form": "10-Q", "fy": 2025, "fp": "Q1", "start": "2025-01-01", "end": "2025-03-31", "filed": "2025-05-01", "val": 200},
                        {"form": "10-Q", "fy": 2026, "fp": "Q1", "start": "2026-01-01", "end": "2026-03-31", "filed": "2026-05-01", "val": 260},
                    ]
                }
            },
        }
        metrics = {}

        self.parser._extract_revenue_metrics(us_gaap_facts, metrics)

        self.assertEqual(metrics["revenue_period"], "2026Q1")
        self.assertAlmostEqual(metrics["revenue_growth"], 0.30)

    def test_revenue_extraction_skips_stale_concept_data(self):
        """Stale revenue facts should not be mixed with current EPS or balance-sheet data."""
        us_gaap_facts = {
            "Revenues": {
                "units": {
                    "USD": [
                        {"form": "10-Q", "fy": 2016, "fp": "Q4", "start": "2016-10-01", "end": "2016-12-31", "filed": "2017-02-01", "val": 100},
                        {"form": "10-Q", "fy": 2017, "fp": "Q4", "start": "2017-10-01", "end": "2017-12-31", "filed": "2018-02-01", "val": 200},
                    ]
                }
            }
        }
        metrics = {"_latest_fact_end": pd.Timestamp("2026-03-31")}

        self.parser._extract_revenue_metrics(us_gaap_facts, metrics)

        self.assertNotIn("revenue_growth", metrics)

    def test_debt_to_equity_uses_debt_not_total_liabilities_and_latest_quarter(self):
        """Debt-to-equity should use debt tags and the newest 10-Q/10-K balance sheet values."""
        us_gaap_facts = {
            "Liabilities": {
                "units": {
                    "USD": [
                        {"form": "10-Q", "fy": 2025, "fp": "Q1", "end": "2025-03-31", "filed": "2025-05-01", "val": 900},
                    ]
                }
            },
            "LongTermDebtCurrent": {
                "units": {
                    "USD": [
                        {"form": "10-Q", "fy": 2025, "fp": "Q1", "end": "2025-03-31", "filed": "2025-05-01", "val": 100},
                    ]
                }
            },
            "LongTermDebtNoncurrent": {
                "units": {
                    "USD": [
                        {"form": "10-Q", "fy": 2025, "fp": "Q1", "end": "2025-03-31", "filed": "2025-05-01", "val": 200},
                    ]
                }
            },
            "StockholdersEquity": {
                "units": {
                    "USD": [
                        {"form": "10-K", "fy": 2024, "fp": "FY", "end": "2024-12-31", "filed": "2025-02-15", "val": 500},
                        {"form": "10-Q", "fy": 2025, "fp": "Q1", "end": "2025-03-31", "filed": "2025-05-01", "val": 600},
                    ]
                }
            },
        }
        metrics = {}

        self.parser._extract_balance_sheet_metrics(us_gaap_facts, metrics)
        self.parser._calculate_derived_metrics(metrics)

        self.assertEqual(metrics["liabilities"], 900)
        self.assertEqual(metrics["debt"], 300)
        self.assertEqual(metrics["equity"], 600)
        self.assertAlmostEqual(metrics["debt_to_equity"], 0.5)


if __name__ == '__main__':
    unittest.main()
