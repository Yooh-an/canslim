#!/usr/bin/env python3
"""
Growth Stock Screener

A command-line tool for screening growth stocks using SEC EDGAR data.
"""

import argparse
import json
import os
import sys
import logging
import pandas as pd
from pathlib import Path

from utils.logger import setup_logger
from utils.directory import ensure_directories
from api.sec_client import SECClient
from collectors.submissions_collector import SubmissionsCollector
from collectors.facts_collector import CompanyFactsCollector
from parsers.submissions_parser import SubmissionsParser
from parsers.facts_parser import XBRLFactsParser

def load_config(config_path):
    """Load configuration from JSON file."""
    try:
        with open(config_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        logger.error(f"Config file '{config_path}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.error(f"Config file '{config_path}' is not valid JSON.")
        sys.exit(1)

def download_data(config):
    """Download data from SEC EDGAR."""
    logger.info("Downloading data from SEC EDGAR...")
    
    # Initialize SEC API client
    user_agent = config.get("sec_api", {}).get("user_agent")
    if not user_agent:
        logger.error("User-Agent must be provided in config.json under sec_api.user_agent")
        sys.exit(1)
    
    rate_limit = config.get("sec_api", {}).get("rate_limit_delay", 0.1)
    sec_client = SECClient(user_agent=user_agent, rate_limit_delay=rate_limit)
    
    # Download submissions data
    submissions_collector = SubmissionsCollector(sec_client, config)
    submissions_file = submissions_collector.download_submissions()
    
    # Extract active companies
    try:
        min_market_cap = config.get("screening_criteria", {}).get("min_market_cap")
        companies = submissions_collector.get_company_list(min_market_cap)
        logger.info(f"Found {len(companies)} companies meeting criteria")
        
        # Save list of companies for later use
        companies_file = os.path.join(config.get("data_paths", {}).get("processed_data_dir", 
                                                                      "data/processed"), 
                                     "companies_list.json")
        Path(os.path.dirname(companies_file)).mkdir(parents=True, exist_ok=True)
        
        with open(companies_file, 'w') as f:
            json.dump(companies, f)
        
        logger.info(f"Saved company list to {companies_file}")
        
        # Download company facts data
        facts_collector = CompanyFactsCollector(sec_client, config)
        
        # Set limit if specified
        company_limit = config.get("download_settings", {}).get("company_limit")
        force_download = config.get("download_settings", {}).get("force_download", False)
        
        # Start the download process
        results = facts_collector.download_all_company_facts(
            limit=company_limit, 
            force=force_download
        )
        
        # Validate downloaded files
        facts_collector.validate_downloaded_files()
        
        # Clean up any temporary files
        facts_collector.cleanup_temp_files()
        
    except Exception as e:
        logger.error(f"Error during data download: {e}")
        sys.exit(1)

def parse_data(config):
    """Parse downloaded data and calculate metrics."""
    logger.info("Parsing data and calculating metrics...")
    
    # Parse submissions file
    submissions_parser = SubmissionsParser(config)
    
    try:
        # Process submissions to create company index
        force_reprocess = config.get("parsing_settings", {}).get("force_reprocess", False)
        company_df = submissions_parser.process_submissions(force=force_reprocess)
        
        # Log some basic stats about the data
        logger.info(f"Processed company index with {len(company_df)} companies")
        
        # Get top companies by market cap (for informational purposes)
        top_companies = submissions_parser.get_top_companies_by_market_cap(company_df, n=10)
        logger.info("Top 10 companies by market cap:")
        for _, company in top_companies.iterrows():
            logger.info(f"{company['ticker']} ({company['name']}): ${company['market_cap'] / 1e9:.2f}B")
        
        # Parse XBRL facts files
        facts_parser = XBRLFactsParser(config)
        
        # Process facts with an optional limit
        company_limit = config.get("parsing_settings", {}).get("company_limit")
        metrics_df = facts_parser.process_all(limit=company_limit, force=force_reprocess)
        
        # Display some metrics
        logger.info(f"Extracted financial metrics for {len(metrics_df)} companies")
        
        # Show companies with highest quarterly EPS growth (for info purposes)
        if not metrics_df.empty and 'eps_qtr_growth' in metrics_df.columns:
            top_growth = metrics_df.dropna(subset=['eps_qtr_growth']).sort_values('eps_qtr_growth', ascending=False).head(5)
            if not top_growth.empty:
                logger.info("Top 5 companies by quarterly EPS growth:")
                for _, company in top_growth.iterrows():
                    growth_pct = company['eps_qtr_growth'] * 100 if pd.notna(company['eps_qtr_growth']) else 0
                    logger.info(f"{company['ticker']} ({company['name']}): {growth_pct:.1f}%")
        
    except Exception as e:
        logger.error(f"Error during data parsing: {e}")
        sys.exit(1)

def screen_stocks(config):
    """Screen stocks based on criteria."""
    logger.info("Screening stocks based on criteria...")
    # This will be implemented in Phase 4
    pass

def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description="Growth Stock Screener - Find high-growth stocks using SEC EDGAR data."
    )
    
    parser.add_argument(
        "--mode",
        required=True,
        choices=["download", "parse", "screen"],
        help="Operation mode: download SEC data, parse data, or screen stocks"
    )
    
    parser.add_argument(
        "--config",
        default=os.path.join("config", "config.json"),
        help="Path to configuration file (default: config/config.json)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Setup logging
    log_file = config.get("logging", {}).get("log_file", "logs/screener.log")
    log_level = getattr(logging, args.log_level)
    
    global logger
    logger = setup_logger("growth_stock_screener", log_file, log_level)
    
    logger.debug("Configuration loaded successfully.")
    
    # Ensure required directories exist
    ensure_directories(config)
    
    # Execute requested mode
    if args.mode == "download":
        download_data(config)
    elif args.mode == "parse":
        parse_data(config)
    elif args.mode == "screen":
        screen_stocks(config)

if __name__ == "__main__":
    import logging
    main()
