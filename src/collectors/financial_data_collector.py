"""
Financial Data Collector

Module for collecting and processing financial data from SEC EDGAR and other sources.
"""

import os
import json
import sys
import time
import pandas as pd
import numpy as np
import glob
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set, Union

from src.utils.logger import setup_logger

# Setup logger
logger = setup_logger("financial_collector")

class FinancialDataCollector:
    """
    Collects and processes quarterly and annual financial data
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the financial data collector
        
        Args:
            config: Application configuration
        """
        self.config = config
        
        # Get data paths
        data_paths = config.get("data_paths", {})
        self.raw_data_dir = data_paths.get("raw_data_dir", "data/raw")
        self.processed_data_dir = data_paths.get("processed_data_dir", "data/processed")
        self.company_facts_dir = data_paths.get("company_facts_dir", "data/raw/company_facts")
        self.financial_data_dir = os.path.join(self.raw_data_dir, "financial_data")
        
        # Create directory structure if it doesn't exist
        for directory in [self.financial_data_dir]:
            Path(directory).mkdir(parents=True, exist_ok=True)
            
        # Create subdirectories
        for subdir in ["quarterly", "annual", "market_data", "ownership"]:
            Path(os.path.join(self.financial_data_dir, subdir)).mkdir(exist_ok=True)
    
    def collect_quarterly_data(self, limit: Optional[int] = None) -> Dict[str, int]:
        """
        Collect and process quarterly financial data
        
        Args:
            limit: Maximum number of companies to process
            
        Returns:
            Dictionary with statistics
        """
        logger.info("Collecting quarterly financial data")
        
        # Stats to track processing
        stats = {
            "processed": 0,
            "success": 0,
            "error": 0
        }
        
        # Get list of companies with CIK and ticker
        companies = self._load_companies_list(limit)
        
        if not companies:
            logger.error("No companies found for quarterly data collection")
            return stats
        
        output_dir = os.path.join(self.financial_data_dir, "quarterly")
        
        # Process each company
        for company in companies:
            stats["processed"] += 1
            
            try:
                cik = company.get("cik")
                ticker = company.get("ticker")
                name = company.get("name")
                
                if not cik or not ticker:
                    logger.warning(f"Missing CIK or ticker for company: {name}")
                    continue
                
                # Load company facts file
                facts_file = os.path.join(self.company_facts_dir, f"CIK{cik.zfill(10)}.json")
                
                if not os.path.exists(facts_file):
                    logger.warning(f"Facts file not found for CIK {cik}: {facts_file}")
                    continue
                
                # Extract quarterly financials and save them
                quarterly_data = self._extract_quarterly_data(facts_file)
                
                if quarterly_data:
                    # Save to JSON
                    output_file = os.path.join(output_dir, f"{ticker}_quarterly.json")
                    with open(output_file, 'w') as f:
                        json.dump(quarterly_data, f, indent=2)
                    
                    stats["success"] += 1
                    
                    # Log progress occasionally
                    if stats["processed"] % 10 == 0:
                        logger.info(f"Processed {stats['processed']}/{len(companies)} companies")
                        
            except Exception as e:
                logger.error(f"Error processing quarterly data for {company.get('name', 'Unknown')}: {e}")
                stats["error"] += 1
                
        logger.info(f"Quarterly data collection complete: {stats['success']} successful, {stats['error']} errors")
        return stats
    
    def collect_annual_data(self, limit: Optional[int] = None) -> Dict[str, int]:
        """
        Collect and process annual financial data
        
        Args:
            limit: Maximum number of companies to process
            
        Returns:
            Dictionary with statistics
        """
        logger.info("Collecting annual financial data")
        
        # Stats to track processing
        stats = {
            "processed": 0,
            "success": 0,
            "error": 0
        }
        
        # Get list of companies with CIK and ticker
        companies = self._load_companies_list(limit)
        
        if not companies:
            logger.error("No companies found for annual data collection")
            return stats
        
        output_dir = os.path.join(self.financial_data_dir, "annual")
        
        # Process each company
        for company in companies:
            stats["processed"] += 1
            
            try:
                cik = company.get("cik")
                ticker = company.get("ticker")
                name = company.get("name")
                
                if not cik or not ticker:
                    logger.warning(f"Missing CIK or ticker for company: {name}")
                    continue
                
                # Load company facts file
                facts_file = os.path.join(self.company_facts_dir, f"CIK{cik.zfill(10)}.json")
                
                if not os.path.exists(facts_file):
                    logger.warning(f"Facts file not found for CIK {cik}: {facts_file}")
                    continue
                
                # Extract annual financials and save them
                annual_data = self._extract_annual_data(facts_file)
                
                if annual_data:
                    # Save to JSON
                    output_file = os.path.join(output_dir, f"{ticker}_annual.json")
                    with open(output_file, 'w') as f:
                        json.dump(annual_data, f, indent=2)
                    
                    stats["success"] += 1
                    
                    # Log progress occasionally
                    if stats["processed"] % 10 == 0:
                        logger.info(f"Processed {stats['processed']}/{len(companies)} companies")
                        
            except Exception as e:
                logger.error(f"Error processing annual data for {company.get('name', 'Unknown')}: {e}")
                stats["error"] += 1
                
        logger.info(f"Annual data collection complete: {stats['success']} successful, {stats['error']} errors")
        return stats
    
    def collect_market_data(self, limit: Optional[int] = None) -> Dict[str, int]:
        """
        Collect and process financial market data from SEC EDGAR data
        
        Args:
            limit: Maximum number of companies to process
            
        Returns:
            Dictionary with statistics
        """
        logger.info("Collecting market data from SEC filings")
        
        # Stats to track processing
        stats = {
            "processed": 0,
            "success": 0,
            "error": 0
        }
        
        # Get list of companies with tickers
        companies = self._load_companies_list(limit)
        
        if not companies:
            logger.error("No companies found for market data collection")
            return stats
        
        # Filter companies with tickers
        companies_with_tickers = [c for c in companies if c.get("ticker")]
        
        if not companies_with_tickers:
            logger.error("No companies with tickers found")
            return stats
        
        logger.info(f"Found {len(companies_with_tickers)} companies with tickers")
        
        output_dir = os.path.join(self.financial_data_dir, "market_data")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # Process each company
        for company in companies_with_tickers:
            stats["processed"] += 1
            
            try:
                ticker = company.get("ticker")
                cik = company.get("cik")
                name = company.get("name", "Unknown")
                
                # Load company facts file
                facts_file = os.path.join(self.company_facts_dir, f"CIK{cik.zfill(10)}.json")
                
                if not os.path.exists(facts_file):
                    logger.warning(f"Facts file not found for {ticker} (CIK: {cik})")
                    continue
                
                # Extract market valuation metrics from financial data
                market_data = self._calculate_market_metrics(facts_file, company)
                
                if market_data:
                    # Add ticker and timestamp
                    market_data["ticker"] = ticker
                    market_data["data_date"] = datetime.now().strftime("%Y-%m-%d")
                    
                    # Save to JSON
                    output_file = os.path.join(output_dir, f"{ticker}_market.json")
                    with open(output_file, 'w') as f:
                        json.dump(market_data, f, indent=2)
                    
                    stats["success"] += 1
                
                # Log progress occasionally
                if stats["processed"] % 10 == 0:
                    logger.info(f"Processed {stats['processed']}/{len(companies_with_tickers)} companies")
            
            except Exception as e:
                logger.error(f"Error processing market data for {company.get('ticker', 'Unknown')}: {e}")
                stats["error"] += 1
                
        logger.info(f"Market data collection complete: {stats['success']} successful, {stats['error']} errors")
        return stats
    
    def _calculate_market_metrics(self, facts_file: str, company: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate market metrics from SEC financial data
        
        Args:
            facts_file: Path to company facts JSON file
            company: Company data dictionary
            
        Returns:
            Dictionary with market metrics
        """
        try:
            with open(facts_file, 'r') as f:
                facts = json.load(f)
            
            if facts.get("no_data") == True:
                logger.debug(f"No data in facts file: {facts_file}")
                return {}
            
            # Get us-gaap namespace
            us_gaap = facts.get("facts", {}).get("us-gaap", {})
            if not us_gaap:
                logger.debug(f"No us-gaap data found in {facts_file}")
                return {}
            
            result = {}
            
            # Extract latest financial metrics for market valuation
            metrics = self._extract_latest_financial_metrics(us_gaap)
            
            # Calculate estimated market cap based on financial data
            # Book value = Assets - Liabilities
            if metrics.get("assets") is not None and metrics.get("liabilities") is not None:
                book_value = metrics["assets"] - metrics["liabilities"]
                result["book_value"] = book_value
                
                # Estimated market cap (simple book value method)
                result["estimated_market_cap"] = book_value
                
                # Price to Book (P/B) typically ranges from 1-3 for established companies
                # Use 1.5 as a conservative estimate
                result["estimated_market_cap_pb"] = book_value * 1.5
            
            # P/E ratio based estimation if earnings data is available
            if metrics.get("net_income") is not None and metrics["net_income"] > 0:
                # Use industry average P/E of 15 as a default multiplier
                industry_pe = 15
                result["estimated_market_cap_pe"] = metrics["net_income"] * industry_pe
                
                # If we have shares outstanding, calculate estimated share price
                if metrics.get("shares_outstanding") is not None and metrics["shares_outstanding"] > 0:
                    result["estimated_price"] = result["estimated_market_cap_pe"] / metrics["shares_outstanding"]
            
            # Add trailing twelve months (TTM) data if available
            if metrics.get("ttm_revenue") is not None:
                result["ttm_revenue"] = metrics["ttm_revenue"]
            
            if metrics.get("ttm_net_income") is not None:
                result["ttm_net_income"] = metrics["ttm_net_income"]
                
                # Estimate Price/Sales ratio (typically 1-3x for stable companies)
                if result.get("ttm_revenue") and result["ttm_revenue"] > 0:
                    result["price_to_sales"] = result.get("estimated_market_cap", 0) / result["ttm_revenue"]
            
            # Determine best market cap estimate
            # Priority: 1) Existing market_cap if available, 2) P/E based, 3) P/B based, 4) Book value
            if company.get("market_cap") and company["market_cap"] > 0:
                result["market_cap"] = company["market_cap"]
                result["market_cap_source"] = "existing_company_data"
            elif result.get("estimated_market_cap_pe"):
                result["market_cap"] = result["estimated_market_cap_pe"]
                result["market_cap_source"] = "estimated_pe_ratio"
            elif result.get("estimated_market_cap_pb"):
                result["market_cap"] = result["estimated_market_cap_pb"]
                result["market_cap_source"] = "estimated_pb_ratio"
            elif result.get("estimated_market_cap"):
                result["market_cap"] = result["estimated_market_cap"]
                result["market_cap_source"] = "estimated_book_value"
                
            return result
                
        except Exception as e:
            logger.error(f"Error calculating market metrics: {e}")
            return {}
    
    def _extract_latest_financial_metrics(self, us_gaap: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract latest financial metrics from us-gaap data
        
        Args:
            us_gaap: us-gaap namespace data from company facts
            
        Returns:
            Dictionary with latest metrics
        """
        metrics = {}
        
        # Define metric mappings (XBRL tag to metric name)
        metric_mappings = {
            "Assets": "assets",
            "Liabilities": "liabilities",
            "StockholdersEquity": "equity",
            "CommonStockSharesOutstanding": "shares_outstanding",
            "WeightedAverageNumberOfSharesOutstandingBasic": "shares_outstanding", 
            "WeightedAverageNumberOfDilutedSharesOutstanding": "shares_outstanding",
            "NetIncomeLoss": "net_income",
            "ProfitLoss": "net_income",
            "NetIncome": "net_income",
            "Revenues": "revenue",
            "Revenue": "revenue",
            "SalesRevenueNet": "revenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
            "EarningsPerShareDiluted": "eps_diluted",
            "EarningsPerShareBasic": "eps_basic",
            "RetainedEarningsAccumulatedDeficit": "retained_earnings",
            "OperatingIncomeLoss": "operating_income"
        }
        
        # Extract the latest values for each metric
        for tag, metric_name in metric_mappings.items():
            if tag in us_gaap:
                latest_value = self._get_latest_value(us_gaap[tag])
                if latest_value is not None:
                    # If we already have this metric, only replace if it came from a better tag
                    # This creates a priority ordering for tags
                    if metric_name not in metrics or tag in ["Assets", "Liabilities", "StockholdersEquity", 
                                                           "NetIncomeLoss", "Revenue", "EarningsPerShareDiluted"]:
                        metrics[metric_name] = latest_value
        
        # Calculate TTM (Trailing Twelve Months) metrics if possible
        metrics.update(self._calculate_ttm_metrics(us_gaap))
        
        # Derive additional metrics if we have enough data
        if "net_income" in metrics and "revenue" in metrics and metrics["revenue"] > 0:
            metrics["profit_margin"] = metrics["net_income"] / metrics["revenue"]
            
        if "net_income" in metrics and "equity" in metrics and metrics["equity"] > 0:
            metrics["roe"] = metrics["net_income"] / metrics["equity"]
            
        if "liabilities" in metrics and "equity" in metrics and metrics["equity"] > 0:
            metrics["debt_to_equity"] = metrics["liabilities"] / metrics["equity"]
            
        if "assets" in metrics and "liabilities" in metrics:
            metrics["book_value"] = metrics["assets"] - metrics["liabilities"]
        
        return metrics
    
    def _get_latest_value(self, tag_data: Dict[str, Any]) -> Optional[float]:
        """
        Get the latest value for a tag
        
        Args:
            tag_data: Tag data from us-gaap
            
        Returns:
            Latest value or None if not available
        """
        try:
            # Find the units (usually USD)
            units = tag_data.get("units", {})
            if not units:
                return None
            
            # Try common unit types (USD, shares, pure)
            for unit_type in ["USD", "shares", "pure"]:
                if unit_type in units:
                    # Sort by end date (descending)
                    values = sorted(
                        [v for v in units[unit_type] if "val" in v and "period" in v and "endDate" in v["period"]],
                        key=lambda x: x["period"]["endDate"],
                        reverse=True
                    )
                    
                    # Return the most recent value if available
                    if values:
                        return float(values[0]["val"])
            
            return None
            
        except Exception as e:
            logger.debug(f"Error getting latest value: {e}")
            return None
    
    def _calculate_ttm_metrics(self, us_gaap: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate trailing twelve months metrics
        
        Args:
            us_gaap: us-gaap namespace data from company facts
            
        Returns:
            Dictionary with TTM metrics
        """
        ttm_metrics = {}
        
        # Try to calculate TTM revenue
        revenue_tags = ["Revenue", "Revenues", "SalesRevenueNet"]
        for tag in revenue_tags:
            if tag in us_gaap:
                ttm_revenue = self._calculate_ttm_value(us_gaap[tag])
                if ttm_revenue:
                    ttm_metrics["ttm_revenue"] = ttm_revenue
                    break
        
        # Try to calculate TTM net income
        income_tags = ["NetIncomeLoss", "ProfitLoss", "NetIncome"]
        for tag in income_tags:
            if tag in us_gaap:
                ttm_income = self._calculate_ttm_value(us_gaap[tag])
                if ttm_income:
                    ttm_metrics["ttm_net_income"] = ttm_income
                    break
        
        return ttm_metrics
    
    def _calculate_ttm_value(self, tag_data: Dict[str, Any]) -> Optional[float]:
        """
        Calculate trailing twelve months value for a metric
        
        Args:
            tag_data: Tag data from us-gaap
            
        Returns:
            TTM value or None if not enough data
        """
        try:
            # Find the units (usually USD)
            units = tag_data.get("units", {})
            if not units or "USD" not in units:
                return None
            
            # Get quarterly data (10-Q)
            quarterly_data = []
            for item in units["USD"]:
                if item.get("form") == "10-Q" and "val" in item and "period" in item and "endDate" in item["period"]:
                    quarterly_data.append({
                        "end_date": item["period"]["endDate"],
                        "value": float(item["val"])
                    })
            
            # Sort by end date (descending)
            quarterly_data.sort(key=lambda x: x["end_date"], reverse=True)
            
            # Need at least 4 quarters for TTM
            if len(quarterly_data) >= 4:
                ttm_value = sum(item["value"] for item in quarterly_data[:4])
                return ttm_value
            
            # Alternative: Try to use annual report
            annual_data = []
            for item in units["USD"]:
                if item.get("form") == "10-K" and "val" in item and "period" in item and "endDate" in item["period"]:
                    annual_data.append({
                        "end_date": item["period"]["endDate"],
                        "value": float(item["val"])
                    })
            
            # Sort by end date (descending)
            annual_data.sort(key=lambda x: x["end_date"], reverse=True)
            
            # Use most recent annual value if available
            if annual_data:
                return annual_data[0]["value"]
            
            return None
            
        except Exception as e:
            logger.debug(f"Error calculating TTM value: {e}")
            return None
    
    def _load_companies_list(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Load companies list from processed data"""
        companies_list_file = os.path.join(self.processed_data_dir, "companies_list.json")
        
        if not os.path.exists(companies_list_file):
            logger.error(f"Companies list file not found: {companies_list_file}")
            return []
        
        try:
            with open(companies_list_file, 'r') as f:
                companies = json.load(f)
            
            # Apply limit if specified
            if limit and limit > 0:
                companies = companies[:limit]
                
            return companies
            
        except Exception as e:
            logger.error(f"Error loading companies list: {e}")
            return []
    
    def _extract_quarterly_data(self, facts_file: str) -> Dict[str, Any]:
        """Extract quarterly financial data from facts file"""
        try:
            with open(facts_file, 'r') as f:
                facts = json.load(f)
            
            if facts.get("no_data") == True:
                logger.debug(f"No data in facts file: {facts_file}")
                return {}
            
            # Get basic company info
            cik = facts.get("cik", "")
            name = facts.get("entityName", "")
            
            # Get us-gaap namespace
            us_gaap = facts.get("facts", {}).get("us-gaap", {})
            if not us_gaap:
                logger.debug(f"No us-gaap data found in {facts_file}")
                return {}
            
            # Extract quarterly data (10-Q filings)
            quarterly_data = {
                "cik": cik,
                "name": name,
                "quarters": []
            }
            
            # Look for key financial metrics
            metrics = {
                "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic", "IncomeLossPerShareBasicAndDiluted"],
                "revenue": ["Revenue", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax"],
                "net_income": ["NetIncomeLoss", "ProfitLoss", "NetIncome"],
                "assets": ["Assets"],
                "liabilities": ["Liabilities"],
                "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
            }
            
            # Dictionary to store quarterly data by date
            quarterly_by_date = {}
            
            # Process each metric category
            for category, tags in metrics.items():
                for tag in tags:
                    if tag in us_gaap:
                        # Get units
                        units = us_gaap[tag].get("units", {})
                        
                        for unit_type, values in units.items():
                            for item in values:
                                # Only include 10-Q reports
                                if item.get("form") == "10-Q" and "val" in item and "period" in item:
                                    end_date = item["period"].get("endDate")
                                    if end_date:
                                        # Initialize quarter data if needed
                                        if end_date not in quarterly_by_date:
                                            quarterly_by_date[end_date] = {
                                                "end_date": end_date,
                                                "form": "10-Q"
                                            }
                                        
                                        # Add this metric
                                        quarterly_by_date[end_date][category] = float(item["val"])
            
            # Convert to list and sort by date (newest first)
            quarters = list(quarterly_by_date.values())
            quarters.sort(key=lambda x: x["end_date"], reverse=True)
            
            # Add to result
            quarterly_data["quarters"] = quarters
            
            return quarterly_data
            
        except Exception as e:
            logger.error(f"Error extracting quarterly data from {facts_file}: {e}")
            return {}
    
    def _extract_annual_data(self, facts_file: str) -> Dict[str, Any]:
        """Extract annual financial data from facts file"""
        try:
            with open(facts_file, 'r') as f:
                facts = json.load(f)
            
            if facts.get("no_data") == True:
                logger.debug(f"No data in facts file: {facts_file}")
                return {}
            
            # Get basic company info
            cik = facts.get("cik", "")
            name = facts.get("entityName", "")
            
            # Get us-gaap namespace
            us_gaap = facts.get("facts", {}).get("us-gaap", {})
            if not us_gaap:
                logger.debug(f"No us-gaap data found in {facts_file}")
                return {}
            
            # Extract annual data (10-K filings)
            annual_data = {
                "cik": cik,
                "name": name,
                "years": []
            }
            
            # Look for key financial metrics
            metrics = {
                "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic", "IncomeLossPerShareBasicAndDiluted"],
                "revenue": ["Revenue", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax"],
                "net_income": ["NetIncomeLoss", "ProfitLoss", "NetIncome"],
                "assets": ["Assets"],
                "liabilities": ["Liabilities"],
                "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
            }
            
            # Dictionary to store annual data by date
            annual_by_date = {}
            
            # Process each metric category
            for category, tags in metrics.items():
                for tag in tags:
                    if tag in us_gaap:
                        # Get units
                        units = us_gaap[tag].get("units", {})
                        
                        for unit_type, values in units.items():
                            for item in values:
                                # Only include 10-K reports
                                if item.get("form") == "10-K" and "val" in item and "period" in item:
                                    end_date = item["period"].get("endDate")
                                    if end_date:
                                        # Initialize year data if needed
                                        if end_date not in annual_by_date:
                                            annual_by_date[end_date] = {
                                                "end_date": end_date,
                                                "form": "10-K"
                                            }
                                        
                                        # Add this metric
                                        annual_by_date[end_date][category] = float(item["val"])
            
            # Convert to list and sort by date (newest first)
            years = list(annual_by_date.values())
            years.sort(key=lambda x: x["end_date"], reverse=True)
            
            # Add to result
            annual_data["years"] = years
            
            return annual_data
            
        except Exception as e:
            logger.error(f"Error extracting annual data from {facts_file}: {e}")
            return {}

def collect_financial_data(config: Dict[str, Any]) -> bool:
    """
    Standalone function to collect financial data
    
    Args:
        config: Application configuration
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info("Starting financial data collection")
        
        # Create collector
        collector = FinancialDataCollector(config)
        
        # Get limit from config
        limit = config.get("download_settings", {}).get("company_limit")
        
        # Collect quarterly data
        quarterly_stats = collector.collect_quarterly_data(limit)
        logger.info(f"Quarterly data: {quarterly_stats}")
        
        # Collect annual data
        annual_stats = collector.collect_annual_data(limit)
        logger.info(f"Annual data: {annual_stats}")
        
        # Collect market data
        market_stats = collector.collect_market_data(limit)
        logger.info(f"Market data: {market_stats}")
        
        # Summary
        total_success = quarterly_stats["success"] + annual_stats["success"] + market_stats["success"]
        logger.info(f"Financial data collection complete. Total successful files: {total_success}")
        
        return total_success > 0
        
    except Exception as e:
        logger.error(f"Error during financial data collection: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Collect financial data")
    parser.add_argument("--config", default="config/config.json", help="Path to config file")
    parser.add_argument("--limit", type=int, help="Limit number of companies to process")
    args = parser.parse_args()
    
    # Load config
    with open(args.config, 'r') as f:
        config = json.load(f)
    
    # Override company limit if specified
    if args.limit:
        if "download_settings" not in config:
            config["download_settings"] = {}
        config["download_settings"]["company_limit"] = args.limit
    
    # Run collection
    success = collect_financial_data(config)
    sys.exit(0 if success else 1)
