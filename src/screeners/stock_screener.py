"""
Stock Screener Module

This module provides functionality for screening stocks based on various criteria.
"""

import os
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Set, Union
from datetime import datetime, timedelta

from utils.logger import setup_logger

# Set up logger
logger = setup_logger("stock_screener")

class StockScreener:
    """
    Stock screener that applies various filters to find growth stocks.
    
    This class loads financial metrics data and applies a series of filters
    based on the CAN SLIM and Minervini growth stock criteria.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the StockScreener.
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        
        # Get data paths from config
        data_paths = config.get("data_paths", {})
        self.processed_data_dir = data_paths.get("processed_data_dir", "data/processed")
        self.financial_metrics_file = os.path.join(self.processed_data_dir, "financial_metrics.parquet")
        self.companies_index_file = os.path.join(self.processed_data_dir, "companies_index.parquet")
        self.output_file = data_paths.get("output_file", "data/processed/results.csv")
        
        # Get screening criteria from config
        self.criteria = config.get("screening_criteria", {})
        
        # Load the data
        self.load_data()
    
    def load_data(self) -> None:
        """
        Load the financial metrics and company index data.
        """
        logger.info("Loading financial metrics data...")
        
        # Check if the financial metrics file exists
        if not os.path.exists(self.financial_metrics_file):
            logger.error(f"Financial metrics file not found: {self.financial_metrics_file}")
            raise FileNotFoundError(f"Financial metrics file not found: {self.financial_metrics_file}")
        
        # Load the financial metrics data
        try:
            self.metrics_df = pd.read_parquet(self.financial_metrics_file)
            logger.info(f"Loaded financial metrics for {len(self.metrics_df)} companies")
        except Exception as e:
            logger.error(f"Error loading financial metrics: {e}")
            raise
        
        # Load the companies index data if it exists
        if os.path.exists(self.companies_index_file):
            try:
                self.companies_df = pd.read_parquet(self.companies_index_file)
                logger.info(f"Loaded companies index with {len(self.companies_df)} entries")
                
                # Merge market cap data into the metrics DataFrame
                if 'ticker' in self.metrics_df.columns and 'ticker' in self.companies_df.columns:
                    self.metrics_df = self.metrics_df.merge(
                        self.companies_df[['ticker', 'market_cap', 'exchange']],
                        on='ticker',
                        how='left'
                    )
            except Exception as e:
                logger.warning(f"Error loading companies index: {e}")
                self.companies_df = None
    
    def apply_eps_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter companies by EPS growth rate.
        
        Args:
            df: DataFrame containing financial metrics
            
        Returns:
            Filtered DataFrame
        """
        min_eps_growth = self.criteria.get("quarterly_eps_growth")
        if min_eps_growth is not None and 'eps_qtr_growth' in df.columns:
            before_count = len(df)
            df = df[df['eps_qtr_growth'] >= min_eps_growth]
            logger.info(f"Applied EPS growth filter (≥{min_eps_growth*100:.1f}%): {before_count} -> {len(df)} companies")
        
        # Also check annual EPS CAGR if specified
        min_eps_cagr = self.criteria.get("annual_eps_cagr")
        if min_eps_cagr is not None and 'eps_3yr_cagr' in df.columns:
            before_count = len(df)
            df = df[df['eps_3yr_cagr'] >= min_eps_cagr]
            logger.info(f"Applied EPS 3-yr CAGR filter (≥{min_eps_cagr*100:.1f}%): {before_count} -> {len(df)} companies")
            
        return df
    
    def apply_revenue_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter companies by revenue growth rate.
        
        Args:
            df: DataFrame containing financial metrics
            
        Returns:
            Filtered DataFrame
        """
        min_revenue_growth = self.criteria.get("revenue_growth")
        if min_revenue_growth is not None and 'revenue_qtr_growth' in df.columns:
            before_count = len(df)
            df = df[df['revenue_qtr_growth'] >= min_revenue_growth]
            logger.info(f"Applied revenue growth filter (≥{min_revenue_growth*100:.1f}%): {before_count} -> {len(df)} companies")
            
        return df
    
    def apply_profit_margin_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter companies by profit margin.
        
        Args:
            df: DataFrame containing financial metrics
            
        Returns:
            Filtered DataFrame
        """
        min_profit_margin = self.criteria.get("profit_margin")
        if min_profit_margin is not None and 'profit_margin' in df.columns:
            before_count = len(df)
            df = df[df['profit_margin'] >= min_profit_margin]
            logger.info(f"Applied profit margin filter (≥{min_profit_margin*100:.1f}%): {before_count} -> {len(df)} companies")
            
        return df
    
    def apply_roe_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter companies by return on equity (ROE).
        
        Args:
            df: DataFrame containing financial metrics
            
        Returns:
            Filtered DataFrame
        """
        min_roe = self.criteria.get("roe")
        if min_roe is not None and 'roe' in df.columns:
            before_count = len(df)
            df = df[df['roe'] >= min_roe]
            logger.info(f"Applied ROE filter (≥{min_roe*100:.1f}%): {before_count} -> {len(df)} companies")
            
        return df
    
    def apply_debt_to_equity_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter companies by debt-to-equity ratio.
        
        Args:
            df: DataFrame containing financial metrics
            
        Returns:
            Filtered DataFrame
        """
        max_debt_to_equity = self.criteria.get("debt_to_equity")
        if max_debt_to_equity is not None and 'debt_to_equity' in df.columns:
            before_count = len(df)
            df = df[df['debt_to_equity'] <= max_debt_to_equity]
            logger.info(f"Applied debt-to-equity filter (≤{max_debt_to_equity:.1f}): {before_count} -> {len(df)} companies")
            
        return df
    
    def apply_market_cap_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter companies by market capitalization.
        
        Args:
            df: DataFrame containing financial metrics with market cap
            
        Returns:
            Filtered DataFrame
        """
        min_market_cap = self.criteria.get("min_market_cap")
        if min_market_cap is not None and 'market_cap' in df.columns:
            before_count = len(df)
            df = df[df['market_cap'] >= min_market_cap]
            logger.info(f"Applied market cap filter (≥${min_market_cap/1e6:.1f}M): {before_count} -> {len(df)} companies")
            
        return df
    
    def apply_complete_data_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter for companies with complete financial data.
        
        Args:
            df: DataFrame containing financial metrics
            
        Returns:
            Filtered DataFrame
        """
        if 'has_complete_data' in df.columns:
            before_count = len(df)
            df = df[df['has_complete_data'] == True]
            logger.info(f"Applied complete data filter: {before_count} -> {len(df)} companies")
            
        return df
    
    def apply_all_filters(self, df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Apply all configured filters to the data.
        
        Args:
            df: Optional DataFrame to filter (uses self.metrics_df if not provided)
            
        Returns:
            Filtered DataFrame
        """
        if df is None:
            df = self.metrics_df.copy()
        
        logger.info(f"Starting screening with {len(df)} companies")
        
        # Apply base data quality filter
        df = self.apply_complete_data_filter(df)
        
        # Apply financial metric filters
        df = self.apply_eps_filter(df)
        df = self.apply_revenue_filter(df)
        df = self.apply_profit_margin_filter(df)
        df = self.apply_roe_filter(df)
        df = self.apply_debt_to_equity_filter(df)
        df = self.apply_market_cap_filter(df)
        
        logger.info(f"Screening complete: {len(df)} companies matched all criteria")
        return df
