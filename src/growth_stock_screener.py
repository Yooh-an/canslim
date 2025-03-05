#!/usr/bin/env python3
"""
Growth Stock Screener

A command-line tool for screening growth stocks using SEC EDGAR data.
"""

import argparse
import json
import os
import sys
import logging
import pandas as pd
from pathlib import Path

from src.utils.logger import setup_logger
from src.utils.directory import ensure_directories
from src.api.sec_client import SECClient
from src.collectors.submissions_collector import SubmissionsCollector
from src.collectors.facts_collector import CompanyFactsCollector
from src.parsers.submissions_parser import SubmissionsParser
from src.parsers.facts_parser import XBRLFactsParser

def load_config(config_path):
    """Load configuration from JSON file."""
    try:
        with open(config_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        logger.error(f"Config file '{config_path}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.error(f"Config file '{config_path}' is not valid JSON.")
        sys.exit(1)

def download_data(config):
    """Download data from SEC EDGAR."""
    logger.info("Downloading data from SEC EDGAR...")
    
    # Initialize SEC API client
    user_agent = config.get("sec_api", {}).get("user_agent")
    if not user_agent:
        logger.error("User-Agent must be provided in config.json under sec_api.user_agent")
        sys.exit(1)
    
    rate_limit = config.get("sec_api", {}).get("rate_limit_delay", 0.1)
    sec_client = SECClient(user_agent=user_agent, rate_limit_delay=rate_limit)
    
    # Download submissions data
    submissions_collector = SubmissionsCollector(sec_client, config)
    submissions_file = submissions_collector.download_submissions()
    
    # Extract active companies
    try:
        min_market_cap = config.get("screening_criteria", {}).get("min_market_cap")
        companies = submissions_collector.get_company_list(min_market_cap)
        logger.info(f"Found {len(companies)} companies meeting criteria")
        
        # Save list of companies for later use
        companies_file = os.path.join(config.get("data_paths", {}).get("processed_data_dir", 
                                                                      "data/processed"), 
                                     "companies_list.json")
        Path(os.path.dirname(companies_file)).mkdir(parents=True, exist_ok=True)
        
        with open(companies_file, 'w') as f:
            json.dump(companies, f)
        
        logger.info(f"Saved company list to {companies_file}")
        
        # Download company facts data
        facts_collector = CompanyFactsCollector(sec_client, config)
        
        # Set limit if specified
        company_limit = config.get("download_settings", {}).get("company_limit")
        force_download = config.get("download_settings", {}).get("force_download", False)
        
        # Start the download process
        results = facts_collector.download_all_company_facts(
            limit=company_limit, 
            force=force_download
        )
        
        # Validate downloaded files
        facts_collector.validate_downloaded_files()
        
        # Clean up any temporary files
        facts_collector.cleanup_temp_files()
        
    except Exception as e:
        logger.error(f"Error during data download: {e}")
        sys.exit(1)

def parse_data(config):
    """Parse downloaded data and calculate metrics."""
    logger.info("Parsing data and calculating metrics...")
    
    try:
        # Create company index
        submissions_parser = SubmissionsParser(config)
        companies_df = submissions_parser.create_company_index()
        
        logger.info(f"Processed company index with {len(companies_df)} companies")
        
        # Parse company facts
        facts_parser = XBRLFactsParser(config)
        metrics_df = facts_parser.process_all()
        
        logger.info(f"Processed financial metrics for {len(metrics_df)} companies")
        
        # Save a combined list of companies with metrics to JSON
        # Only try to merge if both DataFrames have data
        if not companies_df.empty and not metrics_df.empty:
            # Check if 'cik' column exists in metrics_df
            if 'cik' in metrics_df.columns:
                combined_df = pd.merge(companies_df, metrics_df, on='cik', how='inner')
                logger.info(f"Combined data for {len(combined_df)} companies")
                companies_list = combined_df.to_dict(orient='records')
            else:
                logger.warning("Column 'cik' not found in metrics dataframe, using company data only")
                companies_list = companies_df.to_dict(orient='records')
        elif not companies_df.empty:
            logger.warning("No metrics data available, using company data only")
            companies_list = companies_df.to_dict(orient='records')
        elif not metrics_df.empty:
            logger.warning("No company index data available, using metrics data only")
            companies_list = metrics_df.to_dict(orient='records')
        else:
            logger.warning("No data available in either company index or metrics")
            companies_list = []
        
        # Save to JSON
        output_dir = os.path.dirname(config.get("data_paths", {}).get("output_file", "data/processed/results.csv"))
        os.makedirs(output_dir, exist_ok=True)
        
        companies_list_file = os.path.join(output_dir, "companies_list.json")
        with open(companies_list_file, 'w') as f:
            json.dump(companies_list, f, indent=2)
        
        logger.info(f"Saved combined data for {len(companies_list)} companies to {companies_list_file}")
        
        return True
    except Exception as e:
        logger.error(f"Error during data parsing: {e}")
        import traceback
        traceback.print_exc()  # 자세한 오류 추적 출력
        return False

def screen_stocks(config):
    """Screen stocks based on criteria."""
    logger.info("Screening stocks based on criteria...")
    
    try:
        # 처리된 회사 데이터 로드
        processed_dir = config.get("data_paths", {}).get("processed_data_dir", "data/processed")
        companies_list_file = os.path.join(processed_dir, "companies_list.json")
        
        if not os.path.exists(companies_list_file):
            logger.error(f"Companies list file not found: {companies_list_file}")
            print(f"Error: Companies list file not found at {companies_list_file}")
            print("Please run the parse mode first to generate the required data.")
            return
        
        with open(companies_list_file, 'r') as f:
            companies = json.load(f)
        
        logger.info(f"Loaded data for {len(companies)} companies")
        print(f"Loaded data for {len(companies)} companies")
        
        # 스크리닝 조건 가져오기
        criteria = config.get("screening_criteria", {})
        
        # 스크리닝 기준 출력
        print("\nScreening Criteria:")
        print(f"- Quarterly EPS Growth: ≥ {criteria.get('quarterly_eps_growth', 0.20) * 100:.1f}%")
        print(f"- Annual EPS Growth (CAGR): ≥ {criteria.get('annual_eps_cagr', 0.20) * 100:.1f}%")
        print(f"- Revenue Growth: ≥ {criteria.get('revenue_growth', 0.15) * 100:.1f}%")
        print(f"- Profit Margin: ≥ {criteria.get('profit_margin', 0.10) * 100:.1f}%")
        print(f"- Return on Equity: ≥ {criteria.get('roe', 0.15) * 100:.1f}%")
        print(f"- Debt to Equity: ≤ {criteria.get('debt_to_equity', 1.0)}")
        print(f"- Minimum Market Cap: ${criteria.get('min_market_cap', 200000000) / 1000000:.1f}M")
        if criteria.get('outperform_sp500', True):
            print("- Must outperform S&P 500")
        
        # 기준에 맞는 회사 필터링
        filtered_companies = []
        for company in companies:
            # 필수 필드가 있는지 확인
            if not all(key in company for key in ['ticker', 'name']):
                continue
                
            # 각 기준에 대해 개별적으로 검사 (누락된 데이터 처리)
            eps_growth_ok = company.get("quarterly_eps_growth", 0) >= criteria.get("quarterly_eps_growth", 0.2)
            eps_cagr_ok = company.get("annual_eps_cagr", 0) >= criteria.get("annual_eps_cagr", 0.2)
            revenue_ok = company.get("revenue_growth", 0) >= criteria.get("revenue_growth", 0.15)
            margin_ok = company.get("profit_margin", 0) >= criteria.get("profit_margin", 0.1)
            roe_ok = company.get("roe", 0) >= criteria.get("roe", 0.15)
            
            # 부채비율은 낮을수록 좋음
            debt_ok = company.get("debt_to_equity", float('inf')) <= criteria.get("debt_to_equity", 1.0)
            
            # 시가총액은 최소값 이상이어야 함
            mktcap_ok = company.get("market_cap", 0) >= criteria.get("min_market_cap", 200000000)
            
            # S&P 500 대비 성과 검사 (선택적)
            sp500_ok = True
            if criteria.get("outperform_sp500", True) and "price_performance" in company:
                sp500_ok = company.get("price_performance", {}).get("vs_sp500", 0) > 0
            
            # 모든 조건을 만족하면 필터링된 회사 목록에 추가
            if eps_growth_ok and eps_cagr_ok and revenue_ok and margin_ok and roe_ok and debt_ok and mktcap_ok and sp500_ok:
                filtered_companies.append(company)
        
        logger.info(f"Found {len(filtered_companies)} companies passing screening criteria")
        print(f"\nFound {len(filtered_companies)} companies passing screening criteria")
        
        # 결과 저장
        output_file = config.get("data_paths", {}).get("output_file", "data/processed/results.csv")
        
        if filtered_companies:
            # 결과를 시장 성과 대비 성장률로 정렬
            filtered_companies.sort(key=lambda x: (
                x.get("quarterly_eps_growth", 0) + 
                x.get("annual_eps_cagr", 0) + 
                x.get("revenue_growth", 0)
            ), reverse=True)
            
            # DataFrame으로 변환하여 CSV로 저장
            df = pd.DataFrame(filtered_companies)
            df.to_csv(output_file, index=False)
            logger.info(f"Results saved to {output_file}")
            print(f"Results saved to {output_file}")
            
            # 결과 출력 - 상위 10개 회사만
            print("\nTop companies passing screening criteria:")
            print(f"{'TICKER':<6} {'NAME':<30} {'Q EPS':<8} {'A EPS':<8} {'REV':<8} {'MARGIN':<8} {'ROE':<8} {'D/E':<8} {'MKTCAP($M)':<12}")
            print("-" * 100)
            
            for company in filtered_companies[:10]:
                ticker = company.get('ticker', 'N/A')
                name = company.get('name', 'Unknown')
                if len(name) > 28:
                    name = name[:25] + '...'
                
                q_eps = f"{company.get('quarterly_eps_growth', 0) * 100:.1f}%"
                a_eps = f"{company.get('annual_eps_cagr', 0) * 100:.1f}%"
                rev = f"{company.get('revenue_growth', 0) * 100:.1f}%"
                margin = f"{company.get('profit_margin', 0) * 100:.1f}%"
                roe = f"{company.get('roe', 0) * 100:.1f}%"
                de = f"{company.get('debt_to_equity', 0):.2f}"
                mktcap = f"${company.get('market_cap', 0) / 1000000:.1f}M"
                
                print(f"{ticker:<6} {name:<30} {q_eps:<8} {a_eps:<8} {rev:<8} {margin:<8} {roe:<8} {de:<8} {mktcap:<12}")
                
            # 전체 결과 수가 10개 이상인 경우 추가 결과가 있음을 알려줌
            if len(filtered_companies) > 10:
                print(f"\n...and {len(filtered_companies) - 10} more companies. See {output_file} for the complete list.")
        else:
            logger.warning("No companies passed the screening criteria")
            print("\nNo companies passed the screening criteria. Consider relaxing your criteria in config.json.")
            
            # 빈 결과 파일 생성
            with open(output_file, 'w') as f:
                f.write("No companies passed the screening criteria.\n")
            print(f"Empty results file created at {output_file}")
    
    except Exception as e:
        logger.error(f"Error during stock screening: {e}")
        print(f"Error during stock screening: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description="Growth Stock Screener - Find high-growth stocks using SEC EDGAR data."
    )
    
    parser.add_argument(
        "--mode",
        required=True,
        choices=["download", "parse", "screen"],
        help="Operation mode: download SEC data, parse data, or screen stocks"
    )
    
    parser.add_argument(
        "--config",
        default=os.path.join("config", "config.json"),
        help="Path to configuration file (default: config/config.json)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Setup logging
    log_file = config.get("logging", {}).get("log_file", "logs/screener.log")
    log_level = getattr(logging, args.log_level)
    
    global logger
    logger = setup_logger("growth_stock_screener", log_file, log_level)
    
    logger.debug("Configuration loaded successfully.")
    
    # Ensure required directories exist
    ensure_directories(config)
    
    # Execute requested mode
    if args.mode == "download":
        download_data(config)
    elif args.mode == "parse":
        parse_data(config)
    elif args.mode == "screen":
        screen_stocks(config)

if __name__ == "__main__":
    import logging
    main()
