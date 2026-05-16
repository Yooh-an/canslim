#!/usr/bin/env python3
"""
SEC Financial Data Collector Runner

Script to run the SEC-based financial data collection process to enrich existing data
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Add project root path to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.collectors.financial_data_collector import collect_financial_data
from src.utils.logger import setup_logger
from src.utils.directory import ensure_directories

# Setup logger
logger = setup_logger("run_data_collector")

def main():
    """Main function for data collection"""
    parser = argparse.ArgumentParser(description="Run SEC financial data collection")
    parser.add_argument("--config", default="config/config.json", help="Path to config file")
    parser.add_argument("--limit", type=int, help="Limit the number of companies to process")
    parser.add_argument("--quarterly", action="store_true", help="Collect quarterly data only")
    parser.add_argument("--annual", action="store_true", help="Collect annual data only")
    parser.add_argument("--market", action="store_true", help="Collect market data only")
    args = parser.parse_args()
    
    # Load config
    try:
        with open(args.config, 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Error loading config file: {e}")
        sys.exit(1)
    
    # Ensure directories
    ensure_directories(config)
    
    # Override company limit if specified
    if args.limit:
        if "download_settings" not in config:
            config["download_settings"] = {}
        config["download_settings"]["company_limit"] = args.limit
        logger.info(f"Processing limit set to {args.limit} companies")
    
    # Track success
    success = False
    
    # If no specific collection type is specified, collect all data types
    collect_all = not (args.quarterly or args.annual or args.market)
    
    if collect_all:
        # Collect all data types
        logger.info("Starting full financial data collection...")
        success = collect_financial_data(config)
    else:
        # Create collector for selective data collection
        from src.collectors.financial_data_collector import FinancialDataCollector
        collector = FinancialDataCollector(config)
        
        # Get limit from config
        limit = config.get("download_settings", {}).get("company_limit")
        
        results = {"success": 0, "error": 0}
        
        # Collect only specified data types
        if args.quarterly:
            logger.info("Collecting quarterly financial data...")
            quarterly_results = collector.collect_quarterly_data(limit)
            results["success"] += quarterly_results["success"]
            results["error"] += quarterly_results["error"]
            
        if args.annual:
            logger.info("Collecting annual financial data...")
            annual_results = collector.collect_annual_data(limit)
            results["success"] += annual_results["success"]
            results["error"] += annual_results["error"]
            
        if args.market:
            logger.info("Collecting market data from SEC filings...")
            market_results = collector.collect_market_data(limit)
            results["success"] += market_results["success"]
            results["error"] += market_results["error"]
            
        success = results["success"] > 0
        logger.info(f"Collection complete. Success: {results['success']}, Errors: {results['error']}")
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
