"""
Financial Modeling Prep API Client

This module provides a client for accessing the Financial Modeling Prep API
to retrieve institutional ownership data.
"""

import os
import time
import requests
import pandas as pd
from typing import Dict, List, Any, Optional, Union

from utils.logger import setup_logger

# Set up logger
logger = setup_logger("fmp_api_client")

class FMPClient:
    """
    Client for the Financial Modeling Prep API.
    
    Provides methods for retrieving institutional ownership data and other
    financial information.
    """
    
    BASE_URL = "https://financialmodelingprep.com/api/v3"
    
    def __init__(self, api_key: str, rate_limit_delay: float = 0.5):
        """
        Initialize the FMP API client.
        
        Args:
            api_key: API key for Financial Modeling Prep API
            rate_limit_delay: Delay between requests in seconds
        """
        if not api_key:
            raise ValueError("API key is required for Financial Modeling Prep API")
        
        self.api_key = api_key
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0
        
        logger.info("FMP API client initialized")
        
    def _respect_rate_limit(self) -> None:
        """Ensure rate limit is respected by adding delay if necessary."""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last_request
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _make_request(self, endpoint: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Make a request to the FMP API.
        
        Args:
            endpoint: API endpoint to request
            params: Query parameters
            
        Returns:
            Response data as dictionary
        """
        # Respect rate limit
        self._respect_rate_limit()
        
        # Prepare request
        url = f"{self.BASE_URL}/{endpoint}"
        request_params = params or {}
        request_params["apikey"] = self.api_key
        
        try:
            logger.debug(f"Making request to {url}")
            response = requests.get(url, params=request_params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making request to {url}: {e}")
            return {}
    
    def get_institutional_ownership(self, ticker: str) -> Dict[str, Any]:
        """
        Get institutional ownership data for a stock.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dictionary with institutional ownership data
        """
        endpoint = f"institutional-ownership/symbol-ownership/{ticker}"
        
        logger.debug(f"Getting institutional ownership for {ticker}")
        data = self._make_request(endpoint)
        
        if not data:
            logger.warning(f"No institutional ownership data found for {ticker}")
            return {"ticker": ticker, "institutionalOwnership": 0.0}
        
        return data
    
    def get_batch_institutional_ownership(self, tickers: List[str]) -> pd.DataFrame:
        """
        Get institutional ownership data for multiple stocks.
        
        Args:
            tickers: List of stock ticker symbols
            
        Returns:
            DataFrame with institutional ownership data
        """
        logger.info(f"Getting institutional ownership data for {len(tickers)} stocks")
        
        results = []
        for ticker in tickers:
            try:
                ownership_data = self.get_institutional_ownership(ticker)
                
                # Extract the summary data
                if isinstance(ownership_data, list) and ownership_data:
                    # Calculate total ownership percentage
                    total_ownership = sum(item.get('percentage', 0) for item in ownership_data)
                    results.append({
                        'ticker': ticker.lower(),
                        'institutional_ownership': total_ownership,
                        'institutional_holders': len(ownership_data)
                    })
                else:
                    results.append({
                        'ticker': ticker.lower(),
                        'institutional_ownership': 0.0,
                        'institutional_holders': 0
                    })
            except Exception as e:
                logger.error(f"Error getting institutional ownership for {ticker}: {e}")
                results.append({
                    'ticker': ticker.lower(),
                    'institutional_ownership': None,
                    'institutional_holders': 0
                })
        
        # Convert to DataFrame
        df = pd.DataFrame(results)
        
        logger.info(f"Retrieved institutional ownership data for {len(df)} stocks")
        return df
    
    def add_institutional_ownership(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add institutional ownership data to a DataFrame of stocks.
        
        Args:
            df: DataFrame containing stock information with 'ticker' column
            
        Returns:
            DataFrame with added institutional ownership data
        """
        if 'ticker' not in df.columns:
            logger.error("DataFrame must contain a 'ticker' column")
            return df
        
        # Extract unique tickers
        tickers = df['ticker'].unique().tolist()
        
        # Get institutional ownership data
        ownership_df = self.get_batch_institutional_ownership(tickers)
        
        # Merge with original DataFrame
        result_df = df.merge(ownership_df, on='ticker', how='left')
        
        logger.info(f"Added institutional ownership data to {len(result_df)} companies")
        return result_df
        
    def apply_institutional_ownership_filter(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """
        Filter stocks by institutional ownership.
        
        Args:
            df: DataFrame with institutional ownership data
            config: Configuration dictionary with screening criteria
            
        Returns:
            Filtered DataFrame
        """
        criteria = config.get("screening_criteria", {})
        min_ownership = criteria.get("institutional_ownership")
        
        if min_ownership is not None and 'institutional_ownership' in df.columns:
            before_count = len(df)
            df = df[df['institutional_ownership'] >= min_ownership]
            logger.info(f"Applied institutional ownership filter (≥{min_ownership*100:.1f}%): {before_count} -> {len(df)} companies")
        
        return df
