"""
Price Screener Module

This module provides functionality for integrating stock price data and 
calculating market outperformance.
"""

import os
import pandas as pd
import numpy as np
import yfinance as yf
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta

from utils.logger import setup_logger

# Set up logger
logger = setup_logger("price_screener")

class PriceScreener:
    """
    Price screener that retrieves stock price data and calculates performance.
    
    This class retrieves stock price data from yfinance and calculates
    performance metrics, including market outperformance.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the PriceScreener.
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        self.criteria = config.get("screening_criteria", {})
        self.market_index = self.criteria.get("market_index", "^GSPC")  # S&P 500 by default
        
        # Calculate the date range for price performance
        self.months_lookback = self.criteria.get("price_months_lookback", 6)
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=self.months_lookback * 30)
        
        # Format dates for yfinance
        self.start_str = self.start_date.strftime('%Y-%m-%d')
        self.end_str = self.end_date.strftime('%Y-%m-%d')
        
    def get_market_performance(self) -> float:
        """
        Get the performance of the market index over the specified time period.
        
        Returns:
            Market performance as a percentage return
        """
        logger.info(f"Fetching market performance for {self.market_index} from {self.start_str} to {self.end_str}")
        
        try:
            # Download market index data
            market_data = yf.download(
                self.market_index,
                start=self.start_str,
                end=self.end_str,
                progress=False
            )
            
            if market_data.empty:
                logger.warning(f"No data found for market index {self.market_index}")
                return 0.0
            
            # Calculate performance
            first_price = market_data['Close'].iloc[0]
            last_price = market_data['Close'].iloc[-1]
            performance = (last_price / first_price) - 1.0
            
            logger.info(f"{self.market_index} performance: {performance*100:.2f}% over {self.months_lookback} months")
            return performance
            
        except Exception as e:
            logger.error(f"Error getting market performance: {e}")
            return 0.0
    
    def get_stock_prices(self, tickers: List[str], chunk_size: int = 50) -> pd.DataFrame:
        """
        Get price data for a list of stocks.
        
        Args:
            tickers: List of ticker symbols
            chunk_size: Number of tickers to process in each batch
            
        Returns:
            DataFrame with stock price performance data
        """
        logger.info(f"Fetching price data for {len(tickers)} stocks")
        
        # Ensure tickers are in the correct format for yfinance
        formatted_tickers = [ticker.upper() for ticker in tickers]
        
        # Initialize results DataFrame
        result_data = []
        
        # Process tickers in chunks to avoid rate limits
        for i in range(0, len(formatted_tickers), chunk_size):
            chunk_tickers = formatted_tickers[i:i+chunk_size]
            ticker_str = ' '.join(chunk_tickers)
            
            logger.debug(f"Processing chunk {i//chunk_size + 1}: {len(chunk_tickers)} tickers")
            
            try:
                # Download price data for the chunk
                price_data = yf.download(
                    ticker_str,
                    start=self.start_str,
                    end=self.end_str,
                    group_by='ticker',
                    progress=False
                )
                
                # Process each ticker in the chunk
                for ticker in chunk_tickers:
                    # Handle single ticker case
                    if len(chunk_tickers) == 1:
                        ticker_data = price_data
                    else:
                        ticker_data = price_data[ticker]
                    
                    # Skip if no data
                    if ticker_data.empty:
                        logger.warning(f"No price data for {ticker}")
                        continue
                    
                    # Calculate performance
                    first_price = ticker_data['Close'].iloc[0]
                    last_price = ticker_data['Close'].iloc[-1]
                    performance = (last_price / first_price) - 1.0
                    
                    # Add to results
                    result_data.append({
                        'ticker': ticker.lower(),  # Convert back to lowercase for consistency
                        'price_performance': performance,
                        'start_price': first_price,
                        'end_price': last_price,
                        'start_date': self.start_date,
                        'end_date': self.end_date,
                        'trading_days': len(ticker_data)
                    })
                    
            except Exception as e:
                logger.error(f"Error getting price data for chunk: {e}")
                continue
        
        # Convert to DataFrame
        df = pd.DataFrame(result_data)
        
        logger.info(f"Retrieved price data for {len(df)} out of {len(tickers)} stocks")
        return df
    
    def add_price_performance(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add price performance data to a DataFrame of stocks.
        
        Args:
            df: DataFrame containing stock information with 'ticker' column
            
        Returns:
            DataFrame with added price performance data
        """
        # Extract unique tickers
        if 'ticker' not in df.columns:
            logger.error("DataFrame must contain a 'ticker' column")
            return df
        
        tickers = df['ticker'].unique().tolist()
        
        # Get market performance
        market_performance = self.get_market_performance()
        
        # Get stock performance data
        price_df = self.get_stock_prices(tickers)
        
        # Add the market performance to the price data
        price_df['market_performance'] = market_performance
        
        # Calculate market outperformance
        price_df['market_outperformance'] = price_df['price_performance'] - market_performance
        
        # Merge with original DataFrame
        result_df = df.merge(price_df, on='ticker', how='left')
        
        logger.info(f"Added price performance data to {len(result_df)} companies")
        return result_df
    
    def apply_outperformance_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter for stocks that outperform the market.
        
        Args:
            df: DataFrame with price performance data
            
        Returns:
            Filtered DataFrame
        """
        outperform_required = self.criteria.get("outperform_sp500", False)
        if outperform_required and 'market_outperformance' in df.columns:
            before_count = len(df)
            df = df[df['market_outperformance'] > 0]
            logger.info(f"Applied market outperformance filter: {before_count} -> {len(df)} companies")
        
        return df
