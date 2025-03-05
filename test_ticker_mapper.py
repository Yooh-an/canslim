#!/usr/bin/env python3
"""
Test script for ticker mapper functionality.
"""

import os
import sys
import json

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.utils.ticker_mapper import TickerMapper
from src.utils.logger import setup_logger

# Set up logger
logger = setup_logger("test_ticker_mapper")

def main():
    """Main function to test ticker mapper."""
    # Load configuration
    config_path = os.path.join("config", "config.json")
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return
    
    # Create ticker mapper
    mapper = TickerMapper(config)
    
    # Download mapping
    logger.info("Downloading ticker mapping...")
    mapper.download_mapping(force=True)
    
    # Test some lookups
    test_ciks = ["0000320193", "0000789019", "0001652044"]  # Apple, Microsoft, Alphabet
    test_tickers = ["AAPL", "MSFT", "GOOGL"]
    
    logger.info("Testing CIK to ticker mapping:")
    for cik in test_ciks:
        ticker = mapper.get_ticker(cik)
        logger.info(f"CIK {cik} -> Ticker: {ticker}")
    
    logger.info("\nTesting ticker to CIK mapping:")
    for ticker in test_tickers:
        cik = mapper.get_cik(ticker)
        logger.info(f"Ticker {ticker} -> CIK: {cik}")
    
    # List first 10 mappings
    logger.info("\nFirst 10 CIK-ticker mappings:")
    items = list(mapper.cik_to_ticker.items())[:10]
    for cik, ticker in items:
        logger.info(f"CIK {cik} -> Ticker: {ticker}")

if __name__ == "__main__":
    main()
