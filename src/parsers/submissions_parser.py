"""
SEC Submissions Parser

Module for parsing SEC submissions data and creating company index.
"""

import os
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional
import glob

from src.utils.logger import setup_logger
from src.utils.ticker_mapper import TickerMapper

# Set up logger
logger = setup_logger("submissions_parser")

class SubmissionsParser:
    """
    Parser for SEC submissions data.
    
    This class handles parsing and indexing of the submissions data to create
    a structured company index with key metadata.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the SubmissionsParser.
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        
        # Get paths from config
        data_paths = config.get("data_paths", {})
        self.raw_data_dir = data_paths.get("raw_data_dir", "data/raw")
        self.processed_data_dir = data_paths.get("processed_data_dir", "data/processed")
        self.submissions_file = data_paths.get("submissions_file", "data/raw/submissions.zip")
        self.extracted_dir = os.path.join(self.raw_data_dir, "submissions_extracted")
        
        # Define output files
        self.companies_index_file = os.path.join(self.processed_data_dir, "companies_index.parquet")
        
        # Ensure directories exist
        Path(self.processed_data_dir).mkdir(parents=True, exist_ok=True)
    
    def create_company_index(self, force: bool = False) -> pd.DataFrame:
        """
        Create a company index from submissions data.
        
        Args:
            force: If True, recreate index even if it exists
            
        Returns:
            DataFrame with company index
        """
        refresh_tickers = self.config.get("ticker_mapping", {}).get("force_refresh_on_cached_companies", False)

        # Skip if index exists and not forced. When ticker refresh is enabled, rebuild
        # the index so cached companies.json receives the latest CIK/ticker mapping.
        if os.path.exists(self.companies_index_file) and not force and not refresh_tickers:
            logger.info("Using existing company index")
            return pd.read_parquet(self.companies_index_file)
        
        # Check if extracted submissions exist
        if not os.path.exists(self.extracted_dir):
            raise FileNotFoundError(f"Extracted submissions not found: {self.extracted_dir}")
        
        logger.info(f"Using existing extracted submissions in {self.extracted_dir}")
        
        # Create company index
        logger.info("Creating company index")
        
        # Load companies.json
        companies_json = os.path.join(self.extracted_dir, "companies.json")
        if not os.path.exists(companies_json):
            raise FileNotFoundError(f"Companies data not found: {companies_json}")
        
        logger.info("Loading companies data from JSON")
        with open(companies_json, 'r') as f:
            companies_data = json.load(f)
        
        logger.info(f"Loaded data for {len(companies_data)} companies")

        if refresh_tickers:
            before = json.dumps(companies_data, sort_keys=True)
            ticker_mapper = TickerMapper(self.config)
            ticker_mapper.download_mapping(force=True)
            companies_data = ticker_mapper.enrich_companies_with_tickers(companies_data)
            if before != json.dumps(companies_data, sort_keys=True):
                with open(companies_json, 'w') as f:
                    json.dump(companies_data, f, indent=2)
                logger.info("Refreshed companies.json ticker mappings before indexing")
        
        # Create DataFrame from companies data
        companies = []
        for cik, data in companies_data.items():
            # Get ticker if available, otherwise empty string
            ticker = data.get("tickers", [""])[0] if data.get("tickers") else ""
            
            # Only include companies with tickers
            if ticker:
                # Ensure market_cap is present (use 0 if not)
                market_cap = data.get("marketCap", 0)
                if market_cap is None:  # Handle None value explicitly
                    market_cap = 0
                
                companies.append({
                    "cik": cik,
                    "ticker": ticker,
                    "name": data.get("name", ""),
                    "sic": data.get("sic", ""),
                    "category": data.get("category", ""),
                    "market_cap": market_cap  # Ensure this is a number
                })
        
        # Convert to DataFrame
        df = pd.DataFrame(companies)
        
        logger.info(f"Created index with {len(df)} companies")
        
        # Save to Parquet
        logger.info(f"Saving company index to {self.companies_index_file}")
        df.to_parquet(self.companies_index_file, index=False)
        logger.info(f"Company index saved with {len(df)} entries")
        
        return df
    
    def process_submissions(self, force: bool = False) -> pd.DataFrame:
        """Backward-compatible alias for creating the company index."""
        return self.create_company_index(force=force)

    def get_tickers_list(self) -> List[str]:
        """
        Get a list of all ticker symbols in the index.
        
        Returns:
            List of ticker symbols
        """
        if not os.path.exists(self.companies_index_file):
            self.create_company_index()
        
        df = pd.read_parquet(self.companies_index_file)
        return df["ticker"].unique().tolist()
