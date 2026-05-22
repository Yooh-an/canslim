"""
Market Data Enricher

Module for enriching company data with market data from SEC EDGAR.
"""

import os
import json
import requests
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from pathlib import Path

from src.api.sec_client import SECClient
from src.collectors.insider_collector import enrich_companies_with_insider_data
from src.collectors.institutional_collector import enrich_companies_with_13f_data
from src.enrichers.pipeline import CompositeCompanyEnricher, FunctionCompanyEnricher
from src.screeners.market_direction import analyze_market_direction
from src.utils.security_classifier import apply_security_classification
from src.utils.yahoo_finance import configure_yfinance_user_agent

try:
    import yfinance as yf
    configure_yfinance_user_agent()
except ImportError:
    yf = None

logger = logging.getLogger(__name__)


def _print_progress(message: str) -> None:
    print(message, flush=True)


def _build_optional_enrichment_pipeline(config, sec_client=None) -> CompositeCompanyEnricher:
    """Build optional post-market enrichment steps from config."""
    enrichers = []
    if config.get("institutional_data", {}).get("enabled", False):
        enrichers.append(
            FunctionCompanyEnricher(
                name="sec_13f",
                enrich_func=lambda companies: enrich_companies_with_13f_data(
                    companies,
                    config,
                    sec_client=sec_client,
                ),
                before_message="[enrich] Starting SEC 13F institutional enrichment",
                after_message="[enrich] Applied SEC 13F institutional enrichment",
                progress=_print_progress,
            )
        )
    if config.get("insider_data", {}).get("enabled", False):
        enrichers.append(
            FunctionCompanyEnricher(
                name="sec_form4",
                enrich_func=lambda companies: enrich_companies_with_insider_data(
                    companies,
                    config,
                    sec_client=sec_client,
                ),
                before_message="[enrich] Starting SEC Form 4 insider enrichment",
                after_message="[enrich] Applied SEC Form 4 insider enrichment",
                progress=_print_progress,
            )
        )
    return CompositeCompanyEnricher(enrichers)


class MarketDataEnricher:
    """Enriches company data with market information from SEC data."""
    
    def __init__(self, config):
        """
        Initialize the MarketDataEnricher.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.quiet = bool(config.get("_quiet", False))
        
        logger.info("Using yfinance market data with SEC fallback")
        
        # Get paths from config
        data_paths = config.get("data_paths", {})
        self.processed_dir = data_paths.get("processed_data_dir", "data/processed")
        self.financial_data_dir = os.path.join(
            data_paths.get("raw_data_dir", "data/raw"), 
            "financial_data"
        )
        self.market_data_dir = os.path.join(self.financial_data_dir, "market_data")
        raw_data_dir = data_paths.get("raw_data_dir", "data/raw")
        self.price_cache_dir = os.path.join(
            raw_data_dir,
            "price_history",
        )
        self.sec_metadata_dir = os.path.join(raw_data_dir, "sec_company_metadata")
        self._ticker_cik_lookup_cache = None
        self._company_context_by_ticker = {}
        self._yfinance_rate_limited = False
        self._yfinance_rate_limit_warning_logged = False
        self._yfinance_info_rate_limited = False
        self._yfinance_info_rate_limit_warning_logged = False
        self._bulk_yfinance_fetch = False
        Path(self.market_data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.price_cache_dir).mkdir(parents=True, exist_ok=True)
        Path(self.sec_metadata_dir).mkdir(parents=True, exist_ok=True)

    def _progress(self, message: str) -> None:
        """Print progress even when logging handlers are not attached to this module."""
        logger.info(message)
        if not self.quiet:
            print(f"[enrich] {message}", flush=True)
    
    def enrich_companies_with_market_data(self, max_companies: int = 100) -> List[Dict]:
        """
        Enrich companies with market data from SEC.
        
        Args:
            max_companies: Maximum number of companies to enrich
            
        Returns:
            List of enriched company dictionaries
        """
        # Load companies list
        companies_list_file = os.path.join(self.processed_dir, "companies_list.json")
        if not os.path.exists(companies_list_file):
            logger.error(f"Companies list file not found: {companies_list_file}")
            return []
        
        with open(companies_list_file, 'r') as f:
            companies = json.load(f)
        
        logger.info(f"Loaded {len(companies)} companies for market data enrichment")
        self._progress(f"Loaded {len(companies)} companies")
        
        companies_to_enrich = self._prioritize_market_data_candidates(companies, max_companies)
        companies_by_ticker = {
            self._normalize_yahoo_ticker(company.get("ticker", "")): company
            for company in companies_to_enrich
            if company.get("ticker")
        }
        self._progress(f"Selected {len(companies_to_enrich)} companies / {len(companies_by_ticker)} tickers for market data")
        
        # Check for existing market data files
        market_data_dir = self.market_data_dir
            
        # Load existing market data files
        market_data = self._load_market_data_files(market_data_dir)
        tickers_to_fetch = [
            ticker for ticker in companies_by_ticker.keys()
            if not market_data.get(ticker, {}).get("market_cap")
        ]
        self._progress(f"Loaded cached market data for {len(market_data)} tickers; {len(tickers_to_fetch)} tickers need yfinance lookup")
        yf_market_data = self._fetch_yfinance_market_data(tickers_to_fetch)
        for ticker, data in yf_market_data.items():
            market_data.setdefault(ticker, {}).update(data)

        self._company_context_by_ticker = companies_by_ticker
        tickers_needing_sec_metadata = [
            ticker for ticker, company in companies_by_ticker.items()
            if not self._has_sec_industry_metadata(company)
            and not self._has_sec_industry_metadata(market_data.get(ticker, {}))
        ]
        sec_metadata = self._fetch_sec_metadata_for_tickers(tickers_needing_sec_metadata)
        for ticker, data in sec_metadata.items():
            market_data.setdefault(ticker, {}).update(data)
            self._save_market_data_file(ticker, market_data[ticker])

        self._progress("Calculating leadership, RS, volume, and pattern metrics")
        leadership_data = self._calculate_leadership_metrics(companies)
        for ticker, data in leadership_data.items():
            market_data.setdefault(ticker, {}).update(data)
        
        # Enrich companies with market data
        enriched_count = 0
        
        for i, company in enumerate(companies_to_enrich):
            ticker = company.get("ticker", "")
            if not ticker:
                continue
            yahoo_ticker = self._normalize_yahoo_ticker(ticker)
            
            # Check if we have market data for this ticker
            if yahoo_ticker in market_data:
                # Extract market cap and other metrics
                company_market_data = market_data[yahoo_ticker]
                
                # Add market cap
                if "market_cap" in company_market_data:
                    company["market_cap"] = company_market_data["market_cap"]
                    company["market_cap_source"] = company_market_data.get("market_cap_source", "sec_data")
                    enriched_count += 1
                
                # Add book value if available
                if "book_value" in company_market_data:
                    company["book_value"] = company_market_data["book_value"]
                
                # Add TTM metrics if available
                if "ttm_revenue" in company_market_data:
                    company["ttm_revenue"] = company_market_data["ttm_revenue"]
                
                if "ttm_net_income" in company_market_data:
                    company["ttm_net_income"] = company_market_data["ttm_net_income"]
                
                # Add P/S ratio if available
                if "price_to_sales" in company_market_data:
                    company["price_to_sales"] = company_market_data["price_to_sales"]

                if "current_price" in company_market_data:
                    company["current_price"] = company_market_data["current_price"]

                if "shares_outstanding" in company_market_data:
                    company["shares_outstanding"] = company_market_data["shares_outstanding"]

                for field in [
                    "price_return_3m",
                    "price_return_6m",
                    "price_return_9m",
                    "price_return_12m",
                    "market_outperformance_12m",
                    "rs_score",
                    "rs_rating",
                    "rs_line_near_high",
                    "rs_line_new_high",
                    "rs_line_pct_from_high",
                    "price_vs_52w_high",
                    "avg_dollar_volume_50d",
                    "volume_trend_50_200",
                    "up_down_volume_ratio_50d",
                    "volume_dry_up_ratio_10_50",
                    "breakout_volume_ratio",
                    "new_52w_high",
                    "recent_new_52w_high",
                    "recent_new_52w_high_days_ago",
                    "new_20d_high",
                    "base_depth_65d",
                    "base_tightness_3w",
                    "pivot_price",
                    "breakout_pct",
                    "near_pivot",
                    "valid_breakout",
                    "sma_50",
                    "sma_200",
                    "sector",
                    "industry",
                    "sic",
                    "sicDescription",
                    "entity_type",
                    "filer_category",
                    "institutional_ownership",
                    "institutional_holders",
                    "industry_rs_rank",
                    "industry_stock_rank",
                    "industry_group_leader",
                    "industry_stock_leader",
                    "industry_group",
                ]:
                    if field in company_market_data:
                        company[field] = company_market_data[field]
            
            # If no market data available, use SEC financial metrics to estimate
            if not company.get("market_cap") and company.get("equity") and company.get("assets"):
                book_value = company.get("equity", 0)
                
                # Use book value as a simple estimate if no other data available
                company["market_cap"] = book_value
                company["market_cap_source"] = "estimated_from_book_value"
                company["book_value"] = book_value
                enriched_count += 1
                
                # Add simple price to book ratio of 1.5x (conservative estimate)
                estimated_market_cap = book_value * 1.5
                company["estimated_market_cap"] = estimated_market_cap

            if (i + 1) % 500 == 0:
                self._progress(f"Applied market data to {i + 1}/{len(companies_to_enrich)} companies")
        
        classification_settings = self.config.get("security_classification", {})
        recent_listing_days = classification_settings.get("recent_listing_days", 730)
        for company in companies:
            apply_security_classification(company, recent_listing_days=recent_listing_days)

        logger.info(f"Enriched {enriched_count} companies with market data")
        self._progress(f"Enriched {enriched_count} companies with market data")
        
        # Save enriched data
        output_file = os.path.join(self.processed_dir, "companies_list_enriched.json")
        with open(output_file, 'w') as f:
            json.dump(companies, f, indent=2)
        
        logger.info(f"Saved enriched company data to {output_file}")
        self._progress(f"Saved enriched company data to {output_file}")
        return companies

    def enrich_companies_with_leadership_data(self) -> List[Dict]:
        """Add only price-based CAN SLIM leadership data, preserving existing enrichment."""
        enriched_file = os.path.join(self.processed_dir, "companies_list_enriched.json")
        companies_list_file = os.path.join(self.processed_dir, "companies_list.json")
        source_file = enriched_file if os.path.exists(enriched_file) else companies_list_file
        if not os.path.exists(source_file):
            logger.error(f"Companies list file not found: {source_file}")
            return []

        with open(source_file, "r") as f:
            companies = json.load(f)

        self._progress(f"Loaded {len(companies)} companies from {source_file}")
        self._progress("Skipping slow market-cap lookup; running only price/RS/volume/market-direction enrichment")
        leadership_data = self._calculate_leadership_metrics(companies, cached_only=True)
        if not leadership_data:
            self._progress("No leadership data was calculated")
            return companies

        leadership_fields = [
            "price_return_3m",
            "price_return_6m",
            "price_return_9m",
            "price_return_12m",
            "market_outperformance_12m",
            "rs_score",
            "rs_rating",
            "rs_line_near_high",
            "rs_line_new_high",
            "rs_line_pct_from_high",
            "price_vs_52w_high",
            "avg_dollar_volume_50d",
            "volume_trend_50_200",
            "up_down_volume_ratio_50d",
            "volume_dry_up_ratio_10_50",
            "breakout_volume_ratio",
            "new_52w_high",
            "recent_new_52w_high",
            "recent_new_52w_high_days_ago",
            "new_20d_high",
            "base_depth_65d",
            "base_tightness_3w",
            "pivot_price",
            "breakout_pct",
            "near_pivot",
            "valid_breakout",
            "sma_50",
            "sma_200",
            "industry_rs_rank",
            "industry_stock_rank",
            "industry_group_leader",
            "industry_stock_leader",
            "industry_group",
        ]

        updated = 0
        for company in companies:
            ticker = self._normalize_yahoo_ticker(company.get("ticker", ""))
            if not ticker or ticker not in leadership_data:
                continue
            metrics = leadership_data[ticker]
            for field in leadership_fields:
                if field in metrics:
                    company[field] = metrics[field]
            updated += 1

        classification_settings = self.config.get("security_classification", {})
        recent_listing_days = classification_settings.get("recent_listing_days", 730)
        for company in companies:
            apply_security_classification(company, recent_listing_days=recent_listing_days)

        for output_file in [enriched_file, companies_list_file]:
            with open(output_file, "w") as f:
                json.dump(companies, f, indent=2)
        self._progress(f"Applied leadership data to {updated} companies")
        self._progress(f"Saved updated files: {enriched_file}, {companies_list_file}")
        return companies

    def _prioritize_market_data_candidates(self, companies: List[Dict], max_companies: Optional[int]) -> List[Dict]:
        """Prefer likely screen results before applying the cap."""
        market_data_config = self.config.get("market_data", {})
        prefer_screenable_only = market_data_config.get("enrich_only_screenable_candidates", True)

        metric_fields = [
            "quarterly_eps_growth",
            "annual_eps_cagr",
            "revenue_growth",
            "profit_margin",
            "roe",
            "debt_to_equity",
        ]
        financial_candidates = [
            company for company in companies
            if self._passes_non_market_screen(company)
        ]
        with_metrics = [
            company for company in companies
            if any(pd.notna(company.get(field)) for field in metric_fields)
        ]
        if prefer_screenable_only:
            prioritized = financial_candidates or with_metrics
        else:
            prioritized = [company for company in companies if company.get("ticker")]

        if not prioritized:
            prioritized = [company for company in companies if company.get("ticker")]

        if max_companies and max_companies > 0:
            prioritized = prioritized[:max_companies]
        logger.info(f"Selected {len(prioritized)} companies for market data enrichment")
        return prioritized

    def _passes_non_market_screen(self, company: Dict[str, Any]) -> bool:
        """Check the financial filters that do not require market data."""
        criteria = self.config.get("screening_criteria", {})
        required_minimums = {
            "quarterly_eps_growth": criteria.get("quarterly_eps_growth", 0),
            "annual_eps_cagr": criteria.get("annual_eps_cagr", 0),
            "revenue_growth": criteria.get("revenue_growth", 0),
            "profit_margin": criteria.get("profit_margin", 0),
            "roe": criteria.get("roe", 0),
        }
        for field, threshold in required_minimums.items():
            value = company.get(field)
            if not pd.notna(value) or value < threshold:
                return False

        debt_to_equity = company.get("debt_to_equity")
        if not pd.notna(debt_to_equity):
            return False
        if debt_to_equity > 0 and debt_to_equity > criteria.get("debt_to_equity", float("inf")):
            return False

        return bool(company.get("ticker"))

    @staticmethod
    def _normalize_yahoo_ticker(ticker: str) -> str:
        """Convert SEC-style class tickers to Yahoo Finance symbols."""
        if not ticker:
            return ""
        return str(ticker).strip().replace(".", "-")

    def _fetch_yfinance_market_data(self, tickers: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch free market-cap data from Yahoo Finance through yfinance."""
        if yf is None:
            logger.warning("yfinance is not installed; skipping live market data")
            return {}

        market_data = {}
        unique_tickers = [ticker for ticker in dict.fromkeys(tickers) if ticker]
        logger.info(f"Fetching yfinance market data for {len(unique_tickers)} tickers")
        if not unique_tickers:
            self._progress("No uncached yfinance market-cap lookups needed")
            return {}
        self._progress(f"Fetching yfinance market-cap data for {len(unique_tickers)} tickers")
        max_workers = self.config.get("market_data", {}).get(
            "yfinance_max_workers",
            self.config.get("download_settings", {}).get("max_workers", 4),
        )
        max_workers = max(1, min(int(max_workers), 12))
        use_info_fallback = self.config.get("market_data", {}).get("use_yfinance_info_fallback", False)
        if use_info_fallback:
            self._progress("Using sequential yfinance lookups because info fallback is enabled")
            previous_bulk_state = self._bulk_yfinance_fetch
            self._bulk_yfinance_fetch = True
            try:
                for index, ticker in enumerate(unique_tickers, start=1):
                    if self._yfinance_rate_limited:
                        self._progress(
                            f"Stopping yfinance market-data lookups after rate limit; skipped {len(unique_tickers) - index + 1} tickers"
                        )
                        break
                    try:
                        if index == 1 or index % 10 == 0:
                            self._progress(f"Yfinance market-cap lookup {index}/{len(unique_tickers)}: {ticker}")
                        data = self._fetch_single_yfinance_ticker(ticker)
                        if data:
                            market_data[ticker] = data
                            self._save_market_data_file(ticker, data)
                        if index % 25 == 0:
                            logger.info(f"Fetched yfinance data for {index}/{len(unique_tickers)} tickers")
                            self._progress(f"Fetched yfinance market-cap data for {index}/{len(unique_tickers)} tickers")
                    except Exception as e:
                        logger.warning(f"Failed to fetch yfinance data for {ticker}: {e}")
                        self._progress(f"Failed yfinance market-cap lookup {index}/{len(unique_tickers)}: {ticker} ({e})")
            finally:
                self._bulk_yfinance_fetch = previous_bulk_state
        else:
            self._progress(f"Using {max_workers} workers for yfinance market-data lookups")
            previous_bulk_state = self._bulk_yfinance_fetch
            self._bulk_yfinance_fetch = True
            try:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_ticker = {
                        executor.submit(self._fetch_single_yfinance_ticker, ticker): ticker
                        for ticker in unique_tickers
                    }
                    for index, future in enumerate(as_completed(future_to_ticker), start=1):
                        ticker = future_to_ticker[future]
                        try:
                            if index == 1 or index % 10 == 0:
                                self._progress(f"Yfinance market-cap lookup {index}/{len(unique_tickers)}: {ticker}")
                            data = future.result()
                            if data:
                                market_data[ticker] = data
                                self._save_market_data_file(ticker, data)

                            if index % 25 == 0:
                                logger.info(f"Fetched yfinance data for {index}/{len(unique_tickers)} tickers")
                                self._progress(f"Fetched yfinance market-cap data for {index}/{len(unique_tickers)} tickers")
                        except Exception as e:
                            logger.warning(f"Failed to fetch yfinance data for {ticker}: {e}")
                            self._progress(f"Failed yfinance market-cap lookup {index}/{len(unique_tickers)}: {ticker} ({e})")
            finally:
                self._bulk_yfinance_fetch = previous_bulk_state

        logger.info(f"Fetched yfinance market data for {len(market_data)} tickers")
        self._progress(f"Fetched yfinance market data for {len(market_data)} tickers")
        return market_data

    def _calculate_leadership_metrics(self, companies: List[Dict[str, Any]], cached_only: bool = False) -> Dict[str, Dict[str, Any]]:
        """Calculate CAN SLIM leadership metrics from price and volume history."""
        if yf is None:
            logger.warning("yfinance is not installed; skipping leadership metrics")
            return {}

        market_data_config = self.config.get("market_data", {})
        leadership_universe_size = market_data_config.get("leadership_universe_size", 200)
        metric_universe = [
            company for company in self._prioritize_leadership_universe(companies, leadership_universe_size)
            if company.get("ticker") and (leadership_universe_size is None or self._has_financial_metrics(company))
        ]
        if not metric_universe:
            logger.warning("No companies with financial metrics available for leadership calculations")
            return {}

        ticker_to_company = {
            self._normalize_yahoo_ticker(company.get("ticker")): company
            for company in metric_universe
        }
        tickers = list(ticker_to_company.keys())
        cached_market_data = self._load_market_data_files(self.market_data_dir)
        self._company_context_by_ticker.update(ticker_to_company)
        tickers_needing_sec_metadata = [
            ticker for ticker in tickers
            if not self._has_sec_industry_metadata(ticker_to_company.get(ticker, {}))
            and not self._has_sec_industry_metadata(cached_market_data.get(ticker, {}))
        ]
        sec_metadata = self._fetch_sec_metadata_for_tickers(tickers_needing_sec_metadata)
        for ticker, data in sec_metadata.items():
            cached_market_data.setdefault(ticker, {}).update(data)
            self._save_market_data_file(ticker, cached_market_data[ticker])

        benchmark = market_data_config.get("leadership_benchmark", "SPY")
        period = market_data_config.get("leadership_period", "15mo")
        chunk_size = market_data_config.get("leadership_chunk_size", 100)

        logger.info(f"Calculating leadership metrics for {len(tickers)} tickers")
        self._progress(f"Calculating leadership metrics for {len(tickers)} tickers")
        price_history = self._download_price_history(tickers, period, chunk_size, cached_only=cached_only)
        benchmark_history = self._download_single_history(benchmark, period)
        self._save_market_direction(benchmark_history, market_data_config)
        if not price_history:
            return {}

        benchmark_close = self._history_series(benchmark_history, "Close")
        if benchmark_close.empty:
            benchmark_close = None
        results = {}
        for index, (ticker, history) in enumerate(price_history.items(), start=1):
            metrics = self._calculate_single_leadership_metrics(history, benchmark_close)
            if metrics:
                group = self._industry_group_for_company(ticker_to_company[ticker])
                if not group:
                    group = self._industry_group_for_company(cached_market_data.get(ticker, {}))
                metrics["ticker"] = ticker
                if group:
                    metrics["industry_group"] = group
                results[ticker] = metrics
            if index % 500 == 0:
                self._progress(f"Calculated leadership metrics for {index}/{len(price_history)} price histories")

        self._add_percentile_ranks(results, "rs_score", "rs_rating", scale=99)
        self._add_industry_ranks(results)

        for ticker, metrics in results.items():
            cached = cached_market_data.get(ticker, {})
            cached.update(metrics)
            self._save_market_data_file(ticker, cached)

        logger.info(f"Calculated leadership metrics for {len(results)} tickers")
        self._progress(f"Calculated leadership metrics for {len(results)} tickers")
        return results

    def enrich_single_ticker_market_data(self, company: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch/cache market, price, RS, and volume metrics for a single ticker.

        This is used by single-ticker analysis so users do not need to rerun a
        full-universe enrichment just to fill one newly mapped ticker.
        """
        output = dict(company)
        ticker = self._normalize_yahoo_ticker(output.get("ticker", ""))
        if not ticker:
            return output

        market_data = self._load_market_data_files(self.market_data_dir).get(ticker, {})
        fetched_market = self._fetch_yfinance_market_data([ticker]).get(ticker, {})
        market_data.update(fetched_market)

        market_data_config = self.config.get("market_data", {})
        period = market_data_config.get("leadership_period", "15mo")
        chunk_size = market_data_config.get("leadership_chunk_size", 100)
        histories = self._download_price_history([ticker], period, chunk_size)
        history = histories.get(ticker)
        benchmark_history = self._download_single_history(market_data_config.get("leadership_benchmark", "SPY"), period)
        benchmark_close = self._history_series(benchmark_history, "Close")
        if benchmark_close.empty:
            benchmark_close = None

        if history is not None and not history.empty:
            metrics = self._calculate_single_leadership_metrics(history, benchmark_close)
            close = self._history_series(history, "Close")
            if not close.empty:
                latest_close = float(close.iloc[-1])
                metrics["current_price"] = latest_close
                shares = market_data.get("shares_outstanding") or output.get("shares_outstanding")
                if shares and not market_data.get("market_cap"):
                    try:
                        metrics["market_cap"] = int(latest_close * float(shares))
                        metrics["market_cap_source"] = "price_history_x_shares"
                    except (TypeError, ValueError):
                        pass
            market_data.update(metrics)

        cached_market_data = self._load_market_data_files(self.market_data_dir)
        ranking_pool = {
            pool_ticker: dict(values)
            for pool_ticker, values in cached_market_data.items()
            if pd.notna(values.get("rs_score"))
        }
        if pd.notna(market_data.get("rs_score")):
            ranking_pool[ticker] = dict(market_data)
            self._add_percentile_ranks(ranking_pool, "rs_score", "rs_rating", scale=99)
            if ticker in ranking_pool and "rs_rating" in ranking_pool[ticker]:
                market_data["rs_rating"] = ranking_pool[ticker]["rs_rating"]

        if market_data:
            self._save_market_data_file(ticker, {**market_data, "ticker": ticker})
            output.update(market_data)
        return output

    def _prioritize_leadership_universe(self, companies: List[Dict[str, Any]], max_companies: Optional[int]) -> List[Dict[str, Any]]:
        """Limit free price-history downloads to the highest-value universe."""
        if max_companies is None:
            prioritized = [company for company in companies if company.get("ticker")]
            logger.info(f"Selected {len(prioritized)} companies for leadership calculations")
            return prioritized

        financial_candidates = [
            company for company in companies
            if self._passes_non_market_screen(company)
        ]
        remaining = [
            company for company in companies
            if id(company) not in {id(candidate) for candidate in financial_candidates}
            and self._has_financial_metrics(company)
        ]
        remaining.sort(
            key=lambda company: sum(
                float(company.get(field) or 0)
                for field in ["quarterly_eps_growth", "annual_eps_cagr", "revenue_growth", "roe"]
                if pd.notna(company.get(field))
            ),
            reverse=True,
        )
        prioritized = financial_candidates + remaining
        if max_companies and max_companies > 0:
            prioritized = prioritized[:max_companies]
        logger.info(f"Selected {len(prioritized)} companies for leadership calculations")
        return prioritized

    @staticmethod
    def _has_financial_metrics(company: Dict[str, Any]) -> bool:
        fields = [
            "quarterly_eps_growth",
            "annual_eps_cagr",
            "revenue_growth",
            "profit_margin",
            "roe",
            "debt_to_equity",
        ]
        return any(pd.notna(company.get(field)) for field in fields)

    def _download_price_history(
        self,
        tickers: List[str],
        period: str,
        chunk_size: int,
        cached_only: bool = False,
    ) -> Dict[str, pd.DataFrame]:
        """Download OHLCV history in chunks, reusing local cache where possible."""
        histories = {}
        missing = []
        for ticker in tickers:
            cached = self._load_price_history_cache(ticker)
            if cached is not None:
                histories[ticker] = cached
            else:
                missing.append(ticker)

        logger.info(f"Loaded cached price history for {len(histories)} tickers; {len(missing)} need download")
        self._progress(f"Loaded cached price history for {len(histories)} tickers; {len(missing)} need download")
        if cached_only and histories:
            self._progress(f"Using cached price history only; skipping {len(missing)} uncached tickers")
            logger.info("Skipping uncached price history downloads because cached_only=True")
            return histories

        for start in range(0, len(missing), chunk_size):
            chunk = missing[start:start + chunk_size]
            chunk_number = start // chunk_size + 1
            total_chunks = (len(missing) + chunk_size - 1) // chunk_size
            self._progress(f"Downloading price history chunk {chunk_number}/{total_chunks} ({len(chunk)} tickers)")
            try:
                downloaded = yf.download(
                    tickers=" ".join(chunk),
                    period=period,
                    interval="1d",
                    auto_adjust=True,
                    group_by="ticker",
                    progress=False,
                    threads=True,
                )
            except Exception as e:
                logger.warning(f"Failed to download price history for chunk {start // chunk_size + 1}: {e}")
                continue

            if downloaded.empty:
                for ticker in chunk:
                    history = self._download_yahoo_chart_history(ticker, period)
                    if history is not None and not history.empty:
                        histories[ticker] = history
                        self._save_price_history_cache(ticker, history)
                continue

            if len(chunk) == 1:
                history = downloaded.dropna(how="all")
                if history.empty:
                    history = self._download_yahoo_chart_history(chunk[0], period)
                if history is not None and not history.empty:
                    histories[chunk[0]] = history
                    self._save_price_history_cache(chunk[0], history)
                continue

            for ticker in chunk:
                if ticker in downloaded.columns.get_level_values(0):
                    ticker_df = downloaded[ticker].dropna(how="all")
                    if not ticker_df.empty:
                        histories[ticker] = ticker_df
                        self._save_price_history_cache(ticker, ticker_df)

        logger.info(f"Available price history for {len(histories)} tickers")
        self._progress(f"Available price history for {len(histories)} tickers")
        return histories

    def _download_single_history(self, ticker: str, period: str) -> Optional[pd.DataFrame]:
        cached = self._load_price_history_cache(ticker)
        if cached is not None:
            return cached
        try:
            data = yf.download(
                tickers=ticker,
                period=period,
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            history = data.dropna(how="all") if not data.empty else None
        except Exception:
            history = None

        if history is None or history.empty:
            history = self._download_yahoo_chart_history(ticker, period)

        if history is not None and not history.empty:
            self._save_price_history_cache(ticker, history)
        return history

    @staticmethod
    def _chart_response_to_history(payload: Dict[str, Any]) -> Optional[pd.DataFrame]:
        result = (payload.get("chart", {}).get("result") or [None])[0]
        if not result or not result.get("timestamp"):
            return None
        quote = (result.get("indicators", {}).get("quote") or [None])[0]
        if not quote:
            return None
        index = pd.to_datetime(result["timestamp"], unit="s")
        history = pd.DataFrame(
            {
                "Open": quote.get("open"),
                "High": quote.get("high"),
                "Low": quote.get("low"),
                "Close": quote.get("close"),
                "Volume": quote.get("volume"),
            },
            index=index,
        )
        return history.dropna(how="all")

    def _download_yahoo_chart_history(self, ticker: str, period: str) -> Optional[pd.DataFrame]:
        """Fallback to Yahoo's chart endpoint when yfinance returns empty data."""
        try:
            response = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
                params={"range": period, "interval": "1d", "includePrePost": "false"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=30,
            )
            response.raise_for_status()
            return self._chart_response_to_history(response.json())
        except Exception as e:
            logger.debug(f"Yahoo chart fallback failed for {ticker}: {e}")
            return None

    def _price_cache_file(self, ticker: str) -> str:
        safe_ticker = ticker.replace("/", "-")
        return os.path.join(self.price_cache_dir, f"{safe_ticker}.csv")

    def _load_price_history_cache(self, ticker: str) -> Optional[pd.DataFrame]:
        cache_file = self._price_cache_file(ticker)
        if not os.path.exists(cache_file):
            return None

        max_age_days = self.config.get("market_data", {}).get("price_cache_max_age_days", 2)
        try:
            modified_at = pd.Timestamp(os.path.getmtime(cache_file), unit="s", tz="UTC")
            age_days = (pd.Timestamp.utcnow() - modified_at).total_seconds() / 86400
            if max_age_days is not None and age_days > max_age_days:
                return None

            data = pd.read_csv(cache_file, index_col=0)
            if data.empty or self._history_series(data, "Close").empty:
                return None
            return data.dropna(how="all")
        except Exception as e:
            logger.debug(f"Failed to load price cache for {ticker}: {e}")
            return None

    def _save_price_history_cache(self, ticker: str, history: pd.DataFrame) -> None:
        if history is None or history.empty:
            return
        try:
            history.to_csv(self._price_cache_file(ticker))
        except Exception as e:
            logger.debug(f"Failed to save price cache for {ticker}: {e}")

    def _history_series(self, history: Optional[pd.DataFrame], field: str) -> pd.Series:
        """Extract one numeric OHLCV series from normal, duplicate, or MultiIndex columns."""
        if history is None or history.empty:
            return pd.Series(dtype=float)

        candidates = []
        if isinstance(history, pd.Series):
            candidates.append(history)
        elif isinstance(history.columns, pd.MultiIndex):
            for level in range(history.columns.nlevels):
                values = history.columns.get_level_values(level)
                mask = values == field
                if mask.any():
                    candidates.append(history.loc[:, mask])
        else:
            if field in history.columns:
                candidates.append(history.loc[:, field])
            lower_field = field.lower()
            for column in history.columns:
                if str(column).lower() == lower_field and column != field:
                    candidates.append(history.loc[:, column])

        for candidate in candidates:
            series = self._first_numeric_series(candidate)
            if not series.empty:
                return series
        return pd.Series(dtype=float)

    @staticmethod
    def _first_numeric_series(data: Any) -> pd.Series:
        if isinstance(data, pd.DataFrame):
            for column_index in range(data.shape[1]):
                series = MarketDataEnricher._coerce_numeric_history_series(data.iloc[:, column_index])
                if not series.empty:
                    return series
            return pd.Series(dtype=float)
        return MarketDataEnricher._coerce_numeric_history_series(data)

    @staticmethod
    def _coerce_numeric_history_series(data: Any) -> pd.Series:
        series = pd.Series(data).copy()
        series = pd.to_numeric(series, errors="coerce")
        index_labels = pd.Index(series.index).astype(str)
        series = series[~index_labels.isin({"Ticker", "Date", "Price"})]
        index = pd.to_datetime(series.index, errors="coerce")
        series.index = index
        series = series[~series.index.isna()].dropna()
        if series.empty:
            return pd.Series(dtype=float)
        series = series[~series.index.duplicated(keep="last")].sort_index()
        return series.astype(float)

    def _calculate_single_leadership_metrics(
        self,
        history: pd.DataFrame,
        benchmark_close: Optional[pd.Series],
    ) -> Dict[str, Any]:
        if history.empty:
            return {}

        close = self._history_series(history, "Close")
        volume = self._history_series(history, "Volume")
        if len(close) < 60:
            return {}

        returns = {
            "price_return_3m": self._return_over_days(close, 63),
            "price_return_6m": self._return_over_days(close, 126),
            "price_return_9m": self._return_over_days(close, 189),
            "price_return_12m": self._return_over_days(close, 252),
        }
        rs_score = (
            0.4 * returns["price_return_3m"]
            + 0.2 * returns["price_return_6m"]
            + 0.2 * returns["price_return_9m"]
            + 0.2 * returns["price_return_12m"]
        )

        high = self._history_series(history, "High")
        high_source = high if not high.empty else close
        high_52w_series = high_source.tail(252)
        high_52w = high_52w_series.max()
        price_vs_52w_high = close.iloc[-1] / high_52w if high_52w and high_52w > 0 else np.nan
        high_20d = high_source.tail(20).max()
        recent_new_high_lookback = int(
            self.config.get("market_data", {}).get("recent_new_high_lookback_days", 10) or 0
        )
        recent_new_high = False
        recent_new_high_days_ago = np.nan
        if recent_new_high_lookback > 0 and pd.notna(high_52w) and high_52w > 0:
            recent_window = high_52w_series.tail(recent_new_high_lookback)
            recent_matches = recent_window[recent_window >= high_52w * 0.995]
            if not recent_matches.empty:
                recent_new_high = True
                recent_new_high_days_ago = int(len(high_source) - 1 - high_source.index.get_loc(recent_matches.index[-1]))
        base_window = close.tail(65)
        base_depth = (base_window.max() - base_window.min()) / base_window.max() if len(base_window) >= 30 and base_window.max() > 0 else np.nan
        base_tightness = float(close.pct_change().tail(15).std()) if len(close) >= 20 else np.nan
        pivot_window = close.iloc[-55:-5] if len(close) >= 60 else pd.Series(dtype=float)
        pivot_price = float(pivot_window.max()) if not pivot_window.empty else np.nan
        breakout_pct = float(close.iloc[-1] / pivot_price - 1) if pd.notna(pivot_price) and pivot_price > 0 else np.nan

        # Moving average calculations for general technical trend analysis
        sma_50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else np.nan
        sma_200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else np.nan

        metrics = {
            **returns,
            "rs_score": rs_score,
            "price_vs_52w_high": price_vs_52w_high,
            "new_52w_high": bool(close.iloc[-1] >= high_52w * 0.995) if pd.notna(high_52w) and high_52w > 0 else False,
            "recent_new_52w_high": recent_new_high,
            "recent_new_52w_high_days_ago": recent_new_high_days_ago,
            "new_20d_high": bool(close.iloc[-1] >= high_20d * 0.995) if pd.notna(high_20d) and high_20d > 0 else False,
            "base_depth_65d": float(base_depth) if pd.notna(base_depth) else np.nan,
            "base_tightness_3w": base_tightness,
            "pivot_price": pivot_price,
            "breakout_pct": breakout_pct,
            "near_pivot": bool(-0.05 <= breakout_pct <= 0.05) if pd.notna(breakout_pct) else False,
            "sma_50": sma_50,
            "sma_200": sma_200,
        }

        if benchmark_close is not None and len(benchmark_close.dropna()) >= 60:
            aligned = pd.concat([close, benchmark_close.dropna()], axis=1, join="inner").dropna()
            if len(aligned) >= 60:
                aligned.columns = ["stock", "benchmark"]
                rs_line = aligned["stock"] / aligned["benchmark"]
                rs_line_high = rs_line.tail(252).max()
                latest_rs_line = rs_line.iloc[-1]
                metrics["rs_line_near_high"] = bool(latest_rs_line >= rs_line_high * self.config.get("leadership_criteria", {}).get("rs_line_high_threshold", 0.95))
                metrics["rs_line_new_high"] = bool(latest_rs_line >= rs_line_high) if pd.notna(rs_line_high) and rs_line_high > 0 else False
                metrics["rs_line_pct_from_high"] = float(latest_rs_line / rs_line_high - 1) if pd.notna(rs_line_high) and rs_line_high > 0 else np.nan
                metrics["market_outperformance_12m"] = self._return_over_days(aligned["stock"], 252) - self._return_over_days(aligned["benchmark"], 252)

        if not volume.empty:
            price_volume = pd.concat([close, volume], axis=1, join="inner").dropna()
            price_volume.columns = ["close", "volume"]
            dollar_volume = price_volume["close"] * price_volume["volume"]
            if len(dollar_volume) >= 50:
                metrics["avg_dollar_volume_50d"] = float(dollar_volume.tail(50).mean())
            if len(price_volume) >= 200:
                avg_200 = price_volume["volume"].tail(200).mean()
                metrics["volume_trend_50_200"] = float(price_volume["volume"].tail(50).mean() / avg_200) if avg_200 else np.nan
            if len(price_volume) >= 50:
                recent = price_volume.tail(50).copy()
                recent["price_change"] = recent["close"].diff()
                up_volume = recent.loc[recent["price_change"] > 0, "volume"].sum()
                down_volume = recent.loc[recent["price_change"] < 0, "volume"].sum()
                if down_volume > 0:
                    metrics["up_down_volume_ratio_50d"] = float(up_volume / down_volume)
                elif up_volume > 0:
                    metrics["up_down_volume_ratio_50d"] = float("inf")
                else:
                    metrics["up_down_volume_ratio_50d"] = np.nan
                avg_50 = recent["volume"].mean()
                metrics["volume_dry_up_ratio_10_50"] = float(price_volume["volume"].tail(10).mean() / avg_50) if avg_50 else np.nan
                metrics["breakout_volume_ratio"] = float(price_volume["volume"].iloc[-1] / avg_50) if avg_50 else np.nan
                metrics["valid_breakout"] = bool(
                    pd.notna(metrics.get("breakout_pct"))
                    and 0 <= metrics["breakout_pct"] <= 0.05
                    and metrics["breakout_volume_ratio"] >= self.config.get("pattern_criteria", {}).get("breakout_volume_ratio_min", 1.4)
                )
            else:
                metrics["valid_breakout"] = False

        return metrics

    def _save_market_direction(self, benchmark_history: Optional[pd.DataFrame], market_data_config: Dict[str, Any]) -> None:
        """Persist a simple CAN SLIM M proxy from index trend and distribution days."""
        if benchmark_history is None or benchmark_history.empty:
            return

        output = analyze_market_direction(
            benchmark_history,
            benchmark=market_data_config.get("leadership_benchmark", "SPY"),
            rally_lookback=market_data_config.get("rally_lookback_days", 30),
            distribution_lookback=market_data_config.get("distribution_lookback_days", 25),
            ftd_min_gain=market_data_config.get("follow_through_min_gain", 0.0125),
            ftd_min_day=market_data_config.get("follow_through_min_day", 4),
            ftd_max_day=market_data_config.get("follow_through_max_day", 10),
        )
        if output.get("market_direction_status") == "unknown":
            return
        output_file = os.path.join(self.processed_dir, "market_direction.json")
        try:
            with open(output_file, "w") as f:
                json.dump(output, f, indent=2)
            logger.info(f"Saved market direction data to {output_file}: {output.get('market_direction_status')}")
        except Exception as e:
            logger.warning(f"Failed to save market direction data: {e}")

    @staticmethod
    def _distribution_days(close: pd.Series, volume: pd.Series, lookback: int = 25) -> int:
        if volume.empty:
            return 0
        aligned = pd.concat([close, volume], axis=1, join="inner").dropna()
        aligned.columns = ["close", "volume"]
        if len(aligned) < 2:
            return 0
        recent = aligned.tail(lookback + 1).copy()
        recent["price_change"] = recent["close"].pct_change()
        recent["volume_change"] = recent["volume"].diff()
        distribution = (recent["price_change"] <= -0.002) & (recent["volume_change"] > 0)
        return int(distribution.tail(lookback).sum())

    @staticmethod
    def _return_over_days(close: pd.Series, days: int) -> float:
        if len(close) <= days:
            first = close.iloc[0]
        else:
            first = close.iloc[-days - 1]
        last = close.iloc[-1]
        if not first or first <= 0:
            return np.nan
        return float(last / first - 1)

    @staticmethod
    def _industry_group_for_company(company: Dict[str, Any]) -> str:
        return (
            str(company.get("sicDescription") or "").strip()
            or str(company.get("sic_description") or "").strip()
            or str(company.get("industry") or "").strip()
            or str(company.get("sector") or "").strip()
            or str(company.get("sic") or "").strip()
            or str(company.get("category") or "").strip()
        )

    def _has_industry_group_metadata(self, company: Dict[str, Any]) -> bool:
        return bool(self._industry_group_for_company(company or {}))

    @staticmethod
    def _has_sec_industry_metadata(company: Dict[str, Any]) -> bool:
        company = company or {}
        return bool(
            str(company.get("sicDescription") or "").strip()
            or str(company.get("sic_description") or "").strip()
        )

    @staticmethod
    def _add_percentile_ranks(results: Dict[str, Dict[str, Any]], source_field: str, target_field: str, scale: int = 100) -> None:
        values = pd.Series({
            ticker: metrics.get(source_field)
            for ticker, metrics in results.items()
            if pd.notna(metrics.get(source_field))
        })
        if values.empty:
            return
        if target_field == "rs_rating" and len(values) < 200:
            logger.warning(
                f"[enrich] Warning: RS rating is being ranked against a small subset of {len(values)} tickers "
                "instead of the entire market. Consider running the enrichment process without company_limit "
                "for accurate relative strength percentile ranks."
            )
        ranks = values.rank(pct=True) * scale
        for ticker, rank in ranks.items():
            results[ticker][target_field] = float(rank)

    def _add_industry_ranks(self, results: Dict[str, Dict[str, Any]]) -> None:
        rows = [
            {"ticker": ticker, "industry_group": metrics.get("industry_group"), "rs_score": metrics.get("rs_score")}
            for ticker, metrics in results.items()
            if metrics.get("industry_group") and pd.notna(metrics.get("rs_score"))
        ]
        if not rows:
            return

        df = pd.DataFrame(rows)
        industry_scores = df.groupby("industry_group")["rs_score"].mean()
        industry_ranks = industry_scores.rank(pct=True) * 100
        stock_ranks = df.groupby("industry_group")["rs_score"].rank(pct=True) * 100
        df["industry_stock_rank"] = stock_ranks

        for _, row in df.iterrows():
            ticker = row["ticker"]
            group = row["industry_group"]
            results[ticker]["industry_rs_rank"] = float(industry_ranks[group])
            results[ticker]["industry_stock_rank"] = float(row["industry_stock_rank"])
            results[ticker]["industry_group_leader"] = bool(industry_ranks[group] >= 80)
            results[ticker]["industry_stock_leader"] = bool(row["industry_stock_rank"] >= 80)

    def _fetch_single_yfinance_ticker(self, ticker: str) -> Dict[str, Any]:
        """Fetch one ticker with fast_info first, then fall back to info."""
        yf_ticker = yf.Ticker(ticker)
        data = {"ticker": ticker, "market_cap_source": "yfinance", "data_date": pd.Timestamp.utcnow().date().isoformat()}

        fast_info = getattr(yf_ticker, "fast_info", None)
        if fast_info:
            market_cap = self._safe_fast_info_get(fast_info, "market_cap")
            current_price = self._safe_fast_info_get(fast_info, "last_price")
            shares = self._safe_fast_info_get(fast_info, "shares")
            if market_cap:
                data["market_cap"] = int(market_cap)
            if current_price:
                data["current_price"] = float(current_price)
            if shares:
                data["shares_outstanding"] = int(shares)

        market_data_config = self.config.get("market_data", {})
        use_info_fallback = market_data_config.get("use_yfinance_info_fallback", False)
        if self._yfinance_rate_limited or self._yfinance_info_rate_limited:
            use_info_fallback = False
        if use_info_fallback:
            try:
                info = yf_ticker.get_info()
            except Exception as exc:
                if self._is_yfinance_rate_limit_error(exc):
                    self._yfinance_info_rate_limited = True
                    if not self._yfinance_info_rate_limit_warning_logged:
                        logger.warning(
                            "Yahoo Finance info endpoint is rate-limited; pausing get_info() for the rest of this enrichment run. "
                            "Continuing with fast_info and SEC company metadata."
                        )
                        self._yfinance_info_rate_limit_warning_logged = True
                else:
                    logger.warning(f"Failed to fetch yfinance info for {ticker}: {exc}")
                info = {}
            market_cap = info.get("marketCap")
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
            if market_cap and "market_cap" not in data:
                data["market_cap"] = int(market_cap)
            if current_price and "current_price" not in data:
                data["current_price"] = float(current_price)
            if shares and "shares_outstanding" not in data:
                data["shares_outstanding"] = int(shares)
            for source, target in [
                ("sector", "sector"),
                ("industry", "industry"),
                ("heldPercentInstitutions", "institutional_ownership"),
                ("numberOfInstitutionalHolders", "institutional_holders"),
            ]:
                value = info.get(source)
                if value is not None:
                    data[target] = value
            if "institutional_ownership" in data or "institutional_holders" in data:
                data["institutional_data_source"] = "yfinance_info"

        if not self._has_industry_group_metadata(data):
            sec_metadata = self._fetch_sec_company_metadata_for_ticker(ticker)
            if sec_metadata:
                data.update(sec_metadata)

        return data if len(data) > 3 else {}

    def _fetch_sec_metadata_for_tickers(self, tickers: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch/cache SEC company metadata for tickers missing industry group data.

        Yahoo's quoteSummary endpoint is aggressively rate-limited.  SEC's
        submissions endpoint provides stable SIC descriptions, which are good
        enough to build an industry-group ranking fallback when Yahoo sector or
        industry metadata is unavailable.
        """
        unique_tickers = [ticker for ticker in dict.fromkeys(tickers) if ticker]
        if not unique_tickers:
            return {}

        self._progress(f"Fetching SEC company metadata for {len(unique_tickers)} tickers missing industry data")
        metadata: Dict[str, Dict[str, Any]] = {}
        delay = float(self.config.get("sec_api", {}).get("rate_limit_delay", 0.1) or 0)
        for index, ticker in enumerate(unique_tickers, start=1):
            data = self._fetch_sec_company_metadata_for_ticker(ticker)
            if data:
                metadata[ticker] = data
            if delay > 0 and index < len(unique_tickers):
                time.sleep(delay)
        self._progress(f"Fetched SEC company metadata for {len(metadata)}/{len(unique_tickers)} tickers")
        return metadata

    def _fetch_sec_company_metadata_for_ticker(self, ticker: str) -> Dict[str, Any]:
        cik = self._cik_for_ticker(ticker)
        if not cik:
            return {}
        return self._fetch_sec_company_metadata_by_cik(cik, ticker=ticker)

    def _cik_for_ticker(self, ticker: str) -> Optional[str]:
        normalized = self._normalize_yahoo_ticker(ticker).upper()
        company = self._company_context_by_ticker.get(normalized) or self._company_context_by_ticker.get(ticker)
        if company and company.get("cik"):
            return str(company.get("cik")).zfill(10)

        lookup = self._load_ticker_cik_lookup()
        cik = lookup.get(normalized)
        return str(cik).zfill(10) if cik else None

    def _load_ticker_cik_lookup(self) -> Dict[str, str]:
        if self._ticker_cik_lookup_cache is not None:
            return self._ticker_cik_lookup_cache

        lookup: Dict[str, str] = {}
        mapping_path = self.config.get("data_paths", {}).get("cik_ticker_mapping")
        if mapping_path and os.path.exists(mapping_path):
            try:
                mapping_df = pd.read_csv(mapping_path, dtype={"ticker": str, "cik": str})
                for _, row in mapping_df.iterrows():
                    ticker = self._normalize_yahoo_ticker(row.get("ticker", "")).upper()
                    cik = row.get("cik")
                    if ticker and pd.notna(cik):
                        lookup[ticker] = str(cik).zfill(10)
            except Exception as exc:
                logger.warning(f"Could not load CIK ticker mapping {mapping_path}: {exc}")

        self._ticker_cik_lookup_cache = lookup
        return lookup

    def _fetch_sec_company_metadata_by_cik(self, cik: str, ticker: str = "") -> Dict[str, Any]:
        cik_padded = str(cik).zfill(10)
        cache_file = os.path.join(self.sec_metadata_dir, f"CIK{cik_padded}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    cached = json.load(f)
                return self._normalize_sec_company_metadata(cached, ticker=ticker)
            except Exception as exc:
                logger.warning(f"Could not read SEC metadata cache {cache_file}: {exc}")

        user_agent = self.config.get("sec_api", {}).get("user_agent")
        if not user_agent:
            return {}

        url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
        try:
            response = requests.get(url, headers={"User-Agent": user_agent}, timeout=15)
            response.raise_for_status()
            payload = response.json()
            with open(cache_file, "w") as f:
                json.dump(payload, f, indent=2)
            return self._normalize_sec_company_metadata(payload, ticker=ticker)
        except Exception as exc:
            logger.warning(f"Failed to fetch SEC company metadata for {ticker or cik_padded}: {exc}")
            return {}

    @staticmethod
    def _normalize_sec_company_metadata(payload: Dict[str, Any], ticker: str = "") -> Dict[str, Any]:
        if not payload:
            return {}
        data: Dict[str, Any] = {}
        if ticker:
            data["ticker"] = ticker
        for source, target in [
            ("sic", "sic"),
            ("sicDescription", "sicDescription"),
            ("entityType", "entity_type"),
            ("category", "filer_category"),
        ]:
            value = payload.get(source)
            if value not in (None, ""):
                data[target] = value
        if "sicDescription" in data:
            data["industry_group"] = data["sicDescription"]
            data["industry_data_source"] = "sec_submissions"
        return data

    @staticmethod
    def _is_yfinance_rate_limit_error(exc: Exception) -> bool:
        message = str(exc).lower()
        error_name = exc.__class__.__name__.lower()
        return "ratelimit" in error_name or "rate limited" in message or "too many requests" in message

    def _safe_fast_info_get(self, fast_info: Any, key: str) -> Optional[float]:
        try:
            if hasattr(fast_info, "get"):
                return fast_info.get(key)
            return fast_info[key]
        except Exception as exc:
            if self._is_yfinance_rate_limit_error(exc):
                self._mark_yfinance_rate_limited("fast_info")
            return None

    def _mark_yfinance_rate_limited(self, source: str) -> None:
        self._yfinance_rate_limited = True
        if not self._yfinance_rate_limit_warning_logged:
            logger.warning(
                f"Yahoo Finance {source} endpoint is rate-limited; stopping yfinance calls for this enrichment run. "
                "Continuing with cached data and SEC company metadata."
            )
            self._yfinance_rate_limit_warning_logged = True

    def _save_market_data_file(self, ticker: str, data: Dict[str, Any]) -> None:
        safe_ticker = ticker.replace("/", "-")
        output_file = os.path.join(self.market_data_dir, f"{safe_ticker}_market.json")
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def _load_market_data_files(self, market_data_dir: str) -> Dict[str, Dict]:
        """
        Load market data files from directory
        
        Args:
            market_data_dir: Directory containing market data files
            
        Returns:
            Dictionary mapping tickers to market data
        """
        market_data = {}
        
        # Get all market data files
        market_files = os.listdir(market_data_dir)
        market_files = [f for f in market_files if f.endswith('_market.json')]
        
        for file_name in market_files:
            try:
                file_path = os.path.join(market_data_dir, file_name)
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                ticker = self._normalize_yahoo_ticker(data.get("ticker"))
                if ticker:
                    market_data[ticker] = data
                    
            except Exception as e:
                logger.warning(f"Error loading market data file {file_name}: {e}")
        
        logger.info(f"Loaded market data for {len(market_data)} companies")
        return market_data

    def enrich_company_data(self, companies_df, max_companies=100):
        """
        Add market data to company financial data
        
        Args:
            companies_df: DataFrame with company financial metrics
            max_companies: Maximum number of companies to process
        
        Returns:
            DataFrame with added market data
        """
        # Filter to companies with tickers
        df = companies_df.copy()
        has_ticker = df['ticker'].notna() & (df['ticker'] != '')
        df_with_tickers = df[has_ticker].copy()
        
        if len(df_with_tickers) > max_companies:
            logger.warning(f"Limiting market data enrichment to {max_companies} companies")
            df_with_tickers = df_with_tickers.head(max_companies)
        
        # Load market data from files
        market_data_dir = os.path.join(self.financial_data_dir, "market_data")
        market_data_dict = self._load_market_data_files(market_data_dir)
        
        if market_data_dict:
            # Convert market data to DataFrame
            market_data_df = pd.DataFrame.from_dict(market_data_dict, orient='index')
            
            # Merge with company data if market data exists
            if not market_data_df.empty:
                df_with_tickers = df_with_tickers.set_index('ticker')
                
                # Add market data columns
                for col in ['market_cap', 'book_value', 'ttm_revenue', 'ttm_net_income', 'price_to_sales']:
                    if col in market_data_df.columns:
                        df_with_tickers[col] = market_data_df[col]
                
                df_with_tickers = df_with_tickers.reset_index()
        
        # For companies without market data, estimate market cap from financial data
        missing_market_cap = df_with_tickers['market_cap'].isna() | (df_with_tickers['market_cap'] == 0)
        if 'equity' in df_with_tickers.columns:
            df_with_tickers.loc[missing_market_cap, 'market_cap'] = df_with_tickers.loc[missing_market_cap, 'equity'] * 1.5
            df_with_tickers.loc[missing_market_cap, 'market_cap_source'] = 'estimated_from_equity'
        
        # Combine enriched data with original data
        result = pd.merge(
            df, df_with_tickers, 
            how='left', 
            on=df.columns.tolist(),
            suffixes=('', '_y')
        )
        
        # Drop duplicate columns
        result = result.loc[:, ~result.columns.str.endswith('_y')]
        
        return result

def enrich_market_data(config, use_external_api: bool = False):
    """
    Standalone function to enrich company data with market information.
    
    Args:
        config: Application configuration
        use_external_api: Whether to use external API for market data (ignored, using SEC data only)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        enricher = MarketDataEnricher(config)
        company_limit = config.get("download_settings", {}).get("company_limit", 100)
        print("[enrich] Starting market data enrichment", flush=True)
        
        # SEC 데이터만 사용
        enriched_companies = enricher.enrich_companies_with_market_data(company_limit)
        
        sec_client = None
        needs_sec_client = (
            config.get("institutional_data", {}).get("enabled", False)
            and bool(config.get("institutional_data", {}).get("manager_ciks"))
        ) or (
            config.get("insider_data", {}).get("enabled", False)
            and config.get("insider_data", {}).get("fetch_live", False)
        )
        if needs_sec_client:
            user_agent = config.get("sec_api", {}).get("user_agent")
            rate_limit = config.get("sec_api", {}).get("rate_limit_delay", 0.1)
            sec_client = SECClient(user_agent=user_agent, rate_limit_delay=rate_limit)

        if enriched_companies:
            enrichment_pipeline = _build_optional_enrichment_pipeline(
                config,
                sec_client=sec_client,
            )
            enriched_companies = enrichment_pipeline.enrich(enriched_companies)

        # Replace original file with enriched file
        if enriched_companies:
            processed_dir = config.get("data_paths", {}).get("processed_data_dir", "data/processed")
            companies_list_file = os.path.join(processed_dir, "companies_list.json")
            enriched_file = os.path.join(processed_dir, "companies_list_enriched.json")
            with open(enriched_file, 'w') as f:
                json.dump(enriched_companies, f, indent=2)
            
            # Back up original file
            backup_file = os.path.join(processed_dir, "companies_list_backup.json")
            if os.path.exists(companies_list_file):
                import shutil
                shutil.copy2(companies_list_file, backup_file)
                logger.info(f"Backed up original companies list to {backup_file}")
                
            # Replace with enriched file if it exists
            if os.path.exists(enriched_file):
                with open(enriched_file, 'r') as f:
                    enriched_data = json.load(f)
                    
                with open(companies_list_file, 'w') as f:
                    json.dump(enriched_data, f, indent=2)
                    
                logger.info(f"Updated companies list file with enriched data")
                print("[enrich] Updated companies_list.json with enriched data", flush=True)
                
        print("[enrich] Done", flush=True)
        return True
    except Exception as e:
        logger.error(f"Error during market data enrichment: {e}")
        import traceback
        traceback.print_exc()
        return False

def enrich_leadership_data(config):
    """Run only price-based leadership enrichment."""
    try:
        print("[leadership] Starting price/RS/volume enrichment", flush=True)
        enricher = MarketDataEnricher(config)
        enricher.enrich_companies_with_leadership_data()
        print("[leadership] Done", flush=True)
        return True
    except Exception as e:
        logger.error(f"Error during leadership enrichment: {e}")
        import traceback
        traceback.print_exc()
        return False
