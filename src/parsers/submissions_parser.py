"""
SEC Submissions Parser

Module for parsing SEC submissions data and extracting company information.
"""

import os
import json
import zipfile
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

from utils.logger import setup_logger

# Set up logger
logger = setup_logger("submissions_parser")

class SubmissionsParser:
    """
    Parser for SEC submissions data.
    
    This class extracts company information from the SEC submissions file,
    creating indexes and lookups for efficient access.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the SubmissionsParser.
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        
        # Get data paths from config
        data_paths = config.get("data_paths", {})
        self.raw_data_dir = data_paths.get("raw_data_dir", "data/raw")
        self.processed_data_dir = data_paths.get("processed_data_dir", "data/processed")
        self.submissions_file = data_paths.get("submissions_file", "data/raw/submissions.zip")
        self.extracted_dir = os.path.join(self.raw_data_dir, "submissions_extracted")
        
        # Define output paths
        self.companies_index_file = os.path.join(self.processed_data_dir, "companies_index.parquet")
        
        # Ensure directories exist
        Path(self.processed_data_dir).mkdir(parents=True, exist_ok=True)
    
    def extract_submissions(self, force: bool = False) -> str:
        """
        Extract the submissions ZIP file if needed.
        
        Args:
            force: If True, extract even if the directory already exists
            
        Returns:
            Path to the extracted directory
        """
        # Check if the directory already exists and has the expected file
        companies_json = os.path.join(self.extracted_dir, "companies.json")
        if not force and os.path.exists(companies_json):
            logger.info(f"Using existing extracted submissions in {self.extracted_dir}")
            return self.extracted_dir
        
        # Ensure the output directory exists
        Path(self.extracted_dir).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Extracting submissions file to {self.extracted_dir}")
        try:
            with zipfile.ZipFile(self.submissions_file, 'r') as zip_ref:
                zip_ref.extractall(self.extracted_dir)
            
            logger.info("Submissions file extracted successfully")
            return self.extracted_dir
        except Exception as e:
            logger.error(f"Error extracting submissions file: {e}")
            raise
    
    def load_companies_data(self) -> Dict[str, Any]:
        """
        Load the companies data from the extracted submissions file.
        
        Returns:
            Dictionary of company data keyed by CIK
        """
        companies_file = os.path.join(self.extracted_dir, "companies.json")
        
        if not os.path.exists(companies_file):
            logger.info("Companies file not found, extracting submissions")
            self.extract_submissions()
            
            if not os.path.exists(companies_file):
                raise FileNotFoundError(f"Companies file not found at {companies_file}")
        
        logger.info("Loading companies data from JSON")
        try:
            with open(companies_file, 'r') as f:
                companies = json.load(f)
            
            logger.info(f"Loaded data for {len(companies)} companies")
            return companies
        except Exception as e:
            logger.error(f"Error loading companies data: {e}")
            raise
    
    def create_company_index(self, min_market_cap: Optional[float] = None) -> pd.DataFrame:
        """
        Create a structured index of company information.
        
        Args:
            min_market_cap: Minimum market capitalization filter
            
        Returns:
            DataFrame containing company information
        """
        logger.info("Creating company index")
        
        # Load the raw companies data
        companies_data = self.load_companies_data()
        
        # Initialize lists to hold data
        entries = []
        
        # Process each company
        for cik, company in companies_data.items():
            # Skip companies without tickers
            if not company.get("tickers") or len(company["tickers"]) == 0:
                continue
                
            # Apply market cap filter if provided
            market_cap = company.get("marketCap", 0)
            if min_market_cap is not None and market_cap < min_market_cap:
                continue
            
            # Extract base information
            entry = {
                "cik": cik.lstrip("0"),  # Remove leading zeros for numeric CIK
                "cik_padded": cik.zfill(10),  # Padded CIK for API calls
                "ticker": company["tickers"][0],  # Primary ticker
                "name": company.get("name", ""),
                "market_cap": market_cap,
                "sic": company.get("sic", ""),
                "industry": company.get("category", ""),
                "exchange": company.get("exchanges", [""])[0] if company.get("exchanges") else ""
            }
            
            # Add alternative tickers if any
            if len(company.get("tickers", [])) > 1:
                entry["alt_tickers"] = ",".join(company["tickers"][1:])
                
            entries.append(entry)
        
        # Create DataFrame
        df = pd.DataFrame(entries)
        
        # Add ticker lookup column (lowercase for case-insensitive lookups)
        if "ticker" in df.columns:
            df["ticker_lookup"] = df["ticker"].str.lower()
        
        logger.info(f"Created index with {len(df)} companies")
        return df
    
    def save_company_index(self, df: pd.DataFrame) -> str:
        """
        Save the company index to a Parquet file.
        
        Args:
            df: DataFrame containing company index
            
        Returns:
            Path to the saved file
        """
        logger.info(f"Saving company index to {self.companies_index_file}")
        
        # Ensure the directory exists
        Path(os.path.dirname(self.companies_index_file)).mkdir(parents=True, exist_ok=True)
        
        # Save to Parquet format
        df.to_parquet(self.companies_index_file, index=False, compression="snappy")
        
        logger.info(f"Company index saved with {len(df)} entries")
        return self.companies_index_file
    
    def process_submissions(self, force: bool = False) -> pd.DataFrame:
        """
        Process submissions data to create and save a company index.
        
        Args:
            force: If True, reprocess even if the index already exists
            
        Returns:
            DataFrame containing the company index
        """
        # Check if the index file already exists
        if not force and os.path.exists(self.companies_index_file):
            logger.info(f"Loading existing company index from {self.companies_index_file}")
            try:
                return pd.read_parquet(self.companies_index_file)
            except Exception as e:
                logger.warning(f"Error loading existing index, will recreate: {e}")
        
        # Extract submissions if needed
        self.extract_submissions(force=force)
        
        # Create and save the company index
        min_market_cap = self.config.get("screening_criteria", {}).get("min_market_cap")
        df = self.create_company_index(min_market_cap=min_market_cap)
        self.save_company_index(df)
        
        return df
    
    def lookup_by_ticker(self, df: pd.DataFrame, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Look up a company by ticker symbol.
        
        Args:
            df: Company index DataFrame
            ticker: Ticker symbol to look up
            
        Returns:
            Dictionary of company information or None if not found
        """
        ticker_lower = ticker.lower()
        matches = df[df["ticker_lookup"] == ticker_lower]
        
        if len(matches) == 0:
            return None
            
        # Convert the first match to a dictionary
        return matches.iloc[0].to_dict()
    
    def lookup_by_cik(self, df: pd.DataFrame, cik: str) -> Optional[Dict[str, Any]]:
        """
        Look up a company by CIK number.
        
        Args:
            df: Company index DataFrame
            cik: CIK number (with or without leading zeros)
            
        Returns:
            Dictionary of company information or None if not found
        """
        # Strip leading zeros for comparison
        cik_stripped = cik.lstrip("0")
        matches = df[df["cik"] == cik_stripped]
        
        if len(matches) == 0:
            return None
            
        # Convert the first match to a dictionary
        return matches.iloc[0].to_dict()
    
    def get_industry_groups(self, df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group companies by industry.
        
        Args:
            df: Company index DataFrame
            
        Returns:
            Dictionary of industry groups with lists of companies
        """
        industry_groups = {}
        
        for industry_name, group_df in df.groupby("industry"):
            if not industry_name:  # Skip empty industry names
                continue
                
            industry_groups[industry_name] = group_df.to_dict(orient="records")
        
        return industry_groups
    
    def get_top_companies_by_market_cap(self, df: pd.DataFrame, n: int = 100) -> pd.DataFrame:
        """
        Get the top N companies by market capitalization.
        
        Args:
            df: Company index DataFrame
            n: Number of companies to return
            
        Returns:
            DataFrame of top companies
        """
        return df.sort_values("market_cap", ascending=False).head(n)
