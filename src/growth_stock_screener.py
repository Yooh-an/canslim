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

from src.utils.logger import setup_logger
from src.utils.config_loader import load_config_file
from src.utils.directory import ensure_directories
from src.utils.pipeline_status import collect_pipeline_status, print_pipeline_status
from src.utils.security_classifier import apply_security_classification
from src.api.sec_client import SECClient
from src.collectors.submissions_collector import SubmissionsCollector
from src.collectors.facts_collector import CompanyFactsCollector
from src.parsers.submissions_parser import SubmissionsParser
from src.parsers.facts_parser import XBRLFactsParser
from src.enrichers.market_data_enricher import enrich_market_data, enrich_leadership_data, MarketDataEnricher
from src.enrichers.fundamental_fallback import enrich_missing_fundamentals
from src.collectors.financial_data_collector import collect_financial_data
from src.collectors.institutional_collector import enrich_companies_with_13f_data
from src.collectors.insider_collector import enrich_companies_with_insider_data
from src.collectors.short_interest_collector import enrich_companies_with_short_interest_data
from src.formatters.results_formatter import ResultsFormatter
from src.screeners.stock_screener import StockScreener
from src.screeners.canslim_scoring import calculate_canslim_score
from src.screeners.ticker_analysis import analyze_ticker, format_ticker_analysis
from src.integrations.tradingview_export import export_tradingview_artifacts
from src.screeners.candidate_filter import (
    _check_institutional,
    _check_pattern,
    _check_supply_demand,
    filter_screening_candidates,
    _filter_screening_candidates,
    _sort_screen_results,
)
from src.ui.rich_printer import (
    print_screening_header,
    print_screening_criteria,
    print_metrics_stats,
    print_criteria_breakdown,
    print_results_table,
    print_data_quality_warning,
    print_missing_enrich_warning,
    print_saved_result,
)

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
                combined_df = enrich_missing_fundamentals(combined_df, config)
                
                # Check if financial metrics were successfully merged
                for metric in metrics_found:
                    count = combined_df[metric].notnull().sum()
                    logger.info(f"After merge, metric '{metric}': {count} companies have values")
                
                companies_list = combined_df.to_dict(orient='records')
            else:
                logger.warning("Column 'cik' not found in metrics dataframe, using company data only")
                companies_df = enrich_missing_fundamentals(companies_df, config)
                companies_list = companies_df.to_dict(orient='records')
        elif not companies_df.empty:
            logger.warning("No metrics data available, using company data only")
            companies_df = enrich_missing_fundamentals(companies_df, config)
            companies_list = companies_df.to_dict(orient='records')
        elif not metrics_df.empty:
            logger.warning("No company index data available, using metrics data only")
            metrics_df = enrich_missing_fundamentals(metrics_df, config)
            companies_list = metrics_df.to_dict(orient='records')
        else:
            logger.warning("No data available in either company index or metrics")
            companies_list = []
        
        classification_settings = config.get("security_classification", {})
        recent_listing_days = classification_settings.get("recent_listing_days", 730)
        for company in companies_list:
            apply_security_classification(company, recent_listing_days=recent_listing_days)
        profile_counts = pd.Series([company.get("security_profile", "standard") for company in companies_list]).value_counts().to_dict()
        logger.info(f"Security profile classification counts: {profile_counts}")

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




POSITIVE_VALUE_METRICS = {"market_cap", "avg_dollar_volume_50d"}
BOOLEAN_SIGNAL_METRICS = {"new_52w_high", "recent_new_52w_high", "near_pivot", "valid_breakout"}


METRICS_FOR_COVERAGE = [
    "quarterly_eps_growth",
    "annual_eps_cagr",
    "revenue_growth",
    "profit_margin",
    "roe",
    "debt_to_equity",
    "market_cap",
    "rs_rating",
    "price_vs_52w_high",
    "avg_dollar_volume_50d",
    "up_down_volume_ratio_50d",
    "volume_trend_50_200",
    "volume_dry_up_ratio_10_50",
    "institutional_ownership",
    "institutional_holders",
    "institutional_holders_qoq_change",
    "institutional_value_qoq_change",
    "institutional_accumulation_score",
    "new_holder_count",
    "increased_holder_count",
    "decreased_holder_count",
    "exited_holder_count",
    "insider_ownership",
    "insider_buy_count_90d",
    "net_insider_buy_value_90d",
    "shares_float",
    "short_interest",
    "short_percent_float",
    "short_percent_shares_outstanding",
    "short_days_to_cover",
    "canslim_score",
    "breakout_volume_ratio",
    "new_52w_high",
    "recent_new_52w_high",
    "near_pivot",
    "valid_breakout",
]


def _has_metric_value(company: Dict[str, Any], metric: str) -> bool:
    """Return True when *metric* contains a real data value.

    Data coverage should measure availability, not whether a value is bullish.
    Therefore numeric zero and boolean False count as available values.  The
    only exception is fields where zero is a known placeholder for missing
    market data, such as market cap and dollar volume.
    """
    if metric not in company:
        return False
    value = company.get(metric)
    if value is None or not pd.notna(value):
        return False
    if metric in POSITIVE_VALUE_METRICS:
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return False
    return True


def _coerce_optional_float(value: Any) -> float | None:
    """Return a float for real numeric values, otherwise None."""
    try:
        if value is None or not pd.notna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _calculate_profile_valid_breakout(company: Dict[str, Any], pattern_criteria: Dict[str, Any]) -> bool | None:
    """Calculate valid_breakout using the active profile's breakout criteria.

    The cached market-data file stores raw breakout metrics plus a derived
    boolean. The boolean is profile-dependent because the minimum volume ratio
    differs by profile, so screening must refresh it from the raw metrics.
    """
    breakout_pct = _coerce_optional_float(company.get("breakout_pct"))
    if breakout_pct is None:
        return None
    if not 0 <= breakout_pct <= 0.05:
        return False

    volume_threshold = pattern_criteria.get("breakout_volume_ratio_min", 1.4)
    if volume_threshold is None:
        return True

    breakout_volume_ratio = _coerce_optional_float(company.get("breakout_volume_ratio"))
    if breakout_volume_ratio is None:
        return None

    threshold = _coerce_optional_float(volume_threshold)
    if threshold is None:
        threshold = 1.4
    return breakout_volume_ratio >= threshold


def _refresh_profile_breakout_signals(
    companies: list[Dict[str, Any]],
    pattern_criteria: Dict[str, Any],
) -> list[Dict[str, Any]]:
    """Refresh profile-dependent breakout booleans from raw breakout metrics."""
    refreshed = []
    for company in companies:
        updated = dict(company)
        valid_breakout = _calculate_profile_valid_breakout(updated, pattern_criteria)
        if valid_breakout is None:
            updated.pop("valid_breakout", None)
        else:
            updated["valid_breakout"] = valid_breakout
        refreshed.append(updated)
    return refreshed


def _calculate_metric_coverage(companies: list[Dict[str, Any]]) -> tuple[Dict[str, int], Dict[str, int]]:
    """Return metric availability counts plus bullish signal true counts."""
    coverage_counts = {metric: 0 for metric in METRICS_FOR_COVERAGE}
    signal_counts = {metric: 0 for metric in BOOLEAN_SIGNAL_METRICS}
    for company in companies:
        for metric in METRICS_FOR_COVERAGE:
            if _has_metric_value(company, metric):
                coverage_counts[metric] += 1
        for metric in BOOLEAN_SIGNAL_METRICS:
            if bool(company.get(metric, False)):
                signal_counts[metric] += 1
    return coverage_counts, signal_counts


def _collect_data_quality_warnings(
    metrics_counts: Dict[str, int],
    total: int,
    config: Dict[str, Any],
) -> list[str]:
    """Return non-blocking data quality warnings for the screening report."""
    warnings: list[str] = []
    data_quality = config.get("data_quality", {}) if isinstance(config, dict) else {}
    market_cap_min_coverage = float(data_quality.get("market_cap_min_coverage", 0) or 0)
    if market_cap_min_coverage > 0 and total:
        market_cap_count = metrics_counts.get("market_cap", 0)
        market_cap_coverage = market_cap_count / total
        if market_cap_coverage < market_cap_min_coverage:
            warnings.append(
                "시가총액 커버리지 낮음: "
                f"{market_cap_count:,}/{total:,} ({market_cap_coverage * 100:.1f}%) < "
                f"목표 {market_cap_min_coverage * 100:.1f}%. "
                "`run_screener.py --mode enrich`로 yfinance market cap 보강을 다시 실행하세요."
            )
    insider_enabled = bool(config.get("insider_data", {}).get("enabled", False))
    insider_count = max(
        metrics_counts.get("insider_buy_count_90d", 0),
        metrics_counts.get("net_insider_buy_value_90d", 0),
    )
    if insider_enabled and insider_count == 0:
        warnings.append(
            "내부자 Form 4 데이터 없음: insider_data가 켜져 있지만 로컬 Form 4 XML/집계 데이터가 없습니다. "
            "필수 조건은 아니지만 내부자 신호는 비어 있습니다."
        )
    short_enabled = bool(config.get("short_interest_data", {}).get("enabled", False))
    if short_enabled and metrics_counts.get("short_interest", 0) == 0:
        live_note = (
            "fetch_live=true이지만 FINRA 응답/매칭 데이터가 없습니다."
            if config.get("short_interest_data", {}).get("fetch_live", False)
            else "로컬 FINRA CSV/JSON 캐시가 없고 fetch_live=false입니다."
        )
        warnings.append(
            f"FINRA short interest 데이터 없음: short_interest_data가 켜져 있지만 {live_note} "
            "단일 ticker 확인은 fetch_live를 켠 뒤 analyze 모드에서 실행하세요."
        )
    return warnings


def _score_companies_for_diagnostics(
    companies: list[Dict[str, Any]],
    criteria: Dict[str, Any],
    leadership_criteria: Dict[str, Any],
    supply_demand_criteria: Dict[str, Any],
    institutional_criteria: Dict[str, Any],
    pattern_criteria: Dict[str, Any],
    market_direction_ok: bool,
) -> list[Dict[str, Any]]:
    """Populate CAN SLIM scores for diagnostics before final pass/fail filtering."""
    scored_companies: list[Dict[str, Any]] = []
    for company in companies:
        if company.get("ticker") and company.get("name"):
            scored_companies.append(
                calculate_canslim_score(
                    company,
                    criteria,
                    leadership_criteria,
                    supply_demand_criteria,
                    institutional_criteria,
                    pattern_criteria,
                    market_direction_ok,
                )
            )
        else:
            scored_companies.append(dict(company))
    return scored_companies


def _hydrate_cached_enrichment(companies, config):
    """Apply cached market/13F/insider enrichment before screening.

    Screening should not report zero coverage just because the current companies
    list is stale while local cache files already contain the enrichment data.
    This function is cache/local only: it does not do broad live downloads.
    """
    hydrated = [dict(company) for company in companies]

    try:
        enricher_config = dict(config)
        enricher_config["_quiet"] = True
        enricher = MarketDataEnricher(enricher_config)
        market_cache = enricher._load_market_data_files(enricher.market_data_dir)
        for company in hydrated:
            ticker = enricher._normalize_yahoo_ticker(company.get("ticker", ""))
            cached = market_cache.get(ticker)
            if cached:
                company.update(cached)
                company.setdefault("ticker", ticker)
    except Exception as exc:
        logger.warning(f"Could not apply cached market enrichment: {exc}")

    if config.get("institutional_data", {}).get("enabled", False):
        try:
            hydrated = enrich_companies_with_13f_data(hydrated, config, sec_client=None)
        except Exception as exc:
            logger.warning(f"Could not apply cached/local 13F enrichment: {exc}")

    if config.get("insider_data", {}).get("enabled", False):
        try:
            hydrated = enrich_companies_with_insider_data(hydrated, config, sec_client=None)
        except Exception as exc:
            logger.warning(f"Could not apply cached/local insider enrichment: {exc}")

    if config.get("short_interest_data", {}).get("enabled", False):
        try:
            hydrated = enrich_companies_with_short_interest_data(hydrated, config)
        except Exception as exc:
            logger.warning(f"Could not apply cached/local FINRA short-interest enrichment: {exc}")

    return hydrated


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
        companies = _hydrate_cached_enrichment(companies, config)
        companies = _refresh_profile_breakout_signals(
            companies,
            config.get("pattern_criteria", {}),
        )
        try:
            with open(companies_list_file, 'w') as f:
                json.dump(companies, f, indent=2)
        except Exception as exc:
            logger.warning(f"Could not save hydrated company list to {companies_list_file}: {exc}")
        
        logger.info(f"Loaded data for {len(companies)} companies")
        print_screening_header(len(companies), config.get("profile_name"))
        
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
        print_screening_criteria(
            criteria, leadership_criteria, market_direction_criteria,
            market_direction, supply_demand_criteria, institutional_criteria,
        )

        market_direction_ok = True
        if market_direction_criteria.get("required", False):
            allowed_statuses = market_direction_criteria.get("allowed_statuses", ["confirmed_uptrend"])
            market_direction_ok = market_direction.get("market_direction_status") in allowed_statuses

        companies = _score_companies_for_diagnostics(
            companies,
            criteria,
            leadership_criteria,
            supply_demand_criteria,
            institutional_criteria,
            pattern_criteria,
            market_direction_ok,
        )

        # Financial metrics statistics: availability, not bullish pass counts.
        metrics_counts, signal_counts = _calculate_metric_coverage(companies)
        print_metrics_stats(
            metrics_counts,
            len(companies),
            signal_counts=signal_counts,
            include_insider=bool(config.get("insider_data", {}).get("enabled", False)),
            include_short_interest=bool(config.get("short_interest_data", {}).get("enabled", False)),
        )
        data_quality_warnings = _collect_data_quality_warnings(metrics_counts, len(companies), config)
        for warning in data_quality_warnings:
            logger.warning(warning)
        print_data_quality_warning(data_quality_warnings)

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
            and metrics_counts.get("institutional_holders_qoq_change", 0) == 0
            and metrics_counts.get("institutional_value_qoq_change", 0) == 0
        ):
            missing_enrich_reasons.append("기관 수급 지표가 없습니다. pure CANSLIM 프로필은 기관 보유/보유기관 수 또는 SEC 13F 기관 추세가 필요합니다")
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
            print_missing_enrich_warning(missing_enrich_reasons, enrich_cmd)
            return
        
        # 기준에 맞는 회사 필터링
        filtered_companies, criteria_counts = filter_screening_candidates(
            companies,
            criteria,
            leadership_criteria,
            supply_demand_criteria,
            institutional_criteria,
            pattern_criteria,
            market_direction_ok,
            test_mode,
        )
        
        # Screening criteria summary
        print_criteria_breakdown(criteria_counts, len(companies))
        
        logger.info(f"Found {len(filtered_companies)} companies passing screening criteria")
        
        # 결과 저장
        output_file = config.get("data_paths", {}).get("output_file", "data/processed/results.csv")
        
        if filtered_companies:
            _sort_screen_results(filtered_companies, config.get("profile_name", "default"))
            
            # DataFrame으로 변환하여 CSV로 저장
            df = pd.DataFrame(filtered_companies)
            df.to_csv(output_file, index=False)
            ResultsFormatter(config).export_to_markdown(df, {"total_companies": len(df)})
            logger.info(f"Results saved to {output_file}")
            
            # Rich 결과 테이블 출력
            print_results_table(filtered_companies, len(filtered_companies))
            print_saved_result(output_file)
        else:
            logger.warning("No companies passed the screening criteria")
            
            # 빈 결과 파일 생성
            with open(output_file, 'w') as f:
                f.write("No companies passed the screening criteria.\n")
            ResultsFormatter(config).export_to_markdown(pd.DataFrame(), {"total_companies": 0})
            print_results_table([], 0)
            print_saved_result(output_file)
    
    except Exception as e:
        logger.error(f"Error during stock screening: {e}")
        print(f"Error during stock screening: {e}")
        import traceback
        traceback.print_exc()

def show_status(config):
    """Print current local pipeline/data readiness."""
    status = collect_pipeline_status(config)
    print_pipeline_status(status)
    return status


def update_pipeline(config):
    """Run only missing pipeline stages, then screen when data prerequisites are ready."""
    status = show_status(config)
    if not status["download_ready"]:
        download_data(config)
        status = collect_pipeline_status(config)
    if not status["parse_ready"]:
        parse_data(config)
        status = collect_pipeline_status(config)
    if not status["enrich_ready"]:
        enrich_market_data(config, use_external_api=False)
        status = collect_pipeline_status(config)
    if status["institutional_required"] and not status["institutional_ready"]:
        print("\nInstitutional sponsorship data is required but missing.")
        if not config.get("institutional_data", {}).get("enabled", False):
            print("Enable institutional_data in config or run a 13F enrichment workflow before strict screening.")
        print_pipeline_status(status)
        return False
    screen_stocks(config)
    return True


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
        choices=["download", "parse", "enrich", "leadership", "financials", "screen", "status", "update", "analyze", "tv-export"],
        help="Operation mode: download SEC data, parse data, enrich data, screen stocks, export TradingView artifacts, inspect status, or update missing stages"
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
        "--ticker",
        help="Ticker to analyze when --mode analyze is used"
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
    config["config_path"] = args.config
    
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
    elif args.mode == "tv-export":
        summary = export_tradingview_artifacts(config)
        print("TradingView artifacts exported:")
        print(f"- Watchlist: {summary['watchlist_file']}")
        print(f"- Review plan: {summary['review_plan_file']}")
        print(f"- Symbols: {', '.join(summary['symbols'])}")
    elif args.mode == "status":
        show_status(config)
    elif args.mode == "update":
        update_pipeline(config)
    elif args.mode == "analyze":
        if not args.ticker:
            parser.error("--ticker is required when --mode analyze is used")
        print(format_ticker_analysis(analyze_ticker(args.ticker, config)))

if __name__ == "__main__":
    import logging
    main()
