"""
SEC EDGAR Data Collector

Module for collecting financial data from SEC EDGAR database.
"""

import os
import json
import time
import logging
import pandas as pd
import requests
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SECDataCollector:
    """Collect financial data from SEC EDGAR database."""
    
    def __init__(self, config):
        """Initialize the SEC data collector."""
        self.config = config
        
        # 경로 설정
        data_paths = config.get("data_paths", {})
        self.processed_dir = data_paths.get("processed_data_dir", "data/processed")
        self.financial_data_dir = os.path.join(data_paths.get("raw_data_dir", "data/raw"), "sec_data")
        Path(self.financial_data_dir).mkdir(parents=True, exist_ok=True)
        
        # SEC API 설정
        self.headers = {
            'User-Agent': config.get("sec_settings", {}).get(
                "user_agent", 
                "Name (email@domain.com)"  # Replace with actual user agent in config
            )
        }
        self.base_url = "https://data.sec.gov/api"
        self.submissions_url = "https://data.sec.gov/submissions"
    
    def get_company_data(self, ticker: str) -> Dict:
        """
        Get comprehensive company data from SEC EDGAR.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dictionary with company data
        """
        cache_file = os.path.join(self.financial_data_dir, f"{ticker}_data.json")
        
        # 캐시 확인
        if os.path.exists(cache_file):
            file_age = time.time() - os.path.getmtime(cache_file)
            max_age = self.config.get("download_settings", {}).get("max_file_age_days", 30) * 86400
            
            if file_age < max_age:
                try:
                    with open(cache_file, "r") as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"Error reading cached data for {ticker}: {e}")
        
        try:
            # Get CIK number for the ticker
            cik = self._get_cik_from_ticker(ticker)
            if not cik:
                return {"ticker": ticker, "status": "error", "message": "CIK not found"}
            
            # Pad CIK to 10 digits as required by SEC API
            cik_padded = cik.zfill(10)
            
            # Get company submission information (metadata)
            company_info = self._get_company_submission(cik_padded)
            if not company_info:
                return {"ticker": ticker, "status": "error", "message": "Company information not found"}
            
            # Get latest filings data
            financials = self._get_financials(cik_padded)
            
            # Combine all data
            combined_data = {
                "ticker": ticker,
                "cik": cik,
                "info": company_info.get("info", {}),
                "financials": financials.get("financials", {}),
                "quarterly_financials": financials.get("quarterly_financials", {}),
                "balance_sheet": financials.get("balance_sheet", {}),
                "quarterly_balance_sheet": financials.get("quarterly_balance_sheet", {}),
                "cashflow": financials.get("cashflow", {}),
                "quarterly_cashflow": financials.get("quarterly_cashflow", {}),
                "last_updated": time.time()
            }
            
            # 캐시에 저장
            with open(cache_file, "w") as f:
                json.dump(combined_data, f)
                
            logger.info(f"Successfully downloaded SEC data for {ticker}")
            return combined_data
            
        except Exception as e:
            logger.error(f"Error downloading SEC data for {ticker}: {e}")
            return {"ticker": ticker, "status": "error", "message": str(e)}
    
    def _get_cik_from_ticker(self, ticker: str) -> str:
        """
        Get CIK number from ticker symbol.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            CIK number as string
        """
        try:
            # Use SEC's ticker to CIK mapping file
            response = requests.get("https://www.sec.gov/include/ticker.txt", headers=self.headers)
            if response.status_code != 200:
                logger.error(f"Failed to get ticker-to-CIK mapping: {response.status_code}")
                return None
                
            # Parse the response - format is ticker\tCIK\n
            mappings = response.text.strip().split('\n')
            for mapping in mappings:
                parts = mapping.split('\t')
                if len(parts) == 2 and parts[0].lower() == ticker.lower():
                    return parts[1]
            
            logger.warning(f"CIK not found for ticker {ticker}")
            return None
        except Exception as e:
            logger.error(f"Error getting CIK for {ticker}: {e}")
            return None
    
    def _get_company_submission(self, cik: str) -> Dict:
        """
        Get company submission data from SEC EDGAR.
        
        Args:
            cik: CIK number (10 digits, zero-padded)
            
        Returns:
            Dictionary with company submission data
        """
        try:
            url = f"{self.submissions_url}/CIK{cik}.json"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to get submission data for CIK {cik}: {response.status_code}")
                return None
                
            data = response.json()
            
            # Extract relevant company info
            info = {
                "name": data.get("name", ""),
                "sic": data.get("sic", ""),
                "sicDescription": data.get("sicDescription", ""),
                "exchanges": data.get("exchanges", ""),
                "stateOfIncorporation": data.get("stateOfIncorporation", ""),
                "fiscalYearEnd": data.get("fiscalYearEnd", ""),
            }
            
            return {"info": info, "filings": data.get("filings", {})}
            
        except Exception as e:
            logger.error(f"Error getting submission data for CIK {cik}: {e}")
            return None
    
    def _get_financials(self, cik: str) -> Dict:
        """
        Get financial data from SEC EDGAR.
        
        Args:
            cik: CIK number (10 digits, zero-padded)
            
        Returns:
            Dictionary with financial data
        """
        try:
            # Get annual reports (10-K)
            annual_url = f"{self.base_url}/fundamentals/CIK{cik}/annual.json"
            annual_response = requests.get(annual_url, headers=self.headers)
            
            # Get quarterly reports (10-Q)
            quarterly_url = f"{self.base_url}/fundamentals/CIK{cik}/quarterly.json"
            quarterly_response = requests.get(quarterly_url, headers=self.headers)
            
            financials_data = {}
            
            # Process annual data
            if annual_response.status_code == 200:
                annual_data = annual_response.json()
                
                # Extract key financial metrics
                financials_data["financials"] = self._extract_income_statement(annual_data)
                financials_data["balance_sheet"] = self._extract_balance_sheet(annual_data)
                financials_data["cashflow"] = self._extract_cashflow(annual_data)
            else:
                logger.warning(f"Failed to get annual financials for CIK {cik}: {annual_response.status_code}")
            
            # Process quarterly data
            if quarterly_response.status_code == 200:
                quarterly_data = quarterly_response.json()
                
                # Extract key financial metrics
                financials_data["quarterly_financials"] = self._extract_income_statement(quarterly_data)
                financials_data["quarterly_balance_sheet"] = self._extract_balance_sheet(quarterly_data)
                financials_data["quarterly_cashflow"] = self._extract_cashflow(quarterly_data)
            else:
                logger.warning(f"Failed to get quarterly financials for CIK {cik}: {quarterly_response.status_code}")
                
            return financials_data
            
        except Exception as e:
            logger.error(f"Error getting financial data for CIK {cik}: {e}")
            return {}
    
    def _extract_income_statement(self, data: Dict) -> Dict:
        """Extract income statement items from SEC data"""
        result = {}
        try:
            # Extract key income statement metrics
            if "units" in data:
                units = data["units"]
                
                # Revenue
                if "USD" in units.get("Revenue", []):
                    result["Total Revenue"] = {item["frame"]: item["val"] for item in units["Revenue"]}
                elif "USD" in units.get("RevenueFromContractWithCustomerExcludingAssessedTax", []):
                    result["Total Revenue"] = {item["frame"]: item["val"] for item in units["RevenueFromContractWithCustomerExcludingAssessedTax"]}
                
                # Net Income
                if "USD" in units.get("NetIncomeLoss", []):
                    result["Net Income"] = {item["frame"]: item["val"] for item in units["NetIncomeLoss"]}
                
                # EPS
                if "USD/shares" in units.get("EarningsPerShareBasic", []):
                    result["EPS (Basic)"] = {item["frame"]: item["val"] for item in units["EarningsPerShareBasic"]}
                elif "USD/shares" in units.get("EarningsPerShareBasicAndDiluted", []):
                    result["EPS (Basic)"] = {item["frame"]: item["val"] for item in units["EarningsPerShareBasicAndDiluted"]}
                
                # Operating Income
                if "USD" in units.get("OperatingIncomeLoss", []):
                    result["Operating Income"] = {item["frame"]: item["val"] for item in units["OperatingIncomeLoss"]}
        except Exception as e:
            logger.error(f"Error extracting income statement: {e}")
        
        return result
    
    def _extract_balance_sheet(self, data: Dict) -> Dict:
        """Extract balance sheet items from SEC data"""
        result = {}
        try:
            # Extract key balance sheet metrics
            if "units" in data:
                units = data["units"]
                
                # Total Assets
                if "USD" in units.get("Assets", []):
                    result["Total Assets"] = {item["frame"]: item["val"] for item in units["Assets"]}
                
                # Total Liabilities
                if "USD" in units.get("Liabilities", []):
                    result["Total Liabilities"] = {item["frame"]: item["val"] for item in units["Liabilities"]}
                
                # Total Stockholder Equity
                if "USD" in units.get("StockholdersEquity", []):
                    result["Total Stockholder Equity"] = {item["frame"]: item["val"] for item in units["StockholdersEquity"]}
                elif "USD" in units.get("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", []):
                    result["Total Stockholder Equity"] = {
                        item["frame"]: item["val"] 
                        for item in units["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
                    }
                
                # Long Term Debt
                if "USD" in units.get("LongTermDebt", []):
                    result["Long Term Debt"] = {item["frame"]: item["val"] for item in units["LongTermDebt"]}
        except Exception as e:
            logger.error(f"Error extracting balance sheet: {e}")
        
        return result
    
    def _extract_cashflow(self, data: Dict) -> Dict:
        """Extract cash flow items from SEC data"""
        result = {}
        try:
            # Extract key cash flow metrics
            if "units" in data:
                units = data["units"]
                
                # Operating Cash Flow
                if "USD" in units.get("NetCashProvidedByUsedInOperatingActivities", []):
                    result["Operating Cash Flow"] = {
                        item["frame"]: item["val"] 
                        for item in units["NetCashProvidedByUsedInOperatingActivities"]
                    }
                
                # Capital Expenditures
                if "USD" in units.get("PaymentsToAcquirePropertyPlantAndEquipment", []):
                    result["Capital Expenditures"] = {
                        item["frame"]: item["val"] 
                        for item in units["PaymentsToAcquirePropertyPlantAndEquipment"]
                    }
                
                # Free Cash Flow (can be calculated if needed)
        except Exception as e:
            logger.error(f"Error extracting cash flow: {e}")
        
        return result
    
    def calculate_growth_metrics(self, company_data: Dict) -> Dict:
        """
        Calculate growth metrics from SEC EDGAR data.
        """
        metrics = {
            "ticker": company_data.get("ticker"),
            "quarterly_eps_growth": 0,
            "annual_eps_cagr": 0,
            "revenue_growth": 0,
            "profit_margin": 0,
            "roe": 0,
            "debt_to_equity": 0
        }
        
        try:
            info = company_data.get("info", {})
            quarterly_financials = company_data.get("quarterly_financials", {})
            financials = company_data.get("financials", {})
            balance_sheet = company_data.get("balance_sheet", {})
            
            # 분기별 EPS 성장률 계산
            if "EPS (Basic)" in quarterly_financials:
                dates = sorted(list(quarterly_financials["EPS (Basic)"].keys()), reverse=True)
                if len(dates) >= 2:
                    current_eps = quarterly_financials["EPS (Basic)"][dates[0]]
                    prev_eps = quarterly_financials["EPS (Basic)"][dates[1]]
                    if prev_eps and prev_eps != 0:
                        metrics["quarterly_eps_growth"] = (current_eps - prev_eps) / abs(prev_eps)
            
            # 연간 EPS CAGR 계산
            if "EPS (Basic)" in financials:
                dates = sorted(list(financials["EPS (Basic)"].keys()), reverse=True)
                if len(dates) >= 3:
                    current_eps = financials["EPS (Basic)"][dates[0]]
                    past_eps = financials["EPS (Basic)"][dates[-1]]
                    years = len(dates) - 1
                    if past_eps and past_eps > 0 and current_eps > 0:
                        metrics["annual_eps_cagr"] = (current_eps / past_eps) ** (1/years) - 1
            
            # 매출 성장률 계산
            if "Total Revenue" in financials:
                dates = sorted(list(financials["Total Revenue"].keys()), reverse=True)
                if len(dates) >= 2:
                    current_revenue = financials["Total Revenue"][dates[0]]
                    prev_revenue = financials["Total Revenue"][dates[1]]
                    if prev_revenue and prev_revenue != 0:
                        metrics["revenue_growth"] = (current_revenue - prev_revenue) / prev_revenue
            
            # 수익률 계산
            if "Total Revenue" in financials and "Net Income" in financials:
                dates = sorted(list(financials["Total Revenue"].keys()), reverse=True)
                if dates and dates[0] in financials.get("Net Income", {}):
                    revenue = financials["Total Revenue"][dates[0]]
                    net_income = financials["Net Income"][dates[0]]
                    if revenue and revenue != 0:
                        metrics["profit_margin"] = net_income / revenue
            
            # ROE 계산
            if "Net Income" in financials and "Total Stockholder Equity" in balance_sheet:
                income_dates = sorted(list(financials["Net Income"].keys()), reverse=True)
                equity_dates = sorted(list(balance_sheet["Total Stockholder Equity"].keys()), reverse=True)
                
                if income_dates and equity_dates:
                    net_income = financials["Net Income"][income_dates[0]]
                    equity = balance_sheet["Total Stockholder Equity"][equity_dates[0]]
                    if equity and equity != 0:
                        metrics["roe"] = net_income / equity
            
            # 부채비율 계산
            if "Long Term Debt" in balance_sheet and "Total Stockholder Equity" in balance_sheet:
                dates = sorted(list(balance_sheet["Total Stockholder Equity"].keys()), reverse=True)
                if dates and dates[0] in balance_sheet.get("Long Term Debt", {}):
                    debt = balance_sheet["Long Term Debt"][dates[0]]
                    equity = balance_sheet["Total Stockholder Equity"][dates[0]]
                    if equity and equity != 0:
                        metrics["debt_to_equity"] = debt / equity
            
        except Exception as e:
            logger.error(f"Error calculating metrics for {company_data.get('ticker')}: {e}")
            
        return metrics
    
    def collect_all_data(self, companies: List[Dict], max_companies: int = None) -> List[Dict]:
        """
        Collect data for all companies in the list using SEC EDGAR.
        
        Args:
            companies: List of company dictionaries with ticker
            max_companies: Maximum number of companies to process
            
        Returns:
            List of companies enriched with financial metrics
        """
        logger.info(f"Collecting SEC data for up to {max_companies or 'all'} companies")
        
        # 처리할 회사 리스트 제한
        if max_companies:
            target_companies = companies[:max_companies]
        else:
            target_companies = companies
        
        processed_companies = []
        success_count = 0
        error_count = 0
        
        # 병렬 처리를 위한 ThreadPoolExecutor 설정
        max_workers = min(self.config.get("download_settings", {}).get("max_workers", 4), 10)
        
        # SEC API 요청 제한 (초당 10개 이하)
        delay = 0.1  # 초당 10개 요청 = 0.1초 간격
        
        def process_company(company):
            ticker = company.get("ticker")
            if not ticker:
                return company
            
            # 요청 사이 딜레이
            time.sleep(delay)
                
            # 회사 데이터 가져오기
            company_data = self.get_company_data(ticker)
            
            if company_data and "status" not in company_data:
                # 지표 계산
                metrics = self.calculate_growth_metrics(company_data)
                
                # 회사 정보 업데이트
                company.update({
                    "quarterly_eps_growth": metrics.get("quarterly_eps_growth", 0),
                    "annual_eps_cagr": metrics.get("annual_eps_cagr", 0),
                    "revenue_growth": metrics.get("revenue_growth", 0),
                    "profit_margin": metrics.get("profit_margin", 0),
                    "roe": metrics.get("roe", 0),
                    "debt_to_equity": metrics.get("debt_to_equity", 0),
                    "sec_cik": company_data.get("cik", "")
                })
                
                return {"success": True, "company": company}
            else:
                return {"success": False, "company": company, "error": company_data.get("message", "Unknown error")}
        
        # 병렬 처리
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_company = {executor.submit(process_company, company): company for company in target_companies}
            
            for future in future_to_company:
                try:
                    result = future.result()
                    if isinstance(result, dict) and "success" in result:
                        if result["success"]:
                            processed_companies.append(result["company"])
                            success_count += 1
                        else:
                            processed_companies.append(result["company"])
                            error_count += 1
                            ticker = result["company"].get("ticker", "unknown")
                            logger.debug(f"Error processing {ticker}: {result.get('error')}")
                    else:
                        processed_companies.append(result)
                except Exception as e:
                    company = future_to_company[future]
                    logger.error(f"Error processing {company.get('ticker', 'unknown')}: {e}")
                    processed_companies.append(company)
                    error_count += 1
        
        logger.info(f"Finished collecting SEC data: {success_count} successful, {error_count} failed")
        return processed_companies

def collect_sec_data(config):
    """
    Standalone function to collect SEC EDGAR data for companies.
    
    Args:
        config: Application configuration
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # 회사 리스트 로드
        processed_dir = config.get("data_paths", {}).get("processed_data_dir", "data/processed")
        companies_list_file = os.path.join(processed_dir, "companies_list.json")
        
        if not os.path.exists(companies_list_file):
            logger.error(f"Companies list file not found: {companies_list_file}")
            return False
        
        with open(companies_list_file, "r") as f:
            companies = json.load(f)
        
        logger.info(f"Loaded {len(companies)} companies for SEC data collection")
        
        # SEC 데이터 수집
        collector = SECDataCollector(config)
        company_limit = config.get("download_settings", {}).get("company_limit")
        
        enriched_companies = collector.collect_all_data(companies, company_limit)
        
        # 결과 저장
        output_file = os.path.join(processed_dir, "companies_sec_data.json")
        with open(output_file, "w") as f:
            json.dump(enriched_companies, f, indent=2)
        
        logger.info(f"Saved SEC data for {len(enriched_companies)} companies to {output_file}")
        
        # 주요 회사 리스트에 복사
        with open(companies_list_file, "w") as f:
            json.dump(enriched_companies, f, indent=2)
        
        return True
    except Exception as e:
        logger.error(f"Error collecting SEC data: {e}")
        import traceback
        traceback.print_exc()
        return False
