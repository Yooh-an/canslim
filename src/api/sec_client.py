"""
SEC EDGAR API Client

This module provides a client for accessing the SEC EDGAR API.
"""

import os
import time
import requests
from requests.exceptions import ChunkedEncodingError, RequestException
from typing import Dict, Optional, Any
import logging
from src.utils.logger import setup_logger

# Set up logger
logger = setup_logger("sec_client")

class SECClient:
    """
    Client for accessing SEC EDGAR API.
    
    This class handles communication with the SEC EDGAR API, including
    rate limiting and error handling.
    """
    
    # Base URLs
    BASE_URL = "https://www.sec.gov/Archives"
    SUBMISSIONS_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
    COMPANY_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"  # 공식 URL 형식
    COMPANY_FACTS_ALT_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/{cik}.json"  # 대체 URL 형식
    
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
        # 사용자 에이전트 형식 검증 및 개선
        if '@' in user_agent and not user_agent.startswith('Name ('):
            logger.warning(f"User-Agent format may not be optimal. Current: {user_agent}")
            logger.warning("SEC recommends format: 'Name (email)' instead of just email")
            # 자동으로 형식 개선
            if not user_agent.endswith(')'):
                user_agent = f"SEC API User ({user_agent})"
                logger.info(f"Auto-formatted User-Agent to: {user_agent}")
        
        # 기본 헤더 설정
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json"
        }
        
        # data.sec.gov 도메인용 헤더
        self.data_headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
            "Host": "data.sec.gov"
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
        
        # 도메인에 따라 적절한 기본 헤더 선택
        if "data.sec.gov" in url:
            base_headers = self.data_headers.copy()
        else:
            base_headers = self.headers.copy()
        
        # 추가 헤더 적용
        if headers:
            base_headers.update(headers)
        
        # 디버깅을 위한 로깅 추가
        logger.debug(f"Making request to {url} with headers: {base_headers}")
        
        # Initialize retry counter
        retries = 0
        
        while retries <= max_retries:
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=base_headers,
                    timeout=30
                )
                
                # 응답 상태 로깅 (디버깅용)
                logger.debug(f"Response status: {response.status_code} for {url}")
                response.raise_for_status()
                return response
            
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else 0
                
                # Only retry on server errors (5xx)
                if 500 <= status_code < 600 and retries < max_retries:
                    retries += 1
                    wait_time = self.rate_limit_delay * (2 ** retries)  # Exponential backoff
                    logger.warning(f"Request failed with status {status_code}, "
                                   f"retrying in {wait_time:.2f}s ({retries}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    raise
                    
            except (requests.exceptions.ConnectionError, 
                   requests.exceptions.Timeout) as e:
                if retries < max_retries:
                    retries += 1
                    wait_time = self.rate_limit_delay * (2 ** retries)
                    logger.warning(f"Network error: {e}, "
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
        
        logger.info(f"Downloading {url} to {output_path}")

        part_path = f"{output_path}.part"
        max_retries = 5
        chunk_size = 1024 * 1024

        for attempt in range(max_retries + 1):
            self._respect_rate_limit()

            existing_size = os.path.getsize(part_path) if os.path.exists(part_path) else 0
            headers = self.data_headers.copy() if "data.sec.gov" in url else self.headers.copy()
            if existing_size > 0:
                headers["Range"] = f"bytes={existing_size}-"
                logger.info(f"Resuming download from byte {existing_size}")

            try:
                with requests.get(url, headers=headers, timeout=(10, 120), stream=True) as response:
                    response.raise_for_status()

                    # If the server ignores Range and sends a full response, restart the temp file.
                    if existing_size > 0 and response.status_code == 200:
                        logger.warning("Server did not honor resume request; restarting download")
                        existing_size = 0

                    mode = "ab" if existing_size > 0 and response.status_code == 206 else "wb"
                    with open(part_path, mode) as f:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)

                os.replace(part_path, output_path)
                logger.info(f"Download complete: {output_path}")
                return output_path

            except (ChunkedEncodingError, RequestException, OSError) as e:
                if attempt >= max_retries:
                    logger.error(f"Download failed after {max_retries + 1} attempts: {e}")
                    raise

                wait_time = min(60, self.rate_limit_delay * (2 ** (attempt + 1)) + 2)
                logger.warning(
                    f"Download interrupted: {e}. Retrying in {wait_time:.2f}s "
                    f"({attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)

        return output_path
    
    def get_company_facts(self, cik: str) -> Dict[str, Any]:
        """
        Get company facts data for a company.
        
        Args:
            cik: Company CIK number (with or without leading zeros)
            
        Returns:
            Company facts data as dictionary
        """
        # Normalize CIK
        cik_numeric = str(cik).strip().replace('CIK', '').lstrip('0')
        if not cik_numeric:
            cik_numeric = '0'  # Keep at least one zero if all zeros
            
        # Ensure CIK is padded to 10 digits
        cik_padded = cik_numeric.zfill(10)
        
        logger.debug(f"Getting company facts for CIK: {cik} (normalized: {cik_numeric}, padded: {cik_padded})")
        
        # Try official URL format first
        try:
            url = self.COMPANY_FACTS_URL_TEMPLATE.format(cik=cik_padded)
            logger.info(f"Requesting company facts from: {url}")
            response = self._make_request(url)
            return response.json()
        except requests.exceptions.HTTPError as e:
            # If 404, try alternative URL format
            if e.response and e.response.status_code == 404:
                logger.info(f"Official URL format failed with 404, trying alternative format")
                alt_url = self.COMPANY_FACTS_ALT_URL_TEMPLATE.format(cik=cik_numeric)
                logger.info(f"Requesting company facts from alternative URL: {alt_url}")
                response = self._make_request(alt_url)
                return response.json()
            else:
                # Re-raise other errors
                raise
    
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
