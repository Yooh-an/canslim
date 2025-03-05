"""
Ticker to CIK mapping utility.

This module provides functionality to map SEC CIK numbers to stock ticker symbols.
"""

import os
import requests
import csv
import time
from typing import Dict, Optional, Tuple
import pandas as pd
from pathlib import Path

from src.utils.logger import setup_logger

# Set up logger
logger = setup_logger("ticker_mapper")

class TickerMapper:
    """
    Maps between SEC CIK numbers and stock ticker symbols.
    
    This class downloads and manages a mapping between SEC CIK numbers
    and stock ticker symbols from the SEC website.
    """
    
    # SEC ticker mapping URL
    SEC_TICKER_URL = "https://www.sec.gov/include/ticker.txt"
    
    def __init__(self, config):
        """
        Initialize the TickerMapper.
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        
        # Get paths from config
        data_paths = config.get("data_paths", {})
        self.processed_data_dir = data_paths.get("processed_data_dir", "data/processed")
        
        # Define mapping file path
        self.mapping_file = os.path.join(self.processed_data_dir, "cik_ticker_mapping.csv")
        
        # Ensure directory exists
        Path(self.processed_data_dir).mkdir(parents=True, exist_ok=True)
        
        # Initialize mapping dictionary
        self.cik_to_ticker = {}
        self.ticker_to_cik = {}
        
    def download_mapping(self, force: bool = False) -> bool:
        """
        Download the CIK to ticker mapping from SEC.
        
        Args:
            force: If True, download even if file exists
            
        Returns:
            True if download was successful, False otherwise
        """
        # Skip if file exists and not forced
        if os.path.exists(self.mapping_file) and not force:
            logger.info("Using existing ticker mapping file")
            self._load_mapping()
            return True
        
        logger.info("Downloading ticker mapping from SEC")
        
        try:
            # Configure headers for SEC request
            headers = {}
            if "sec_api" in self.config and "user_agent" in self.config["sec_api"]:
                headers["User-Agent"] = self.config["sec_api"]["user_agent"]
            
            # Download the file
            response = requests.get(self.SEC_TICKER_URL, headers=headers)
            response.raise_for_status()
            
            # Process the mapping data (tab-separated values)
            mapping_data = []
            for line in response.text.split("\n"):
                if line.strip():
                    try:
                        ticker, cik_str = line.strip().split("\t")
                        mapping_data.append({
                            "ticker": ticker.upper(),
                            "cik": cik_str.zfill(10)  # Pad CIK to 10 digits
                        })
                    except ValueError:
                        # Skip malformed lines
                        logger.warning(f"Skipping malformed line: {line}")
                        continue
            
            # Save to DataFrame and then to CSV
            df = pd.DataFrame(mapping_data)
            
            # Remove duplicate CIKs - keep the first occurrence
            if df['cik'].duplicated().any():
                dupes = df['cik'].duplicated().sum()
                logger.warning(f"Found {dupes} duplicate CIKs in ticker mapping, keeping first occurrence")
                df = df.drop_duplicates(subset=['cik'], keep='first')
            
            df.to_csv(self.mapping_file, index=False)
            
            logger.info(f"Downloaded {len(mapping_data)} ticker mappings, saved {len(df)} unique mappings")
            
            # Load the mapping into memory
            self._load_mapping()
            
            return True
            
        except Exception as e:
            logger.error(f"Error downloading ticker mapping: {e}")
            return False
    
    def _load_mapping(self) -> None:
        """Load the mapping from file into memory."""
        try:
            if not os.path.exists(self.mapping_file):
                logger.warning(f"Mapping file {self.mapping_file} does not exist")
                return
            
            df = pd.read_csv(self.mapping_file)
            
            # Ensure CIK is padded to 10 digits
            df['cik'] = df['cik'].astype(str).apply(lambda x: x.zfill(10))
            
            # Create dictionaries for lookups
            self.cik_to_ticker = dict(zip(df['cik'], df['ticker']))
            self.ticker_to_cik = dict(zip(df['ticker'], df['cik']))
            
            logger.info(f"Loaded {len(self.cik_to_ticker)} ticker mappings")
            
        except Exception as e:
            logger.error(f"Error loading ticker mapping: {e}")
    
    def get_ticker(self, cik: str) -> Optional[str]:
        """
        Get ticker for a CIK.
        
        Args:
            cik: CIK number (with or without leading zeros)
            
        Returns:
            Ticker symbol or None if not found
        """
        cik_padded = cik.zfill(10)
        return self.cik_to_ticker.get(cik_padded)
    
    def get_cik(self, ticker: str) -> Optional[str]:
        """
        Get CIK for a ticker.
        
        Args:
            ticker: Ticker symbol (case insensitive)
            
        Returns:
            CIK number or None if not found
        """
        ticker_upper = ticker.upper()
        return self.ticker_to_cik.get(ticker_upper)
    
    def enrich_companies_with_tickers(self, companies_data: Dict) -> Dict:
        """
        Add ticker symbols to companies data.
        
        Args:
            companies_data: Dictionary of company data
            
        Returns:
            Updated companies data with ticker symbols
        """
        # Make sure we have the mapping
        if not self.cik_to_ticker:
            self.download_mapping()
        
        # If mapping is still empty, return original data
        if not self.cik_to_ticker:
            logger.warning("No ticker mapping available, returning original data")
            return companies_data
        
        # Add tickers to companies data
        enriched_count = 0
        for cik, company in companies_data.items():
            ticker = self.get_ticker(cik)
            if ticker:
                if "tickers" not in company or not company["tickers"]:
                    company["tickers"] = [ticker]
                    enriched_count += 1
                elif ticker not in company["tickers"]:
                    company["tickers"].append(ticker)
                    enriched_count += 1
        
        logger.info(f"Enriched {enriched_count} companies with ticker symbols")
        return companies_data
