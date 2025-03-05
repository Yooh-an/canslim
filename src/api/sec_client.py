"""
SEC EDGAR API Client

This module provides a client for accessing the SEC EDGAR API.
"""

import os
import time
import requests
from typing import Dict, Optional, Any
import logging

class SECClient:
    """
    Client for accessing SEC EDGAR API.
    
    This class handles communication with the SEC EDGAR API, including
    rate limiting and error handling.
    """
    
    # Base URLs
    BASE_URL = "https://www.sec.gov/Archives"
    SUBMISSIONS_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
    COMPANY_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    
    def __init__(self, user_agent: str, rate_limit_delay: float = 0.1):
        """
        Initialize the SEC API client.
        
        Args:
            user_agent: User-Agent header value for API requests
            rate_limit_delay: Delay between API requests in seconds
        """
        if not user_agent:
            raise ValueError("User-Agent is required for SEC API requests")
        
        self.user_agent = user_agent
        self.rate_limit_delay = rate_limit_delay
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "www.sec.gov"
        }
        self.last_request_time = 0
        
    def _respect_rate_limit(self) -> None:
        """Ensure rate limit is respected by adding delay if necessary."""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last_request
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _make_request(self, url: str, method: str = "GET", 
                    headers: Optional[Dict[str, str]] = None,
                    max_retries: int = 3) -> requests.Response:
        """
        Make a request to the SEC API with rate limiting and retry logic.
        
        Args:
            url: URL to request
            method: HTTP method to use
            headers: Additional headers to add to the request
            max_retries: Maximum number of retry attempts
            
        Returns:
            Response object
            
        Raises:
            requests.exceptions.RequestException: If request fails after retries
        """
        # Respect rate limit
        self._respect_rate_limit()
        
        # Prepare headers
        request_headers = self.headers.copy()
        if headers:
            request_headers.update(headers)
        
        # Initialize retry counter
        retries = 0
        
        while retries <= max_retries:
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=request_headers,
                    timeout=30
                )
                response.raise_for_status()
                return response
            
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else 0
                
                # Only retry on server errors (5xx)
                if 500 <= status_code < 600 and retries < max_retries:
                    retries += 1
                    wait_time = self.rate_limit_delay * (2 ** retries)  # Exponential backoff
                    logging.warning(f"Request failed with status {status_code}, "
                                   f"retrying in {wait_time:.2f}s ({retries}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    raise
                    
            except (requests.exceptions.ConnectionError, 
                   requests.exceptions.Timeout) as e:
                if retries < max_retries:
                    retries += 1
                    wait_time = self.rate_limit_delay * (2 ** retries)
                    logging.warning(f"Network error: {e}, "
                                  f"retrying in {wait_time:.2f}s ({retries}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    raise
        
        raise requests.exceptions.RequestException(
            f"Request to {url} failed after {max_retries} retries"
        )
    
    def download_file(self, url: str, output_path: str) -> str:
        """
        Download a file from the SEC API.
        
        Args:
            url: URL to download from
            output_path: Path to save the file
            
        Returns:
            Path to the downloaded file
        """
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # Download the file
        logging.info(f"Downloading {url} to {output_path}")
        
        response = self._make_request(url)
        
        # Save file
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logging.info(f"Download complete: {output_path}")
        return output_path
    
    def get_company_facts(self, cik: str) -> Dict[str, Any]:
        """
        Get company facts data for a company.
        
        Args:
            cik: Company CIK number (with or without leading zeros)
            
        Returns:
            Company facts data as dictionary
        """
        # Ensure CIK is padded to 10 digits
        cik_padded = cik.zfill(10)
        
        # Build URL
        url = self.COMPANY_FACTS_URL_TEMPLATE.format(cik=cik_padded)
        
        # Make request
        response = self._make_request(url)
        
        # Return data
        return response.json()
    
    def download_company_facts(self, cik: str, output_dir: str) -> str:
        """
        Download company facts data to a file.
        
        Args:
            cik: Company CIK number (with or without leading zeros)
            output_dir: Directory to save the file
            
        Returns:
            Path to the downloaded file
        """
        # Ensure CIK is padded to 10 digits
        cik_padded = cik.zfill(10)
        
        # Build URL
        url = self.COMPANY_FACTS_URL_TEMPLATE.format(cik=cik_padded)
        
        # Define output path
        output_path = os.path.join(output_dir, f"CIK{cik_padded}.json")
        
        # Download file
        return self.download_file(url, output_path)
