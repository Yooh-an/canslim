#!/usr/bin/env python3
"""
Debug script for ticker mapping and company list generation.
"""

import os
import sys
import json
import glob

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.utils.ticker_mapper import TickerMapper
from src.utils.logger import setup_logger

# Set up logger
logger = setup_logger("debug_ticker_mapping")

def analyze_ticker_mapping():
    """Analyze ticker mapping file directly."""
    # Load configuration
    config_path = os.path.join("config", "config.json")
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return
    
    # Get mapping file path
    data_paths = config.get("data_paths", {})
    processed_dir = data_paths.get("processed_data_dir", "data/processed")
    mapping_file = os.path.join(processed_dir, "cik_ticker_mapping.csv")
    
    if not os.path.exists(mapping_file):
        logger.error(f"Mapping file does not exist: {mapping_file}")
        return
    
    # Analyze mapping file directly
    import pandas as pd
    df = pd.read_csv(mapping_file)
    
    logger.info(f"Mapping file has {len(df)} rows")
    logger.info(f"Columns: {df.columns.tolist()}")
    
    # Check CIK format
    cik_sample = df['cik'].astype(str).head(5).tolist()
    logger.info(f"CIK sample: {cik_sample}")
    
    # Check if CIKs are padded to 10 digits
    cik_lengths = df['cik'].astype(str).str.len().value_counts()
    logger.info(f"CIK lengths: {cik_lengths.to_dict()}")
    
    # Check if there are duplicates
    cik_dupes = df['cik'].duplicated().sum()
    ticker_dupes = df['ticker'].duplicated().sum()
    logger.info(f"Duplicate CIKs: {cik_dupes}, Duplicate tickers: {ticker_dupes}")
    
    # Compare with SEC ticker-CIK mapping URL directly
    logger.info("\nDownloading ticker mapping directly from SEC for comparison...")
    import requests
    headers = {}
    if "sec_api" in config and "user_agent" in config["sec_api"]:
        headers["User-Agent"] = config["sec_api"]["user_agent"]
    
    try:
        response = requests.get("https://www.sec.gov/include/ticker.txt", headers=headers)
        response.raise_for_status()
        
        # Process the mapping data (tab-separated values)
        mapping_data = []
        for line in response.text.split("\n"):
            if line.strip():
                try:
                    ticker, cik_str = line.strip().split("\t")
                    mapping_data.append((ticker.upper(), cik_str))
                except ValueError:
                    logger.warning(f"Invalid line: {line}")
        
        logger.info(f"Direct download has {len(mapping_data)} mappings")
        
        # Check a few known mappings
        test_tickers = ["AAPL", "MSFT", "GOOGL"]
        logger.info("\nChecking known mappings from direct download:")
        for ticker in test_tickers:
            matches = [item for item in mapping_data if item[0] == ticker]
            if matches:
                logger.info(f"Direct download: Ticker {ticker} -> CIK: {matches[0][1]}")
            else:
                logger.info(f"Direct download: Ticker {ticker} -> CIK: Not found")
    
    except Exception as e:
        logger.error(f"Error downloading ticker mapping directly: {e}")

def debug_company_json():
    """Debug companies.json file."""
    # Load configuration
    config_path = os.path.join("config", "config.json")
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return
    
    # Get companies.json path
    data_paths = config.get("data_paths", {})
    raw_dir = data_paths.get("raw_data_dir", "data/raw")
    companies_file = os.path.join(raw_dir, "submissions_extracted/companies.json")
    
    if not os.path.exists(companies_file):
        logger.error(f"Companies file does not exist: {companies_file}")
        # Check if the directory exists
        extracted_dir = os.path.join(raw_dir, "submissions_extracted")
        if os.path.exists(extracted_dir):
            files = os.listdir(extracted_dir)
            logger.info(f"Found {len(files)} files in extracted directory")
            if files:
                logger.info(f"Sample files: {files[:10]}")
        return
    
    # Load and analyze companies.json
    try:
        with open(companies_file, 'r') as f:
            companies_data = json.load(f)
        
        logger.info(f"Companies file has {len(companies_data)} companies")
        
        # Count companies with tickers
        with_tickers = sum(1 for company in companies_data.values() if company.get("tickers"))
        logger.info(f"Companies with tickers: {with_tickers}")
        
        # Sample some companies
        logger.info("\nSample companies:")
        sample_count = 0
        for cik, company in companies_data.items():
            if sample_count >= 5:
                break
            logger.info(f"CIK {cik}: Name: {company.get('name')}, Tickers: {company.get('tickers')}")
            sample_count += 1
    
    except Exception as e:
        logger.error(f"Error analyzing companies file: {e}")

if __name__ == "__main__":
    analyze_ticker_mapping()
    debug_company_json()
