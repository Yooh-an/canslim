"""
SEC Company Facts Collector

Module for downloading company facts data from SEC API.
"""

import os
import time
import json
import glob
import concurrent.futures
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

from src.api.sec_client import SECClient
from src.utils.logger import setup_logger

# Set up logger
logger = setup_logger("facts_collector")

class CompanyFactsCollector:
    """
    Collector for SEC company facts data.
    
    This class handles downloading and initial processing of 
    company facts data from the SEC API.
    """
    
    # Whitelist of CIK for companies known to have XBRL data (optional, for testing)
    KNOWN_GOOD_CIKS = {"0000320193", "0000789019", "0001652044"}  # Example: Apple, Microsoft, Alphabet
    
    def __init__(self, sec_client: SECClient, config: Dict[str, Any]):
        """
        Initialize the CompanyFactsCollector.
        
        Args:
            sec_client: Initialized SEC API client
            config: Application configuration dictionary
        """
        self.sec_client = sec_client
        self.config = config
        
        # Get paths from config
        data_paths = config.get("data_paths", {})
        self.company_facts_dir = data_paths.get("company_facts_dir", "data/raw/company_facts")
        self.temp_dir = os.path.join(self.company_facts_dir, "temp")
        
        # Get download settings
        download_settings = config.get("download_settings", {})
        self.max_workers = download_settings.get("max_workers", 4)
        self.max_retries = download_settings.get("max_retries", 3)
        self.retry_delay = download_settings.get("retry_delay", 5)
        
        # Create directories
        Path(self.company_facts_dir).mkdir(parents=True, exist_ok=True)
        Path(self.temp_dir).mkdir(parents=True, exist_ok=True)
    
    def download_company_facts(self, cik: str, retries: int = 0) -> Optional[str]:
        """
        Download company facts data for a company.
        
        Args:
            cik: Company CIK number
            retries: Number of retries attempted
            
        Returns:
            Path to the downloaded file, or None if download failed
        """
        try:
            # Ensure CIK is padded to 10 digits
            cik_padded = cik.zfill(10)
            
            # Define output file path
            output_file = os.path.join(self.company_facts_dir, f"CIK{cik_padded}.json")
            
            # Skip if file already exists
            if os.path.exists(output_file):
                return output_file
            
            # Download to temporary location first
            temp_file = os.path.join(self.temp_dir, f"CIK{cik_padded}.json.tmp")
            
            # Download the file
            try:
                self.sec_client.download_company_facts(cik_padded, os.path.dirname(temp_file))
                
                # Move to final location
                os.rename(temp_file, output_file)
                
                return output_file
            except requests.exceptions.HTTPError as http_err:
                # Handle 404 errors (company data not available)
                if http_err.response.status_code == 404:
                    logger.info(f"Company facts not available for CIK {cik} (404 Not Found)")
                    
                    # Create empty placeholder file to prevent retries
                    with open(output_file, 'w') as f:
                        json.dump({"cik": cik_padded, "no_data": True, "reason": "404 Not Found"}, f)
                    
                    return output_file
                else:
                    raise  # Re-raise any other HTTP errors
                
        except Exception as e:
            logger.error(f"Error downloading facts for CIK {cik}: {e}")
            
            # Retry logic - only for non-404 errors
            if retries < self.max_retries and "404 Client Error" not in str(e):
                wait_time = self.retry_delay * (2 ** retries)  # Exponential backoff
                logger.info(f"Retrying download for CIK {cik} in {wait_time} seconds...")
                time.sleep(wait_time)
                return self.download_company_facts(cik, retries + 1)
            elif "404 Client Error" in str(e):
                # Create empty placeholder file for 404s
                output_file = os.path.join(self.company_facts_dir, f"CIK{cik_padded}.json")
                with open(output_file, 'w') as f:
                    json.dump({"cik": cik_padded, "no_data": True, "reason": "404 Not Found"}, f)
                return output_file
            
            return None
    
    def download_all_company_facts(self, companies: Optional[List[Dict[str, Any]]] = None, 
                                 limit: Optional[int] = None,
                                 force: bool = False) -> Dict[str, Any]:
        """
        Download facts for multiple companies.
        
        Args:
            companies: List of companies to download facts for
            limit: Optional limit on number of companies to process
            force: Force download even if file exists
            
        Returns:
            Dictionary of results with counts of successes and failures
        """
        # If companies not provided, load from companies.json
        if not companies:
            submissions_file = os.path.join(
                self.config.get("data_paths", {}).get("raw_data_dir", "data/raw"), 
                "submissions_extracted/companies.json"
            )
            
            if not os.path.exists(submissions_file):
                raise FileNotFoundError(f"Submissions file not found: {submissions_file}")
            
            with open(submissions_file, 'r') as f:
                companies_data = json.load(f)
                
            companies = [{"cik": cik} for cik in companies_data.keys()]
        
        # Add filtering to remove companies that likely don't have XBRL data
        if companies:
            # Filter for active companies with tickers
            filtered_companies = [comp for comp in companies if comp.get("tickers") or comp.get("ticker")]
            
            # Apply optional limit to companies with tickers
            if self.config.get("download_settings", {}).get("filter_by_ticker", True):
                companies_with_tickers = len(filtered_companies)
                companies_without_tickers = len(companies) - companies_with_tickers
                logger.info(f"Filtered out {companies_without_tickers} companies without tickers")
                companies = filtered_companies
            
            # Optionally limit to known good CIKs for testing
            test_mode = self.config.get("download_settings", {}).get("test_mode", False)
            if test_mode:
                orig_count = len(companies)
                companies = [comp for comp in companies if comp.get("cik").zfill(10) in self.KNOWN_GOOD_CIKS]
                logger.info(f"Test mode: Limited from {orig_count} to {len(companies)} known companies")
        
        # Apply limit if specified
        if limit and limit < len(companies):
            logger.info(f"Limiting download to {limit} companies (from {len(companies)} total)")
            companies = companies[:limit]
        
        logger.info(f"Downloading facts for {len(companies)} companies")
        
        # Set up tracking
        results = {
            "total": len(companies),
            "success": 0,
            "failed": 0,
            "skipped": 0
        }
        
        # Download in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            
            # Submit download tasks
            for company in companies:
                cik = company.get("cik", "")
                if not cik:
                    continue
                
                # Skip if file exists and not forced
                output_file = os.path.join(self.company_facts_dir, f"CIK{cik.zfill(10)}.json")
                if not force and os.path.exists(output_file):
                    results["skipped"] += 1
                    continue
                
                futures[executor.submit(self.download_company_facts, cik)] = cik
            
            # Process results
            for future in concurrent.futures.as_completed(futures):
                cik = futures[future]
                try:
                    result = future.result()
                    if result:
                        results["success"] += 1
                    else:
                        results["failed"] += 1
                except Exception as e:
                    logger.error(f"Error processing CIK {cik}: {e}")
                    results["failed"] += 1
        
        logger.info(f"Download complete: {results['success']} succeeded, "
                   f"{results['failed']} failed, {results['skipped']} skipped")
        
        return results
    
    def validate_downloaded_files(self) -> Dict[str, int]:
        """
        Validate the downloaded company facts files.
        
        Returns:
            Dictionary with counts of valid and invalid files
        """
        logger.info("Validating downloaded company facts files")
        
        results = {
            "valid": 0,
            "invalid": 0,
            "no_data": 0  # New counter for empty/placeholder files
        }
        
        # Get list of files
        files = glob.glob(os.path.join(self.company_facts_dir, "CIK*.json"))
        
        logger.info(f"Found {len(files)} company facts files")
        
        # Validate each file
        for file_path in files:
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # Check if this is a placeholder for a 404
                if data.get("no_data") == True:
                    results["no_data"] += 1
                    continue
                
                # Check if it has minimal required fields
                if "cik" in data and "entityName" in data:
                    results["valid"] += 1
                else:
                    results["invalid"] += 1
                    logger.warning(f"Invalid file content: {file_path}")
                    
            except Exception as e:
                results["invalid"] += 1
                logger.error(f"Error validating file {file_path}: {e}")
        
        logger.info(f"Validation complete: {results['valid']} valid, " 
                   f"{results['invalid']} invalid, {results['no_data']} no data available")
        return results
    
    def cleanup_temp_files(self) -> int:
        """
        Clean up temporary files.
        
        Returns:
            Number of files removed
        """
        logger.info("Cleaning up temporary files")
        
        # Get list of temporary files
        files = glob.glob(os.path.join(self.temp_dir, "*.tmp"))
        
        # Remove each file
        removed = 0
        for file_path in files:
            try:
                os.remove(file_path)
                removed += 1
            except Exception as e:
                logger.error(f"Error removing file {file_path}: {e}")
        
        logger.info(f"Cleanup complete: {removed} files removed")
        return removed
