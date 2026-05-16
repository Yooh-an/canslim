"""
Unit tests for StockScreener.
"""

import os
import unittest
import tempfile
import pandas as pd
import numpy as np
from unittest.mock import patch, Mock, MagicMock
import shutil

from src.screeners.stock_screener import StockScreener

class TestStockScreener(unittest.TestCase):
    """Test cases for the StockScreener class."""
    
    def setUp(self):
        """Set up test environment."""
        # Create a temp directory for tests
        self.temp_dir = tempfile.mkdtemp()
        
        # Create config with temp paths
        self.config = {
            "data_paths": {
                "processed_data_dir": os.path.join(self.temp_dir, "processed"),
                "output_file": os.path.join(self.temp_dir, "processed", "results.csv"),
            },
            "screening_criteria": {
                "quarterly_eps_growth": 0.25,
                "annual_eps_cagr": 0.20,
                "revenue_growth": 0.15,
                "profit_margin": 0.10,
                "roe": 0.15,
                "debt_to_equity": 1.0,
                "min_market_cap": 100000000
            }
        }
        
        # Create directory structure
        os.makedirs(os.path.join(self.temp_dir, "processed"), exist_ok=True)
        
        # Create mock data
        self.create_test_data()
    
    def tearDown(self):
        """Clean up after tests."""
        shutil.rmtree(self.temp_dir)
    
    def create_test_data(self):
        """Create test financial metrics data."""
        # Create a simple dataframe with mock metrics
        data = {
            'ticker': ['aapl', 'msft', 'googl', 'amzn', 'fb'],
            'name': ['Apple Inc.', 'Microsoft Corp.', 'Alphabet Inc.', 'Amazon.com Inc.', 'Meta Platforms Inc.'],
            'eps_qtr_growth': [0.30, 0.22, 0.28, 0.15, 0.05],
            'eps_3yr_cagr': [0.25, 0.18, 0.22, 0.30, 0.10],
            'revenue_qtr_growth': [0.20, 0.18, 0.25, 0.10, 0.05],
            'profit_margin': [0.25, 0.30, 0.20, 0.05, 0.15],
            'roe': [0.40, 0.35, 0.25, 0.20, 0.10],
            'debt_to_equity': [0.5, 0.8, 0.3, 1.2, 0.9],
            'market_cap': [2500000000000, 2000000000000, 1500000000000, 1200000000000, 500000000000],
            'exchange': ['NASDAQ', 'NASDAQ', 'NASDAQ', 'NASDAQ', 'NASDAQ'],
            'has_complete_data': [True, True, True, True, False]
        }
        
        # Create dataframe
        df = pd.DataFrame(data)
        
        # Save to parquet
        metrics_file = os.path.join(self.temp_dir, "processed", "financial_metrics.parquet")
        df.to_parquet(metrics_file)
        
        # Also save company index
        company_file = os.path.join(self.temp_dir, "processed", "companies_index.parquet")
        df[['ticker', 'name', 'market_cap', 'exchange']].to_parquet(company_file)
        
        # Store paths
        self.metrics_file = metrics_file
        self.company_file = company_file
    
    @patch('pandas.read_parquet')
    def test_load_data(self, mock_read_parquet):
        """Test load_data."""
        # Create test dataframe
        metrics_df = pd.DataFrame({
            'ticker': ['aapl', 'msft'],
            'eps_qtr_growth': [0.3, 0.2]
        })
        
        companies_df = pd.DataFrame({
            'ticker': ['aapl', 'msft'],
            'market_cap': [2000000000000, 1800000000000],
            'exchange': ['NASDAQ', 'NASDAQ']
        })
        
        # Configure mock to return our dataframes
        mock_read_parquet.side_effect = [metrics_df, companies_df]
        
        # Create StockScreener with patched pandas
        screener = StockScreener(self.config)
        
        # Check that dataframes were loaded
        mock_read_parquet.assert_called()
        self.assertEqual(mock_read_parquet.call_count, 2)
        
        # Check dataframes
        pd.testing.assert_frame_equal(screener.metrics_df, metrics_df.merge(
            companies_df[['ticker', 'market_cap', 'exchange']], on='ticker', how='left'
        ))
    
    def test_initialization_with_real_files(self):
        """Test initialization with real files."""
        # Create StockScreener using real files
        screener = StockScreener({
            "data_paths": {
                "processed_data_dir": os.path.join(self.temp_dir, "processed"),
                "output_file": os.path.join(self.temp_dir, "processed", "results.csv"),
            },
            "screening_criteria": {}
        })
        
        # Check loaded dataframes
        self.assertEqual(len(screener.metrics_df), 5)
        self.assertIn('ticker', screener.metrics_df.columns)
        self.assertIn('eps_qtr_growth', screener.metrics_df.columns)
        
        self.assertEqual(len(screener.companies_df), 5)
        self.assertIn('ticker', screener.companies_df.columns)
        self.assertIn('market_cap', screener.companies_df.columns)
    
    def test_apply_eps_filter(self):
        """Test apply_eps_filter."""
        # Create screener
        screener = StockScreener({
            "data_paths": {
                "processed_data_dir": os.path.join(self.temp_dir, "processed"),
                "output_file": os.path.join(self.temp_dir, "processed", "results.csv"),
            },
            "screening_criteria": {
                "quarterly_eps_growth": 0.25
            }
        })
        
        # Apply filter
        filtered_df = screener.apply_eps_filter(screener.metrics_df)
        
        # Should have kept only companies with eps_qtr_growth >= 0.25
        self.assertEqual(len(filtered_df), 2)  # aapl, googl
        self.assertTrue(all(filtered_df['eps_qtr_growth'] >= 0.25))
    
    def test_apply_revenue_filter(self):
        """Test apply_revenue_filter."""
        # Create screener
        screener = StockScreener({
            "data_paths": {
                "processed_data_dir": os.path.join(self.temp_dir, "processed"),
                "output_file": os.path.join(self.temp_dir, "processed", "results.csv"),
            },
            "screening_criteria": {
                "revenue_growth": 0.20
            }
        })
        
        # Apply filter
        filtered_df = screener.apply_revenue_filter(screener.metrics_df)
        
        # Should have kept only companies with revenue_qtr_growth >= 0.20
        self.assertEqual(len(filtered_df), 2)  # aapl, googl
        self.assertTrue(all(filtered_df['revenue_qtr_growth'] >= 0.20))
    
    def test_apply_all_filters(self):
        """Test apply_all_filters."""
        # Create screener with all filters
        screener = StockScreener(self.config)
        
        # Apply all filters
        filtered_df = screener.apply_all_filters()
        
        # Only aapl and googl should pass all filters
        self.assertEqual(len(filtered_df), 2)
        tickers = filtered_df['ticker'].tolist()
        self.assertIn('aapl', tickers)
        self.assertIn('googl', tickers)
        
        # Check individual filters
        self.assertTrue(all(filtered_df['eps_qtr_growth'] >= 0.25))
        self.assertTrue(all(filtered_df['revenue_qtr_growth'] >= 0.15))
        self.assertTrue(all(filtered_df['profit_margin'] >= 0.10))
        self.assertTrue(all(filtered_df['roe'] >= 0.15))
        self.assertTrue(all(filtered_df['debt_to_equity'] <= 1.0))
        self.assertTrue(all(filtered_df['has_complete_data'] == True))

    def test_apply_all_filters_fails_closed_when_outperformance_missing(self):
        """Required S&P outperformance should not be skipped when the metric column is absent."""
        screener = StockScreener({
            "data_paths": {
                "processed_data_dir": os.path.join(self.temp_dir, "processed"),
                "output_file": os.path.join(self.temp_dir, "processed", "results.csv"),
            },
            "screening_criteria": {
                "outperform_sp500": True,
            }
        })
        df = pd.DataFrame({"ticker": ["aapl", "msft"]})

        filtered_df = screener.apply_all_filters(df)

        self.assertTrue(filtered_df.empty)


if __name__ == '__main__':
    unittest.main()
