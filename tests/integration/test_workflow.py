"""
Integration tests for the complete workflow of the Growth Stock Screener.
"""

import os
import unittest
import tempfile
import shutil
import json
import pandas as pd
from unittest.mock import patch, Mock, MagicMock
import sys
from pathlib import Path

# Add project root to path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.api.sec_client import SECClient
from src.collectors.submissions_collector import SubmissionsCollector
from src.collectors.facts_collector import CompanyFactsCollector
from src.parsers.submissions_parser import SubmissionsParser
from src.parsers.facts_parser import XBRLFactsParser
from src.screeners.stock_screener import StockScreener
from src.screeners.price_screener import PriceScreener
from src.formatters.results_formatter import ResultsFormatter

class TestEndToEndWorkflow(unittest.TestCase):
    """Integration test for the complete workflow."""
    
    def setUp(self):
        """Set up test environment with sample data."""
        # Create a temp directory for tests
        self.temp_dir = tempfile.mkdtemp()
        
        # Create directory structure
        for dir_name in ["raw", "raw/company_facts", "processed", "logs"]:
            os.makedirs(os.path.join(self.temp_dir, dir_name), exist_ok=True)
        
        # Create configuration
        self.config = {
            "sec_api": {
                "user_agent": "Test User (test@example.com)",
                "rate_limit_delay": 0.01  # Fast for tests
            },
            "data_paths": {
                "raw_data_dir": os.path.join(self.temp_dir, "raw"),
                "processed_data_dir": os.path.join(self.temp_dir, "processed"),
                "submissions_file": os.path.join(self.temp_dir, "raw/submissions.zip"),
                "company_facts_dir": os.path.join(self.temp_dir, "raw/company_facts"),
                "output_file": os.path.join(self.temp_dir, "processed/results.csv")
            },
            "download_settings": {
                "max_workers": 2,
                "max_retries": 1,
                "retry_delay": 1,
                "max_file_age_days": 30
            },
            "screening_criteria": {
                "quarterly_eps_growth": 0.20,
                "annual_eps_cagr": 0.15,
                "revenue_growth": 0.10,
                "profit_margin": 0.05,
                "roe": 0.10,
                "debt_to_equity": 1.5,
                "min_market_cap": 50000000,
                "outperform_sp500": True
            },
            "logging": {
                "level": "INFO",
                "log_file": os.path.join(self.temp_dir, "logs/test.log")
            }
        }
        
        # Create sample data
        self.create_sample_data()
    
    def tearDown(self):
        """Clean up after tests."""
        shutil.rmtree(self.temp_dir)
    
    def create_sample_data(self):
        """Create sample data for testing."""
        # Sample company submissions data
        companies_data = {
            "0000320193": {  # Apple
                "name": "Apple Inc.",
                "tickers": ["AAPL"],
                "exchanges": ["NASDAQ"],
                "sic": "3571",
                "category": "Technology",
                "marketCap": 2500000000000
            },
            "0000789019": {  # Microsoft
                "name": "Microsoft Corporation",
                "tickers": ["MSFT"],
                "exchanges": ["NASDAQ"],
                "sic": "7372",
                "category": "Technology",
                "marketCap": 2000000000000
            },
            "0001652044": {  # Alphabet
                "name": "Alphabet Inc.",
                "tickers": ["GOOGL", "GOOG"],
                "exchanges": ["NASDAQ"],
                "sic": "7370",
                "category": "Technology",
                "marketCap": 1500000000000
            }
        }
        
        # Create sample submissions files structure
        os.makedirs(os.path.join(self.temp_dir, "raw/submissions_extracted"), exist_ok=True)
        with open(os.path.join(self.temp_dir, "raw/submissions_extracted/companies.json"), 'w') as f:
            json.dump(companies_data, f)
        
        # Create sample company facts files
        self.create_sample_company_facts("0000320193", "Apple Inc.", "AAPL", high_growth=True)  # Apple (passes filters)
        self.create_sample_company_facts("0000789019", "Microsoft Corporation", "MSFT", high_growth=False)  # Microsoft (fails filters)
        self.create_sample_company_facts("0001652044", "Alphabet Inc.", "GOOGL", high_growth=True)  # Alphabet (passes filters)
        
        # Create a sample companies index
        companies_df = pd.DataFrame([
            {
                "cik": "320193",
                "cik_padded": "0000320193",
                "ticker": "aapl", 
                "name": "Apple Inc.",
                "market_cap": 2500000000000,
                "exchange": "NASDAQ",
                "sic": "3571",
                "industry": "Technology"
            },
            {
                "cik": "789019",
                "cik_padded": "0000789019",
                "ticker": "msft", 
                "name": "Microsoft Corporation",
                "market_cap": 2000000000000,
                "exchange": "NASDAQ",
                "sic": "7372",
                "industry": "Technology"
            },
            {
                "cik": "1652044",
                "cik_padded": "0001652044",
                "ticker": "googl", 
                "name": "Alphabet Inc.",
                "market_cap": 1500000000000,
                "exchange": "NASDAQ",
                "sic": "7370",
                "industry": "Technology"
            }
        ])
        companies_df.to_parquet(os.path.join(self.temp_dir, "processed/companies_index.parquet"))
    
    def create_sample_company_facts(self, cik: str, company_name: str, ticker: str, high_growth: bool):
        """Create a sample company facts file."""
        # Different growth values based on whether this company should pass filters
        eps_growth = 0.30 if high_growth else 0.15
        revenue_growth = 0.20 if high_growth else 0.05
        
        # Create sample EPS data
        current_eps = 3.0
        last_year_eps = current_eps / (1 + eps_growth)
        
        # Create sample revenue data
        current_revenue = 100000000
        last_year_revenue = current_revenue / (1 + revenue_growth)
        
        # Create sample net income data (20% of revenue for high growth, 10% for low growth)
        profit_margin = 0.20 if high_growth else 0.08
        current_net_income = current_revenue * profit_margin
        
        # Create sample balance sheet data
        equity = 500000000
        liabilities = 300000000 if high_growth else 800000000  # Lower debt-to-equity for high growth
        
        # Create company facts structure
        facts_data = {
            "cik": cik,
            "entityName": company_name,
            "tickers": [ticker],
            "facts": {
                "us-gaap": {
                    "EarningsPerShareDiluted": {
                        "units": {
                            "USD/shares": [
                                # Quarterly data (most recent quarter)
                                {
                                    "form": "10-Q",
                                    "val": current_eps / 4,  # Quarterly EPS
                                    "period": {
                                        "startDate": "2023-01-01",
                                        "endDate": "2023-03-31"
                                    }
                                },
                                # Previous quarter
                                {
                                    "form": "10-Q",
                                    "val": current_eps / 4 * 0.95,  # Slightly lower
                                    "period": {
                                        "startDate": "2022-10-01",
                                        "endDate": "2022-12-31"
                                    }
                                },
                                # Year ago quarter
                                {
                                    "form": "10-Q",
                                    "val": last_year_eps / 4,  # Year-ago quarterly EPS
                                    "period": {
                                        "startDate": "2022-01-01",
                                        "endDate": "2022-03-31"
                                    }
                                },
                                # Annual data (most recent year)
                                {
                                    "form": "10-K",
                                    "val": current_eps,  # Annual EPS
                                    "period": {
                                        "startDate": "2022-01-01",
                                        "endDate": "2022-12-31"
                                    }
                                },
                                # Previous year
                                {
                                    "form": "10-K",
                                    "val": last_year_eps,  # Previous year EPS
                                    "period": {
                                        "startDate": "2021-01-01",
                                        "endDate": "2021-12-31"
                                    }
                                }
                            ]
                        }
                    },
                    "Revenue": {
                        "units": {
                            "USD": [
                                # Quarterly data (most recent quarter)
                                {
                                    "form": "10-Q",
                                    "val": current_revenue / 4,
                                    "period": {
                                        "startDate": "2023-01-01",
                                        "endDate": "2023-03-31"
                                    }
                                },
                                # Year ago quarter
                                {
                                    "form": "10-Q",
                                    "val": last_year_revenue / 4,
                                    "period": {
                                        "startDate": "2022-01-01",
                                        "endDate": "2022-03-31"
                                    }
                                },
                                # Annual data
                                {
                                    "form": "10-K",
                                    "val": current_revenue,
                                    "period": {
                                        "startDate": "2022-01-01",
                                        "endDate": "2022-12-31"
                                    }
                                }
                            ]
                        }
                    },
                    "NetIncomeLoss": {
                        "units": {
                            "USD": [
                                # Quarterly data (most recent quarter)
                                {
                                    "form": "10-Q",
                                    "val": current_net_income / 4,
                                    "period": {
                                        "startDate": "2023-01-01",
                                        "endDate": "2023-03-31"
                                    }
                                },
                                # Annual data
                                {
                                    "form": "10-K",
                                    "val": current_net_income,
                                    "period": {
                                        "startDate": "2022-01-01",
                                        "endDate": "2022-12-31"
                                    }
                                }
                            ]
                        }
                    },
                    "StockholdersEquity": {
                        "units": {
                            "USD": [
                                # Annual data
                                {
                                    "form": "10-K",
                                    "val": equity,
                                    "period": {
                                        "startDate": "2022-01-01",
                                        "endDate": "2022-12-31"
                                    }
                                }
                            ]
                        }
                    },
                    "Liabilities": {
                        "units": {
                            "USD": [
                                # Annual data
                                {
                                    "form": "10-K",
                                    "val": liabilities,
                                    "period": {
                                        "startDate": "2022-01-01",
                                        "endDate": "2022-12-31"
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        }
        
        # Save to file
        with open(os.path.join(self.temp_dir, f"raw/company_facts/CIK{cik}.json"), 'w') as f:
            json.dump(facts_data, f)
    
    @patch('src.screeners.price_screener.yf.download')
    def test_end_to_end_workflow(self, mock_yf_download):
        """Test the complete workflow."""
        # Mock yfinance download to return sample price data
        mock_market_data = pd.DataFrame({
            'Close': [4000, 4200]  # 5% market return
        }, index=pd.date_range(start='2023-01-01', end='2023-07-01', periods=2))
        
        mock_stock_data = pd.DataFrame({
            ('AAPL', 'Close'): [150, 180],  # 20% return
            ('MSFT', 'Close'): [280, 308],  # 10% return
            ('GOOGL', 'Close'): [100, 130]  # 30% return
        }, index=pd.date_range(start='2023-01-01', end='2023-07-01', periods=2))
        
        # Configure mock to return different data based on input
        def mock_download_side_effect(*args, **kwargs):
            if args[0] == '^GSPC':
                return mock_market_data
            else:
                return mock_stock_data
        
        mock_yf_download.side_effect = mock_download_side_effect
        
        # 1. Parse submissions data
        submissions_parser = SubmissionsParser(self.config)
        company_df = submissions_parser.process_submissions(force=True)
        self.assertEqual(len(company_df), 3)
        
        # 2. Parse company facts
        facts_parser = XBRLFactsParser(self.config)
        metrics_df = facts_parser.process_all(force=True)
        
        # 3. Apply financial filters
        stock_screener = StockScreener(self.config)
        filtered_df = stock_screener.apply_all_filters()
        
        # Check that at least some companies made it past financial filters
        self.assertGreater(len(filtered_df), 0)
        
        # 4. Apply price filters
        price_screener = PriceScreener(self.config)
        with_prices_df = price_screener.add_price_performance(filtered_df)
        price_filtered_df = price_screener.apply_outperformance_filter(with_prices_df)
        
        # 5. Format and export results
        formatter = ResultsFormatter(self.config)
        output_path = formatter.create_report(price_filtered_df)
        
        # 6. Validate the output file exists
        self.assertTrue(os.path.exists(output_path))
        
        # 7. Load the output file and check it has the expected companies
        results_df = pd.read_csv(output_path)
        
        # Only AAPL and GOOGL should pass all filters (high growth + outperform market)
        self.assertEqual(len(results_df), 2)
        tickers = [ticker.lower() for ticker in results_df['ticker'].tolist()]
        self.assertIn('aapl', tickers)
        self.assertIn('googl', tickers)
        self.assertNotIn('msft', tickers)  # Should be filtered out due to low growth


if __name__ == '__main__':
    unittest.main()
