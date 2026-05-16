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
    
    # 2023 SEC API URLs - 개선된 엔드포인트 목록
    COMPANY_FACTS_ENDPOINTS = [
        "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",  # 표준 형식
        "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/Assets.json",  # Assets 개념
        "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/EarningsPerShareDiluted.json",  # EPS
        "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/Revenue.json",  # Revenue
        "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/NetIncomeLoss.json"  # Net Income
    ]
    
    # 잘 알려진 기업 CIK 목록 (테스트용)
    KNOWN_GOOD_CIKS = [
        "0000320193",  # Apple
        "0000789019",  # Microsoft
        "0001652044",  # Alphabet
        "0001018724",  # Amazon
        "0000027904",  # Bank of America
        "0000200406",  # Visa
        "0001326801",  # Facebook (Meta)
        "0000051143",  # JP Morgan Chase
        "0000200406",  # Visa Inc.
        "0001682852"   # Alibaba Group
    ]
    
    def __init__(self, sec_client: Optional[SECClient] = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the CompanyFactsCollector.
        
        Args:
            sec_client: Initialized SEC API client (optional)
            config: Application configuration dictionary (optional)
        """
        self.config = config or {}
        
        # Initialize SEC client if not provided
        if sec_client is None and config:
            sec_api_config = config.get('sec_api', {})
            user_agent = sec_api_config.get('user_agent', '')
            rate_limit_delay = sec_api_config.get('rate_limit_delay', 0.1)
            self.sec_client = SECClient(user_agent, rate_limit_delay)
        else:
            self.sec_client = sec_client
        
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
            # CIK 형식 처리
            cik_numeric = ''.join(filter(str.isdigit, cik)).lstrip('0')
            if not cik_numeric:
                cik_numeric = '0'
                
            # 10자리로 패딩
            cik_padded = cik_numeric.zfill(10)
            
            # 디버그 정보
            logger.debug(f"Original CIK: {cik}, Numeric: {cik_numeric}, Padded: {cik_padded}")
            
            # 출력 파일 경로 정의
            output_file = os.path.join(self.company_facts_dir, f"CIK{cik_padded}.json")
            
            # Add debug log for directory
            logger.debug(f"Output directory: {self.company_facts_dir}, exists: {os.path.exists(self.company_facts_dir)}")
            
            # 이미 존재하는 파일 처리 (no_data가 아닐 경우에만 스킵)
            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r') as f:
                        existing_data = json.load(f)
                    
                    if not existing_data.get('no_data', False):
                        logger.debug(f"Valid file already exists: {output_file}")
                        return output_file
                    else:
                        logger.debug(f"File exists but marked as no_data, trying again")
                except Exception as e:
                    logger.debug(f"Error checking existing file: {e}, will try downloading again")
            
            # 임시 파일 경로
            temp_file = os.path.join(self.temp_dir, f"CIK{cik_padded}.json.tmp")
            
            # 기본 회사 정보 구조 초기화
            company_data = {
                "cik": cik_padded,
                "entityName": "",
                "facts": {"us-gaap": {}}
            }
            
            # 성공 플래그
            success = False
            
            # 메인 엔드포인트에서 시도
            main_url = self.COMPANY_FACTS_ENDPOINTS[0].format(cik=cik_padded)
            try:
                logger.info(f"Downloading company facts from: {main_url}")
                response = self.sec_client._make_request(main_url)
                
                # 데이터 저장 및 검증
                with open(temp_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.debug(f"Wrote temp file: {temp_file}, size: {os.path.getsize(temp_file) if os.path.exists(temp_file) else 'not found'}")
                
                # JSON 형식 확인
                with open(temp_file, 'r') as f:
                    data = json.load(f)
                
                if 'entityName' in data and 'facts' in data:
                    logger.info(f"Successfully downloaded facts for {data.get('entityName')} (CIK {cik_padded})")
                    company_data = data
                    success = True
                else:
                    logger.warning(f"Downloaded file has unexpected format: missing entityName or facts")
                
            except requests.exceptions.HTTPError as http_err:
                status_code = getattr(http_err.response, 'status_code', 0)
                logger.warning(f"HTTP error {status_code} for {main_url}")
                
                # 404 오류면 대체 엔드포인트 시도
                if status_code == 404:
                    logger.info(f"Main URL returned 404, trying alternative concept endpoints...")
                    
                    # 대체 엔드포인트 (companyconcept API) 사용하여 개별 개념 데이터 수집
                    concept_data_collected = False
                    
                    for i, endpoint_template in enumerate(self.COMPANY_FACTS_ENDPOINTS[1:], 1):
                        concept_url = endpoint_template.format(cik=cik_padded)
                        
                        try:
                            logger.info(f"Trying alternative endpoint {i}: {concept_url}")
                            concept_response = self.sec_client._make_request(concept_url)
                            
                            # JSON으로 파싱
                            concept_data = concept_response.json()
                            
                            # 회사 이름 가져오기 (첫 성공한 요청에서)
                            if 'entityName' in concept_data and not company_data["entityName"]:
                                company_data["entityName"] = concept_data["entityName"]
                                if 'tickers' in concept_data:
                                    company_data["tickers"] = concept_data["tickers"]
                            
                            # 개념 데이터 추출
                            tag = endpoint_template.split('/')[-1].replace('.json', '')
                            
                            if 'tag' in concept_data:
                                # companyconcept 응답은 다른 구조를 가짐
                                if tag not in company_data["facts"]["us-gaap"]:
                                    company_data["facts"]["us-gaap"][tag] = {"units": {}}
                                
                                # 단위와 값 추출
                                for unit_type, values in concept_data.get('units', {}).items():
                                    if unit_type not in company_data["facts"]["us-gaap"][tag]["units"]:
                                        company_data["facts"]["us-gaap"][tag]["units"][unit_type] = []
                                    
                                    company_data["facts"]["us-gaap"][tag]["units"][unit_type].extend(values)
                            
                            concept_data_collected = True
                            
                        except Exception as concept_err:
                            logger.warning(f"Failed to get concept data from {concept_url}: {str(concept_err)}")
                    
                    if concept_data_collected:
                        success = True
                        logger.info(f"Successfully collected concept data for CIK {cik_padded}")
                
            except Exception as e:
                logger.error(f"Error downloading from {main_url}: {str(e)}")
            
            # 최종 결과 처리
            if success:
                # 통합된 데이터를 최종 파일에 저장
                with open(output_file, 'w') as f:
                    json.dump(company_data, f)
                
                logger.debug(f"Saved final output file: {output_file}")
                
                # Double-check file was created
                if os.path.exists(output_file):
                    logger.debug(f"Verified file exists: {output_file}, size: {os.path.getsize(output_file)}")
                else:
                    logger.error(f"Failed to create output file: {output_file}")
                
                return output_file
            else:
                # 실패한 경우 no_data 플래그 설정된 파일 생성
                logger.warning(f"Could not get valid data for CIK {cik_padded}")
                with open(output_file, 'w') as f:
                    json.dump({
                        "cik": cik_padded, 
                        "no_data": True, 
                        "reason": "Failed to get data from all endpoints"
                    }, f)
                
                return None
                    
        except Exception as e:
            logger.error(f"Unexpected error for CIK {cik}: {str(e)}")
            logger.error(f"Error stack trace:", exc_info=True)  # 전체 스택 트레이스 출력
            
            # 재시도 로직
            if retries < self.max_retries:
                wait_time = self.retry_delay * (2 ** retries)
                logger.info(f"Retrying in {wait_time}s... ({retries+1}/{self.max_retries})")
                time.sleep(wait_time)
                return self.download_company_facts(cik, retries + 1)
            
            # 최대 재시도 후에도 실패
            output_file = os.path.join(self.company_facts_dir, f"CIK{cik_padded}.json")
            with open(output_file, 'w') as f:
                json.dump({
                    "cik": cik_padded, 
                    "no_data": True, 
                    "reason": f"Error: {str(e)}"
                }, f)
            
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
            companies_file = os.path.join(
                self.config.get("data_paths", {}).get("processed_data_dir", "data/processed"), 
                "companies_list.json"
            )
            
            if os.path.exists(companies_file):
                logger.info(f"Loading companies from processed data: {companies_file}")
                try:
                    with open(companies_file, 'r') as f:
                        companies_data = json.load(f)
                    
                    # Already in list format
                    if isinstance(companies_data, list):
                        companies = companies_data
                        logger.info(f"Loaded {len(companies)} companies from processed list")
                    # Need to convert from dictionary
                    else:
                        companies = [{"cik": cik} for cik in companies_data.keys()]
                        logger.info(f"Converted {len(companies)} companies from dictionary format")
                except Exception as e:
                    logger.error(f"Error loading companies from {companies_file}: {e}")
                    companies = []
            else:
                # Traditional approach - get from submissions_extracted/companies.json
                submissions_file = os.path.join(
                    self.config.get("data_paths", {}).get("raw_data_dir", "data/raw"), 
                    "submissions_extracted/companies.json"
                )
                
                if not os.path.exists(submissions_file):
                    raise FileNotFoundError(f"Submissions file not found: {submissions_file}")
                
                with open(submissions_file, 'r') as f:
                    companies_data = json.load(f)
                    
                companies = [{"cik": cik} for cik in companies_data.keys()]
                logger.info(f"Loaded {len(companies)} companies from submissions file")
        
        # Add filtering to remove companies that likely don't have XBRL data
        if companies:
            # Log company list structure for verification
            if len(companies) > 0:
                logger.info(f"Sample company data: {companies[0]}")
            
            # Check ticker field and improve filtering logic
            has_ticker = []
            for comp in companies:
                # Check if ticker field exists (check various possible field names)
                if comp.get("tickers") or comp.get("ticker") or comp.get("Ticker") or comp.get("TICKER"):
                    has_ticker.append(comp)
            
            # Log results
            companies_with_tickers = len(has_ticker)
            companies_without_tickers = len(companies) - companies_with_tickers
            logger.info(f"Found {companies_with_tickers} companies with tickers out of {len(companies)} total")
            
            # Check whether to apply ticker filtering
            if self.config.get("download_settings", {}).get("filter_by_ticker", True):
                if companies_with_tickers > 0:
                    companies = has_ticker
                    logger.info(f"Applied ticker filter: {len(companies)} companies remaining")
                else:
                    # If no tickers found, keep original company list and output warning log
                    logger.warning("No companies with tickers found! Using original list.")
            else:
                logger.info("Ticker filtering disabled, using all companies")
            
            # When in test mode, use the sample CIKs but make sure they're not all zeros
            test_mode = self.config.get("download_settings", {}).get("test_mode", False)
            if test_mode:
                orig_count = len(companies)
                
                # Create test subset with actual CIKs
                test_companies = []
                for cik in self.KNOWN_GOOD_CIKS:
                    test_companies.append({"cik": cik})
                
                companies = test_companies
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
                output_file = os.path.join(self.company_facts_dir, f"CIK{str(cik).zfill(10)}.json")
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
