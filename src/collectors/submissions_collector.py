"""
SEC Submissions Collector

Module for downloading and processing SEC submissions data.
"""

import os
import time
import json
import zipfile
from pathlib import Path
from typing import Dict, List, Any, Optional
import glob

from src.api.sec_client import SECClient
from src.utils.logger import setup_logger
from src.utils.ticker_mapper import TickerMapper  # Import the new mapper

# Set up logger
logger = setup_logger("submissions_collector")

class SubmissionsCollector:
    """
    Collector for SEC submissions data.
    
    This class handles downloading and initial processing of the
    SEC submissions bulk file.
    """
    
    def __init__(self, sec_client: SECClient, config: Dict[str, Any]):
        """
        Initialize the SubmissionsCollector.
        
        Args:
            sec_client: Initialized SEC API client
            config: Application configuration dictionary
        """
        self.sec_client = sec_client
        self.config = config
        
        # Get paths from config
        data_paths = config.get("data_paths", {})
        self.raw_data_dir = data_paths.get("raw_data_dir", "data/raw")
        self.submissions_file = data_paths.get("submissions_file", "data/raw/submissions.zip")
        self.extracted_dir = os.path.join(self.raw_data_dir, "submissions_extracted")
        
        # Create directories
        Path(self.raw_data_dir).mkdir(parents=True, exist_ok=True)
        
    def download_submissions(self) -> str:
        """
        Download the SEC submissions bulk file.
        
        Returns:
            Path to the downloaded file
        """
        logger.info("Downloading SEC submissions file")
        
        # Create directory if it doesn't exist
        Path(os.path.dirname(self.submissions_file)).mkdir(parents=True, exist_ok=True)
        
        # Download the file
        self.sec_client.download_file(self.sec_client.SUBMISSIONS_URL, self.submissions_file)
        
        logger.info(f"Submissions file downloaded to {self.submissions_file}")
        return self.submissions_file
    
    def extract_submissions(self) -> str:
        """
        Extract the submissions ZIP file.
        
        Returns:
            Path to the extracted directory
        """
        logger.info(f"Extracting submissions file to {self.extracted_dir}")
        
        # Create directory if it doesn't exist
        Path(self.extracted_dir).mkdir(parents=True, exist_ok=True)
        
        # Extract the file
        with zipfile.ZipFile(self.submissions_file, 'r') as zip_ref:
            zip_ref.extractall(self.extracted_dir)
        
        logger.info("Submissions file extracted successfully")
        return self.extracted_dir
    
    def process_submissions_file(self) -> Dict[str, Any]:
        """
        Process the extracted submissions files to create a companies.json file.
        """
        logger.info("Processing submissions files")
        
        # Find all JSON files in the extracted directory (these are company facts files)
        json_files = glob.glob(os.path.join(self.extracted_dir, "**/*.json"), recursive=True)
        logger.info(f"Found {len(json_files)} JSON files in extracted directory")
        
        # Initialize empty companies data
        companies_data = {}
        
        # Filter out companies.json itself if it exists
        json_files = [f for f in json_files if os.path.basename(f) != "companies.json"]
        
        # Process all valid company facts files
        processed_count = 0
        for json_file in json_files:
            try:
                with open(json_file, 'r') as f:
                    file_data = json.load(f)
                
                # Extract company info from the facts files
                if isinstance(file_data, dict) and "cik" in file_data and "entityName" in file_data:
                    # Get CIK and ensure it's padded to 10 digits
                    cik = str(file_data.get("cik", "")).zfill(10)
                    name = file_data.get("entityName", "")
                    
                    # Add to companies data
                    if cik not in companies_data:
                        companies_data[cik] = {
                            "name": name,
                            "tickers": [],
                            "exchanges": [],
                            "sic": "",
                            "category": "",
                            "marketCap": 0
                        }
                        processed_count += 1
                    
            except Exception as e:
                logger.warning(f"Error processing file {json_file}: {e}")
        
        logger.info(f"Successfully processed {processed_count} company files")
        
        # Add ticker symbols using the ticker mapper
        ticker_mapper = TickerMapper(self.config)
        # Force download to make sure we have the latest ticker mappings
        ticker_mapper.download_mapping(force=True)
        companies_data = ticker_mapper.enrich_companies_with_tickers(companies_data)
        
        # Count companies with tickers (for logging)
        companies_with_tickers = sum(1 for company in companies_data.values() 
                                   if company.get("tickers") and len(company.get("tickers")) > 0)
        logger.info(f"Enriched {companies_with_tickers} companies with ticker symbols")
        
        # Save companies data to companies.json
        companies_json_path = os.path.join(self.extracted_dir, "companies.json")
        with open(companies_json_path, 'w') as f:
            json.dump(companies_data, f, indent=2)
        
        logger.info(f"Created companies index with {len(companies_data)} companies")
        return companies_data
    
    def get_company_list(self, min_market_cap: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Get a list of companies from the submissions file.
        """
        logger.info("Generating company list from submissions file")
        
        # Extract submissions if needed
        self.extract_submissions()
        
        # Always process submissions file to ensure we have the latest data
        logger.info("Processing submissions file to generate company data...")
        companies_data = self.process_submissions_file()
        
        # Log the number of companies found for debugging
        logger.info(f"Processing found {len(companies_data)} companies")
        
        # Create list of companies meeting criteria
        companies_list = []
        ticker_count = 0
        
        for cik, company in companies_data.items():
            # Count companies with tickers for debugging
            if company.get("tickers"):
                ticker_count += 1
                
            # Skip companies without tickers
            if not company.get("tickers"):
                continue
            
            # Apply market cap filter if provided
            if min_market_cap is not None and company.get("marketCap", 0) < min_market_cap:
                continue
            
            # Add to list
            companies_list.append({
                "cik": cik,
                "name": company.get("name", ""),
                "ticker": company.get("tickers", [""])[0],
                "market_cap": company.get("marketCap", 0),
                "sic": company.get("sic", ""),
                "category": company.get("category", "")
            })
        
        logger.info(f"Found {ticker_count} companies with tickers, {len(companies_list)} meeting criteria")
        return companies_list
