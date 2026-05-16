"""
Unit tests for PriceScreener.
"""

import os
import unittest
import pandas as pd
import numpy as np
from unittest.mock import patch, Mock, MagicMock
import datetime

from src.screeners.price_screener import PriceScreener

class TestPriceScreener(unittest.TestCase):
    """Test cases for the PriceScreener class."""
    
    def setUp(self):
        """Set up test environment."""
        # Create config
        self.config = {
            "screening_criteria": {
                "market_index": "^GSPC",  # S&P 500
                "price_months_lookback": 6,
                "outperform_sp500": True
            }
        }
        
        # Create mock test data
        self.test_df = pd.DataFrame({
            'ticker': ['aapl', 'msft', 'googl', 'amzn'],
            'name': ['Apple Inc.', 'Microsoft Corp.', 'Alphabet Inc.', 'Amazon.com Inc.']
        })
    
    @patch('src.screeners.price_screener.yf.download')
    def test_get_market_performance(self, mock_download):
        """Test get_market_performance."""
        # Create mock market data
        market_data = pd.DataFrame({
            'Close': [3500, 3600, 3700, 3800, 4000, 4200]
        }, index=pd.date_range(start='2022-01-01', periods=6, freq='M'))
        
        # Configure mock
        mock_download.return_value = market_data
        
        # Create price screener
        screener = PriceScreener(self.config)
        
        # Get market performance
        performance = screener.get_market_performance()
        
        # Check result (4200 / 3500 - 1 = 0.2)
        self.assertAlmostEqual(performance, 0.2)
        
        # Check that download was called correctly
        mock_download.assert_called_once()
        args, kwargs = mock_download.call_args
        self.assertEqual(args[0], "^GSPC")
        self.assertEqual(kwargs["progress"], False)
    
    @patch('src.screeners.price_screener.requests.get')
    @patch('src.screeners.price_screener.yf.download')
    def test_get_market_performance_falls_back_to_yahoo_chart(self, mock_download, mock_get):
        """If yfinance returns empty data, use Yahoo Chart API directly."""
        mock_download.return_value = pd.DataFrame()
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "chart": {
                "result": [{
                    "timestamp": [1640995200, 1643673600],
                    "indicators": {"quote": [{
                        "open": [100, 120],
                        "high": [100, 120],
                        "low": [100, 120],
                        "close": [100, 120],
                        "volume": [1000, 1000],
                    }]},
                }],
                "error": None,
            }
        }
        mock_get.return_value = mock_response

        screener = PriceScreener(self.config)

        self.assertAlmostEqual(screener.get_market_performance(), 0.2)
        mock_get.assert_called_once()

    @patch('src.screeners.price_screener.requests.get')
    @patch('src.screeners.price_screener.yf.download')
    def test_get_market_performance_returns_nan_when_market_data_missing(self, mock_download, mock_get):
        """Missing benchmark data should not be treated as 0% market return."""
        mock_download.return_value = pd.DataFrame()
        mock_get.side_effect = RuntimeError("chart unavailable")

        screener = PriceScreener(self.config)

        self.assertTrue(np.isnan(screener.get_market_performance()))

    @patch('src.screeners.price_screener.yf.download')
    def test_get_stock_prices(self, mock_download):
        """Test get_stock_prices."""
        # Create mock stock data for multiple tickers
        stock_data = pd.DataFrame({
            ('AAPL', 'Close'): [150, 155, 160, 165, 170, 180],
            ('MSFT', 'Close'): [250, 260, 270, 280, 290, 300]
        }, index=pd.date_range(start='2022-01-01', periods=6, freq='M'))
        
        # Configure mock
        mock_download.return_value = stock_data
        
        # Create price screener
        screener = PriceScreener(self.config)
        
        # Get stock prices
        result = screener.get_stock_prices(['aapl', 'msft'])
        
        # Check result
        self.assertEqual(len(result), 2)
        
        # Check first row (AAPL)
        aapl_row = result[result['ticker'] == 'aapl'].iloc[0]
        self.assertAlmostEqual(aapl_row['price_performance'], 0.2)  # 180 / 150 - 1 = 0.2
        
        # Check second row (MSFT)
        msft_row = result[result['ticker'] == 'msft'].iloc[0]
        self.assertAlmostEqual(msft_row['price_performance'], 0.2)  # 300 / 250 - 1 = 0.2
    
    @patch.object(PriceScreener, 'get_market_performance')
    @patch.object(PriceScreener, 'get_stock_prices')
    def test_add_price_performance(self, mock_get_prices, mock_get_market):
        """Test add_price_performance."""
        # Setup mocks
        mock_get_market.return_value = 0.1  # Market returned 10%
        
        # Create price data
        price_data = pd.DataFrame({
            'ticker': ['aapl', 'msft', 'googl', 'amzn'],
            'price_performance': [0.20, 0.15, 0.05, 0.30],  # Stock returns
            'start_price': [150, 250, 2000, 3000],
            'end_price': [180, 287.5, 2100, 3900]
        })
        mock_get_prices.return_value = price_data
        
        # Create price screener
        screener = PriceScreener(self.config)
        
        # Add price performance
        result = screener.add_price_performance(self.test_df)
        
        # Check result
        self.assertEqual(len(result), 4)
        self.assertIn('market_performance', result.columns)
        self.assertIn('market_outperformance', result.columns)
        
        # Check values
        self.assertTrue(all(result['market_performance'] == 0.1))
        
        # Check outperformance calculation
        np.testing.assert_almost_equal(
            result['market_outperformance'].values,
            result['price_performance'].values - 0.1
        )
    
    def test_apply_outperformance_filter(self):
        """Test apply_outperformance_filter."""
        # Create test data
        df = pd.DataFrame({
            'ticker': ['aapl', 'msft', 'googl', 'amzn', 'nvda'],
            'market_outperformance': [0.10, 0.05, -0.05, 0.20, np.nan]  # NaN should not pass
        })
        
        # Create price screener with outperform filter enabled
        screener = PriceScreener({
            "screening_criteria": {
                "outperform_sp500": True
            }
        })
        
        # Apply filter
        result = screener.apply_outperformance_filter(df)
        
        # Check result
        self.assertEqual(len(result), 3)  # Only the outperformers
        tickers = result['ticker'].tolist()
        self.assertIn('aapl', tickers)
        self.assertIn('msft', tickers)
        self.assertIn('amzn', tickers)
        self.assertNotIn('googl', tickers)
        
        # Try with filter disabled
        screener.criteria["outperform_sp500"] = False
        result = screener.apply_outperformance_filter(df)
        self.assertEqual(len(result), 5)  # All stocks pass

    def test_apply_outperformance_filter_fails_closed_without_metric(self):
        """When outperformance is required, missing comparison data should pass no stocks."""
        screener = PriceScreener({"screening_criteria": {"outperform_sp500": True}})
        df = pd.DataFrame({"ticker": ["aapl", "msft"]})

        result = screener.apply_outperformance_filter(df)

        self.assertTrue(result.empty)


if __name__ == '__main__':
    unittest.main()
