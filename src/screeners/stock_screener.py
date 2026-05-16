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
    """Screens stocks based on financial criteria."""
    
    def __init__(self, config):
        self.config = config
        self.criteria = config.get('screening_criteria', {})
        
    def screen_stocks(self, company_data):
        """
        Apply screening criteria to company data
        
        Args:
            company_data: DataFrame with company financial and market data
            
        Returns:
            DataFrame with companies that pass all criteria
        """
        logger.info(f"Screening {len(company_data)} companies")
        
        # Make a copy to avoid modifying original
        df = company_data.copy()
        
        # Initial count
        initial_count = len(df)
        
        # Apply financial criteria
        filtered_df = self._apply_financial_criteria(df)
        
        # Apply market criteria if possible
        if 'market_cap' in filtered_df.columns:
            filtered_df = self._apply_market_criteria(filtered_df)
        
        # Final count
        final_count = len(filtered_df)
        
        logger.info(f"Screening complete: {final_count} companies passed out of {initial_count}")
        
        return filtered_df
        
    def _apply_financial_criteria(self, df):
        """Apply financial metrics criteria."""
        # Start with all companies
        mask = pd.Series(True, index=df.index)
        
        # Apply each criterion if it exists in both data and criteria
        criteria_values = self.criteria
        
        # EPS Growth
        if 'quarterly_eps_growth' in df.columns and 'quarterly_eps_growth' in criteria_values:
            threshold = criteria_values['quarterly_eps_growth']
            eps_mask = df['quarterly_eps_growth'] >= threshold
            # Handle NaN values
            eps_mask = eps_mask.fillna(False)
            mask = mask & eps_mask
            logger.info(f"After EPS growth filter: {mask.sum()} companies")
        
        # Annual EPS CAGR
        if 'annual_eps_cagr' in df.columns and 'annual_eps_cagr' in criteria_values:
            threshold = criteria_values['annual_eps_cagr']
            cagr_mask = df['annual_eps_cagr'] >= threshold
            cagr_mask = cagr_mask.fillna(False)
            mask = mask & cagr_mask
            logger.info(f"After annual EPS CAGR filter: {mask.sum()} companies")
        
        # Revenue Growth
        if 'revenue_growth' in df.columns and 'revenue_growth' in criteria_values:
            threshold = criteria_values['revenue_growth']
            rev_mask = df['revenue_growth'] >= threshold
            rev_mask = rev_mask.fillna(False)
            mask = mask & rev_mask
            logger.info(f"After revenue growth filter: {mask.sum()} companies")
        
        # Profit Margin
        if 'profit_margin' in df.columns and 'profit_margin' in criteria_values:
            threshold = criteria_values['profit_margin']
            pm_mask = df['profit_margin'] >= threshold
            pm_mask = pm_mask.fillna(False)
            mask = mask & pm_mask
            logger.info(f"After profit margin filter: {mask.sum()} companies")
        
        # ROE
        if 'roe' in df.columns and 'roe' in criteria_values:
            threshold = criteria_values['roe']
            roe_mask = df['roe'] >= threshold
            roe_mask = roe_mask.fillna(False)
            mask = mask & roe_mask
            logger.info(f"After ROE filter: {mask.sum()} companies")
        
        # Debt-to-Equity
        if 'debt_to_equity' in df.columns and 'debt_to_equity' in criteria_values:
            threshold = criteria_values['debt_to_equity']
            # For D/E, we want it to be BELOW the threshold
            dte_mask = df['debt_to_equity'] <= threshold
            dte_mask = dte_mask.fillna(False)
            mask = mask & dte_mask
            logger.info(f"After debt-to-equity filter: {mask.sum()} companies")
        
        # Apply the combined filter
        return df[mask].copy()
    
    def _apply_market_criteria(self, df):
        """Apply market-based criteria."""
        # Start with all companies
        mask = pd.Series(True, index=df.index)
        
        # S&P 500 outperformance
        if ('sp500_outperformance' in df.columns and 
            'outperform_sp500' in self.criteria and 
            self.criteria['outperform_sp500']):
            
            outperf_mask = df['sp500_outperformance'] > 0
            outperf_mask = outperf_mask.fillna(False)
            mask = mask & outperf_mask
            logger.info(f"After S&P 500 outperformance filter: {mask.sum()} companies")
        
        # Minimum market cap
        if ('market_cap' in df.columns and 
            'min_market_cap' in self.criteria and 
            self.criteria['min_market_cap'] > 0):
            
            min_cap = self.criteria['min_market_cap']
            cap_mask = df['market_cap'] >= min_cap
            cap_mask = cap_mask.fillna(False)
            mask = mask & cap_mask
            logger.info(f"After market cap filter: {mask.sum()} companies")
        
        # Apply the combined filter
        return df[mask].copy()
