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
from typing import Any, Dict

# 프로젝트 루트 경로를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.utils.logger import setup_logger
from src.utils.config_loader import load_config_file
from src.utils.directory import ensure_directories
from src.api.sec_client import SECClient
from src.collectors.submissions_collector import SubmissionsCollector
from src.collectors.facts_collector import CompanyFactsCollector
from src.parsers.submissions_parser import SubmissionsParser
from src.parsers.facts_parser import XBRLFactsParser
from src.enrichers.market_data_enricher import enrich_market_data, enrich_leadership_data, MarketDataEnricher
from src.collectors.financial_data_collector import collect_financial_data
from src.screeners.stock_screener import StockScreener

def load_config(config_path, profile=None):
    """Load configuration from JSON file, optionally applying a profile overlay."""
    import logging
    temp_logger = logging.getLogger("config_loader")
    
    try:
        return load_config_file(config_path, profile=profile)
    except FileNotFoundError:
        temp_logger.error(f"Config file '{config_path}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        temp_logger.error(f"Config file '{config_path}' is not valid JSON.")
        sys.exit(1)


def _passes_min_threshold(value: Any, threshold: Any) -> bool:
    """Return True when a numeric value passes a minimum threshold or the threshold is disabled."""
    if threshold is None:
        return True
    return pd.notna(value) and value >= threshold


def _passes_max_threshold(value: Any, threshold: Any) -> bool:
    """Return True when a numeric value passes a maximum threshold or the threshold is disabled."""
    if threshold is None:
        return True
    return pd.notna(value) and value <= threshold


def _check_supply_demand(company: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
    """Evaluate CANSLIM supply/demand using accumulation and optional breakout confirmation."""
    if not criteria.get("require_supply_demand", False):
        return True

    accumulation_ok = _passes_min_threshold(
        company.get("up_down_volume_ratio_50d"),
        criteria.get("up_down_volume_ratio_min", 1.0),
    )
    volume_trend_ok = _passes_min_threshold(
        company.get("volume_trend_50_200"),
        criteria.get("volume_trend_50_200_min", 0.9),
    )

    breakout_confirmation_ok = True
    if criteria.get("require_breakout_volume_confirmation", False):
        near_action = bool(company.get("valid_breakout", False))
        if criteria.get("confirm_volume_for_near_pivot", False):
            near_action = near_action or bool(company.get("near_pivot", False))
        if near_action:
            breakout_confirmation_ok = _passes_min_threshold(
                company.get("breakout_volume_ratio"),
                criteria.get("breakout_volume_ratio_min", 1.3),
            )

    volume_dry_up_ok = True
    if criteria.get("require_volume_dry_up", False):
        volume_dry_up_ok = _passes_max_threshold(
            company.get("volume_dry_up_ratio_10_50"),
            criteria.get("volume_dry_up_ratio_max", 0.8),
        )

    return accumulation_ok and volume_trend_ok and breakout_confirmation_ok and volume_dry_up_ok


def _check_institutional(company: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
    """Evaluate CANSLIM institutional sponsorship with support for ownership or holder-count proxies."""
    if not criteria.get("require_institutional_sponsorship", False):
        return True

    ownership = company.get("institutional_ownership")
    holders = company.get("institutional_holders")

    ownership_ok = (
        _passes_min_threshold(ownership, criteria.get("institutional_ownership_min"))
        and _passes_max_threshold(ownership, criteria.get("institutional_ownership_max"))
    )
    holders_ok = _passes_min_threshold(
        holders,
        criteria.get("institutional_holders_min"),
    )

    mode = criteria.get("sponsorship_mode", "ownership")
    if mode == "ownership_and_holders":
        return ownership_ok and holders_ok
    if mode == "ownership_or_holders":
        return ownership_ok or holders_ok
    if mode == "holders":
        return holders_ok
    return ownership_ok


def _check_pattern(company: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
    """Evaluate CANSLIM N using high proximity, pivot setup, and breakout signals."""
    if criteria.get("require_hybrid_setup", False):
        price_vs_high = company.get("price_vs_52w_high")
        base_depth = company.get("base_depth_65d")
        breakout_ok = bool(company.get("valid_breakout", False))
        pivot_ok = bool(company.get("near_pivot", False))
        high_ok = _passes_min_threshold(
            price_vs_high,
            criteria.get("price_vs_52w_high_min", 0.85),
        )
        base_ok = pd.notna(base_depth) and base_depth <= criteria.get("base_depth_max", 0.35)
        rs_line_ok = True
        if criteria.get("require_rs_line_near_high_for_setup", False):
            rs_line_ok = bool(company.get("rs_line_near_high", False))

        setup_ok = breakout_ok
        if criteria.get("allow_hybrid_breakout", True):
            setup_ok = setup_ok or (pivot_ok and high_ok and base_ok)
        else:
            setup_ok = pivot_ok and high_ok and base_ok
        return setup_ok and rs_line_ok

    new_high_ok = True
    if criteria.get("require_new_high_or_breakout", False):
        price_vs_high = company.get("price_vs_52w_high", 0)
        breakout_pct = company.get("breakout_pct")
        pivot_ready = (
            bool(company.get("near_pivot", False))
            and price_vs_high >= criteria.get("price_vs_52w_high_hard_min", 0.90)
            and pd.notna(breakout_pct)
            and breakout_pct >= criteria.get("breakout_pct_min", -0.02)
        )
        new_high_ok = (
            bool(company.get("new_52w_high", False))
            or bool(company.get("valid_breakout", False))
            or (criteria.get("allow_near_pivot_setup", False) and pivot_ready)
        )
    elif criteria.get("require_new_52w_high", False):
        new_high_ok = bool(company.get("new_52w_high", False))

    base_ok = True
    base_depth = company.get("base_depth_65d")
    if criteria.get("require_base_depth", False):
        base_ok = (
            pd.notna(base_depth)
            and base_depth <= criteria.get("base_depth_max", 0.35)
        )

    breakout_ok = True
    if criteria.get("require_near_pivot", False):
        breakout_ok = breakout_ok and bool(company.get("near_pivot", False))
    if criteria.get("require_valid_breakout", False):
        breakout_ok = breakout_ok and bool(company.get("valid_breakout", False))

    return new_high_ok and base_ok and breakout_ok


def _sort_screen_results(filtered_companies: list[Dict[str, Any]], profile_name: str) -> None:
    """Sort results in-place using a profile-aware ranking."""
    if profile_name == "canslim_hybrid":
        filtered_companies.sort(
            key=lambda x: (
                int(bool(x.get("valid_breakout", False))),
                int(bool(x.get("near_pivot", False))),
                x.get("breakout_volume_ratio", 0) or 0,
                x.get("rs_rating", 0) or 0,
                int(bool(x.get("rs_line_near_high", False))),
                x.get("price_vs_52w_high", 0) or 0,
                -((x.get("volume_dry_up_ratio_10_50", 999) or 999)),
                x.get("quarterly_eps_growth", 0) or 0,
                x.get("annual_eps_cagr", 0) or 0,
            ),
            reverse=True,
        )
        return

    filtered_companies.sort(
        key=lambda x: (
            (x.get("quarterly_eps_growth", 0) or 0)
            + (x.get("annual_eps_cagr", 0) or 0)
            + (x.get("revenue_growth", 0) or 0),
            x.get("rs_rating", 0) or 0,
            x.get("price_vs_52w_high", 0) or 0,
        ),
        reverse=True,
    )

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
        
        # Start the download process - Pass the companies list explicitly
        results = facts_collector.download_all_company_facts(
            companies=companies,  # Pass the companies list
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
        
        # Parse company facts with force=True to reprocess data
        facts_parser = XBRLFactsParser(config)
        metrics_df = facts_parser.process_all(force=True)
        
        logger.info(f"Processed financial metrics for {len(metrics_df)} companies")
        logger.info(f"Metrics columns: {metrics_df.columns.tolist()}")
        
        # Check if financial metrics were actually calculated
        financial_metrics = ['quarterly_eps_growth', 'annual_eps_cagr', 'revenue_growth', 'profit_margin', 'roe', 'debt_to_equity']
        metrics_found = [col for col in financial_metrics if col in metrics_df.columns]
        
        if not metrics_found:
            logger.warning("No financial metrics were calculated! Check the facts parser.")
        else:
            # Log summary of calculated metrics
            for metric in metrics_found:
                count = metrics_df[metric].notnull().sum()
                logger.info(f"Metric '{metric}': {count} companies have values ({count/len(metrics_df)*100:.1f}%)")
        
        # Save a combined list of companies with metrics to JSON
        # Only try to merge if both DataFrames have data
        if not companies_df.empty and not metrics_df.empty:
            # Check if 'cik' column exists in metrics_df
            if 'cik' in metrics_df.columns:
                # Ensure both dataframes have the cik column in the same format
                # Sometimes one might be string and one might be numeric
                companies_df['cik'] = companies_df['cik'].astype(str)
                metrics_df['cik'] = metrics_df['cik'].astype(str)
                
                # Log sample CIKs before merge
                logger.debug(f"Sample CIKs in companies_df: {companies_df['cik'].iloc[:5].tolist()}")
                logger.debug(f"Sample CIKs in metrics_df: {metrics_df['cik'].iloc[:5].tolist()}")
                
                # Do the merge and keep screener-facing company fields stable.
                combined_df = pd.merge(companies_df, metrics_df, on='cik', how='left', suffixes=('', '_metrics'))
                for field in ['ticker', 'name']:
                    metrics_field = f"{field}_metrics"
                    if metrics_field in combined_df.columns:
                        if field in combined_df.columns:
                            combined_df[field] = combined_df[field].fillna(combined_df[metrics_field])
                            combined_df.loc[combined_df[field] == '', field] = combined_df.loc[
                                combined_df[field] == '', metrics_field
                            ]
                        else:
                            combined_df[field] = combined_df[metrics_field]
                        combined_df = combined_df.drop(columns=[metrics_field])

                logger.info(f"Combined data for {len(combined_df)} companies, with {len(metrics_df)} providing metrics")
                
                # Check if financial metrics were successfully merged
                for metric in metrics_found:
                    count = combined_df[metric].notnull().sum()
                    logger.info(f"After merge, metric '{metric}': {count} companies have values")
                
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
        traceback.print_exc()
        return False

def screen_stocks(config):
    """Screen stocks based on criteria."""
    logger.info("Screening stocks based on criteria...")
    
    try:
        # Load processed company data
        processed_dir = config.get("data_paths", {}).get("processed_data_dir", "data/processed")
        companies_list_file = os.path.join(processed_dir, "companies_list.json")
        enriched_companies_file = os.path.join(processed_dir, "companies_list_enriched.json")
        if os.path.exists(enriched_companies_file):
            companies_list_file = enriched_companies_file
        
        if not os.path.exists(companies_list_file):
            logger.error(f"Companies list file not found: {companies_list_file}")
            print(f"Error: Companies list file not found at {companies_list_file}")
            print("Please run the parse mode first to generate the required data.")
            return
        
        with open(companies_list_file, 'r') as f:
            companies = json.load(f)
        
        logger.info(f"Loaded data for {len(companies)} companies")
        print(f"Loaded data for {len(companies)} companies")
        if config.get("profile_name"):
            print(f"Active profile: {config.get('profile_name')}")
        
        # Get screening criteria
        criteria = config.get("screening_criteria", {})
        leadership_criteria = config.get("leadership_criteria", {})
        market_direction_criteria = config.get("market_direction", {})
        supply_demand_criteria = config.get("supply_demand_criteria", {})
        institutional_criteria = config.get("institutional_criteria", {})
        pattern_criteria = config.get("pattern_criteria", {})
        test_mode = config.get("download_settings", {}).get("test_mode", False)
        market_direction = {}
        market_direction_file = os.path.join(processed_dir, "market_direction.json")
        if os.path.exists(market_direction_file):
            with open(market_direction_file, "r") as f:
                market_direction = json.load(f)
        
        # Output screening criteria
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
        print(f"- RS Rating: ≥ {leadership_criteria.get('rs_rating_min', 80):.0f}")
        print(f"- Price vs 52-week High: ≥ {leadership_criteria.get('price_vs_52w_high_min', 0.85) * 100:.1f}%")
        print(f"- 50-day Avg Dollar Volume: ≥ ${leadership_criteria.get('avg_dollar_volume_min', 0) / 1000000:.1f}M")
        if market_direction_criteria.get("required", False):
            print(f"- Market Direction: {market_direction.get('market_direction_status', 'missing')} in {market_direction_criteria.get('allowed_statuses', [])}")
        if supply_demand_criteria.get("require_supply_demand", False):
            print(f"- Up/Down Volume Ratio: ≥ {supply_demand_criteria.get('up_down_volume_ratio_min', 1.1):.2f}")
            print(f"- 50/200 Volume Trend: ≥ {supply_demand_criteria.get('volume_trend_50_200_min', 1.0):.2f}")
            if supply_demand_criteria.get("require_volume_dry_up", False):
                print(f"- 10/50 Volume Dry-up Ratio: ≤ {supply_demand_criteria.get('volume_dry_up_ratio_max', 0.8):.2f}")
        if institutional_criteria.get("require_institutional_sponsorship", False):
            print(f"- Institutional Ownership: {institutional_criteria.get('institutional_ownership_min', 0.2) * 100:.1f}%~{institutional_criteria.get('institutional_ownership_max', 0.95) * 100:.1f}%")
        
        # Financial metrics statistics
        metrics_counts = {
            "quarterly_eps_growth": 0,
            "annual_eps_cagr": 0,
            "revenue_growth": 0,
            "profit_margin": 0,
            "roe": 0,
            "debt_to_equity": 0,
            "market_cap": 0,
            "rs_rating": 0,
            "price_vs_52w_high": 0,
            "avg_dollar_volume_50d": 0,
            "up_down_volume_ratio_50d": 0,
            "volume_trend_50_200": 0,
            "volume_dry_up_ratio_10_50": 0,
            "institutional_ownership": 0,
            "institutional_holders": 0,
            "breakout_volume_ratio": 0,
            "new_52w_high": 0,
            "near_pivot": 0,
            "valid_breakout": 0
        }
        
        # Count valid metrics
        for company in companies:
            for metric in metrics_counts.keys():
                if metric in company and pd.notna(company[metric]) and company[metric] != 0:
                    metrics_counts[metric] += 1
        
        print("\nFinancial Metrics Data Statistics:")
        for metric, count in metrics_counts.items():
            print(f"- {metric}: {count}/{len(companies)} companies ({count/len(companies)*100:.1f}%)")

        missing_enrich_reasons = []
        if criteria.get("outperform_sp500", False) and metrics_counts.get("rs_rating", 0) == 0:
            missing_enrich_reasons.append("S&P 500 대비 성과/RS 지표가 없습니다")
        if leadership_criteria.get("rs_rating_min") is not None and metrics_counts.get("rs_rating", 0) == 0:
            missing_enrich_reasons.append("RS Rating 지표가 없습니다")
        if leadership_criteria.get("avg_dollar_volume_min", 0) > 0 and metrics_counts.get("avg_dollar_volume_50d", 0) == 0:
            missing_enrich_reasons.append("50일 평균 거래대금 지표가 없습니다")
        if supply_demand_criteria.get("require_supply_demand", False) and metrics_counts.get("up_down_volume_ratio_50d", 0) == 0:
            missing_enrich_reasons.append("수급/거래량 지표가 없습니다")
        if supply_demand_criteria.get("require_volume_dry_up", False) and metrics_counts.get("volume_dry_up_ratio_10_50", 0) == 0:
            missing_enrich_reasons.append("거래량 드라이업 지표가 없습니다")
        if (
            institutional_criteria.get("require_institutional_sponsorship", False)
            and metrics_counts.get("institutional_ownership", 0) == 0
            and metrics_counts.get("institutional_holders", 0) == 0
        ):
            missing_enrich_reasons.append("기관 수급 지표가 없습니다. pure CANSLIM 프로필은 기관 보유/보유기관 수가 필요합니다")
        if market_direction_criteria.get("required", False) and not market_direction:
            missing_enrich_reasons.append("시장 방향 파일(data/processed/market_direction.json)이 없습니다")

        if missing_enrich_reasons:
            profile_name = config.get("profile_name")
            if profile_name and profile_name != "default":
                enrich_cmd = (
                    "./canslimsepa/bin/python run_screener.py --mode enrich "
                    f"--config config/base.json --profile {profile_name}"
                )
            else:
                enrich_cmd = "./canslimsepa/bin/python run_screener.py --mode enrich --config config/config.json"
            print("\nMarket/leadership enrichment data is missing, so screening would incorrectly return 0 results.")
            for reason in missing_enrich_reasons:
                print(f"- {reason}")
            print("\nRun enrich first and wait for it to finish:")
            print(enrich_cmd)
            return
        
        # 기준에 맞는 회사 필터링
        filtered_companies = []
        criteria_counts = {criterion: 0 for criterion in [
            "eps", "eps_cagr", "revenue", "margin", "roe", "debt", "mktcap",
            "sp500", "rs", "near_high", "liquidity", "rs_line", "industry",
            "market_direction", "supply_demand", "institutional", "new_high", "base", "breakout"
        ]}
        market_direction_ok = True
        if market_direction_criteria.get("required", False):
            allowed_statuses = market_direction_criteria.get("allowed_statuses", ["confirmed_uptrend"])
            market_direction_ok = market_direction.get("market_direction_status") in allowed_statuses
        
        for company in companies:
            # 필수 필드가 있는지 확인
            if not all(key in company for key in ['ticker', 'name']):
                continue
            
            # 필수 재무 데이터가 없는 경우, 디버깅을 위해 기본값 추가 (테스트용)
            if any(key not in company for key in ["quarterly_eps_growth", "annual_eps_cagr", "revenue_growth", "profit_margin", "roe"]):
                # 테스트 모드에서는 누락된 데이터를 임의의 값으로 채워 스크리닝 테스트
                if test_mode:
                    if "quarterly_eps_growth" not in company: company["quarterly_eps_growth"] = 0.05  # 5%
                    if "annual_eps_cagr" not in company: company["annual_eps_cagr"] = 0.07  # 7%
                    if "revenue_growth" not in company: company["revenue_growth"] = 0.06  # 6% 
                    if "profit_margin" not in company: company["profit_margin"] = 0.04  # 4%
                    if "roe" not in company: company["roe"] = 0.08  # 8%
                    if "debt_to_equity" not in company: company["debt_to_equity"] = 1.2  # 1.2
            
            # 각 기준에 대해 개별적으로 검사 (누락된 데이터 처리)
            eps_growth_ok = company.get("quarterly_eps_growth", 0) >= criteria.get("quarterly_eps_growth", 0)
            if eps_growth_ok: criteria_counts["eps"] += 1
            
            eps_cagr_ok = company.get("annual_eps_cagr", 0) >= criteria.get("annual_eps_cagr", 0)
            if eps_cagr_ok: criteria_counts["eps_cagr"] += 1
            
            revenue_ok = _passes_min_threshold(
                company.get("revenue_growth"),
                criteria.get("revenue_growth", 0),
            )
            if revenue_ok: criteria_counts["revenue"] += 1
            
            margin_ok = _passes_min_threshold(
                company.get("profit_margin"),
                criteria.get("profit_margin", 0),
            )
            if margin_ok: criteria_counts["margin"] += 1
            
            roe_ok = _passes_min_threshold(
                company.get("roe"),
                criteria.get("roe", 0),
            )
            if roe_ok: criteria_counts["roe"] += 1
            
            # 부채비율은 낮을수록 좋음 (0보다 작으면 안됨)
            debt_to_equity = company.get("debt_to_equity", float('inf'))
            # 음수 부채비율은 무시하고 양수 부채비율만 필터링 (음수 또는 0이면 통과)
            if debt_to_equity <= 0:
                debt_ok = True
            else:
                debt_ok = _passes_max_threshold(
                    debt_to_equity,
                    criteria.get("debt_to_equity", float('inf')),
                )
            if debt_ok: criteria_counts["debt"] += 1
            
            # 시가총액은 최소값 이상이어야 함
            mktcap_ok = _passes_min_threshold(
                company.get("market_cap"),
                criteria.get("min_market_cap", 0),
            )
            if mktcap_ok: criteria_counts["mktcap"] += 1
            
            # S&P 500 대비 성과 검사 (선택적)
            sp500_ok = True
            if criteria.get("outperform_sp500", False):
                sp500_ok = company.get("market_outperformance_12m", float("-inf")) > 0
            if sp500_ok: criteria_counts["sp500"] += 1

            rs_ok = _passes_min_threshold(
                company.get("rs_rating"),
                leadership_criteria.get("rs_rating_min", 80),
            )
            if rs_ok: criteria_counts["rs"] += 1

            near_high_ok = _passes_min_threshold(
                company.get("price_vs_52w_high"),
                leadership_criteria.get("price_vs_52w_high_min", 0.85),
            )
            if near_high_ok: criteria_counts["near_high"] += 1

            liquidity_ok = _passes_min_threshold(
                company.get("avg_dollar_volume_50d"),
                leadership_criteria.get("avg_dollar_volume_min", 0),
            )
            if liquidity_ok: criteria_counts["liquidity"] += 1

            rs_line_ok = True
            if leadership_criteria.get("rs_line_near_high", False):
                rs_line_ok = bool(company.get("rs_line_near_high", False))
            if rs_line_ok: criteria_counts["rs_line"] += 1

            industry_ok = True
            if leadership_criteria.get("require_industry_leadership", False):
                industry_ok = (
                    company.get("industry_rs_rank", 0) >= leadership_criteria.get("industry_rs_rank_min", 80)
                    and company.get("industry_stock_rank", 0) >= leadership_criteria.get("industry_stock_rank_min", 80)
                )
            if industry_ok: criteria_counts["industry"] += 1

            supply_demand_ok = _check_supply_demand(company, supply_demand_criteria)
            if supply_demand_ok: criteria_counts["supply_demand"] += 1

            institutional_ok = _check_institutional(company, institutional_criteria)
            if institutional_ok: criteria_counts["institutional"] += 1

            new_high_ok = _check_pattern(company, pattern_criteria)
            if new_high_ok: criteria_counts["new_high"] += 1
            base_ok = True
            breakout_ok = True
            if new_high_ok:
                criteria_counts["base"] += 1
                criteria_counts["breakout"] += 1

            if market_direction_ok:
                criteria_counts["market_direction"] += 1
            
            # 조건에 따라 시장 성과와 재무 지표 모두 고려
            if test_mode:
                # 테스트 모드: 시장 데이터만 있으면 회사를 포함
                if mktcap_ok:  
                    filtered_companies.append(company)
            else:
                # 일반 모드: 모든 조건 확인
                if (
                    eps_growth_ok and eps_cagr_ok and revenue_ok and margin_ok and roe_ok
                    and debt_ok and mktcap_ok and sp500_ok
                    and rs_ok and near_high_ok and liquidity_ok and rs_line_ok and industry_ok
                    and market_direction_ok and supply_demand_ok and institutional_ok
                    and new_high_ok and base_ok and breakout_ok
                ):
                    filtered_companies.append(company)
        
        # Screening criteria summary
        print("\nCompanies passing criteria by category:")
        for criterion, count in criteria_counts.items():
            print(f"- {criterion}: {count}/{len(companies)} companies ({count/len(companies)*100:.1f}%)")
        
        logger.info(f"Found {len(filtered_companies)} companies passing screening criteria")
        print(f"\nFound {len(filtered_companies)} companies passing screening criteria")
        
        # 결과 저장
        output_file = config.get("data_paths", {}).get("output_file", "data/processed/results.csv")
        
        if filtered_companies:
            _sort_screen_results(filtered_companies, config.get("profile_name", "default"))
            
            # DataFrame으로 변환하여 CSV로 저장
            df = pd.DataFrame(filtered_companies)
            df.to_csv(output_file, index=False)
            logger.info(f"Results saved to {output_file}")
            print(f"Results saved to {output_file}")
            
            # 결과 출력 - 상위 10개 회사만
            print("\nTop companies passing screening criteria:")
            print(f"{'TICKER':<6} {'NAME':<30} {'Q EPS':<8} {'A EPS':<8} {'REV':<8} {'ROE':<8} {'RS':<6} {'52W':<7} {'MKTCAP($M)':<12}")
            print("-" * 104)
            
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
                rs = f"{company.get('rs_rating', 0):.0f}"
                near_high = f"{company.get('price_vs_52w_high', 0) * 100:.1f}%"
                mktcap = f"${company.get('market_cap', 0) / 1000000:.1f}M"
                
                print(f"{ticker:<6} {name:<30} {q_eps:<8} {a_eps:<8} {rev:<8} {roe:<8} {rs:<6} {near_high:<7} {mktcap:<12}")
                
            # 전체 결과 수가 10개 이상인 경우 추가 결과가 있음을 알려줌
            if len(filtered_companies) > 10:
                print(f"And {len(filtered_companies) - 10} more companies are not shown...")
        else:
            logger.warning("No companies passed the screening criteria")
            print("\nNo companies passed the screening criteria. Consider relaxing your criteria in the active screener profile.")
            
            # 빈 결과 파일 생성
            with open(output_file, 'w') as f:
                f.write("No companies passed the screening criteria.\n")
            print(f"Empty results file created at {output_file}")
    
    except Exception as e:
        logger.error(f"Error during stock screening: {e}")
        print(f"Error during stock screening: {e}")
        import traceback
        traceback.print_exc()

def run_screening(config_path):
    """Run the stock screening process"""
    logger.info("Starting stock screening...")
    
    # Load configuration
    config = load_config(config_path)
    
    # Load processed financial metrics
    metrics_file = os.path.join(config['data_paths']['processed_data_dir'], 'financial_metrics.parquet')
    if not os.path.exists(metrics_file):
        logger.error(f"Financial metrics file not found: {metrics_file}")
        logger.info("Please run 'parse' mode first to generate financial metrics.")
        return
    
    financial_metrics = pd.read_parquet(metrics_file)
    logger.info(f"Loaded financial metrics for {len(financial_metrics)} companies")
    
    # Load company list with tickers for lookup
    companies_file = os.path.join(config['data_paths']['processed_data_dir'], 'companies_list.json')
    with open(companies_file, 'r') as f:
        companies_data = json.load(f)
    
    # Create the stock screener
    screener = StockScreener(config)
    
    # Enrich data with market info if needed
    market_enricher = MarketDataEnricher(config)
    enriched_data = market_enricher.enrich_company_data(financial_metrics)
    
    # Run the screening
    screened_results = screener.screen_stocks(enriched_data)
    
    # Save results
    output_file = config['data_paths'].get('output_file', 'data/processed/results.csv')
    screened_results.to_csv(output_file, index=False)
    logger.info(f"Saved {len(screened_results)} companies to {output_file}")

def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description="Growth Stock Screener - Find high-growth stocks using SEC EDGAR data."
    )
    
    parser.add_argument(
        "--mode",
        required=True,
        choices=["download", "parse", "enrich", "leadership", "financials", "screen"],  # "financials" mode added
        help="Operation mode: download SEC data, parse data, enrich market data, enrich leadership data, collect financial data, or screen stocks"
    )
    
    parser.add_argument(
        "--config",
        default=os.path.join("config", "config.json"),
        help="Path to configuration file (legacy single file, or base config when used with --profile)"
    )

    parser.add_argument(
        "--profile",
        help="Optional screener profile name under config/profiles, e.g. canslim_pure"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config, profile=args.profile)
    
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
    elif args.mode == "enrich":
        # Using SEC data only, no external API
        enrich_market_data(config, use_external_api=False)
    elif args.mode == "leadership":
        enrich_leadership_data(config)
    elif args.mode == "financials":  # Handler for the financials mode
        collect_financial_data(config)
    elif args.mode == "screen":
        screen_stocks(config)

if __name__ == "__main__":
    import logging
    main()
