"""
Stock Screener Module

This module provides functionality for screening stocks based on financial and
basic market criteria.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from src.utils.logger import setup_logger

logger = setup_logger("stock_screener")


_COLUMN_ALIASES = {
    "quarterly_eps_growth": ("quarterly_eps_growth", "eps_qtr_growth"),
    "annual_eps_cagr": ("annual_eps_cagr", "eps_3yr_cagr"),
    "revenue_growth": ("revenue_growth", "revenue_qtr_growth"),
    "profit_margin": ("profit_margin",),
    "roe": ("roe",),
    "debt_to_equity": ("debt_to_equity",),
    "market_cap": ("market_cap",),
    "sp500_outperformance": ("sp500_outperformance", "market_outperformance"),
}


class StockScreener:
    """Screens stocks based on configured criteria."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.criteria = config.get("screening_criteria", {})
        self.metrics_df = pd.DataFrame()
        self.companies_df = pd.DataFrame()
        self._load_data()

    def _processed_path(self, filename: str) -> str:
        processed_dir = self.config.get("data_paths", {}).get(
            "processed_data_dir", "data/processed"
        )
        return os.path.join(processed_dir, filename)

    def _load_data(self) -> None:
        """Load persisted metrics and company index when available."""
        metrics_file = self._processed_path("financial_metrics.parquet")
        companies_file = self._processed_path("companies_index.parquet")

        if os.path.exists(metrics_file):
            self.metrics_df = pd.read_parquet(metrics_file)
        if os.path.exists(companies_file):
            self.companies_df = pd.read_parquet(companies_file)

        if not self.metrics_df.empty and not self.companies_df.empty:
            company_columns = [
                column
                for column in ["ticker", "market_cap", "exchange", "name", "sic", "category"]
                if column in self.companies_df.columns
            ]
            if "ticker" in company_columns:
                company_lookup = self.companies_df[company_columns].drop_duplicates("ticker")
                merge_columns = [c for c in company_lookup.columns if c != "ticker"]
                self.metrics_df = self.metrics_df.merge(
                    company_lookup[["ticker", *merge_columns]],
                    on="ticker",
                    how="left",
                    suffixes=("", "_company"),
                )
                for column in merge_columns:
                    company_column = f"{column}_company"
                    if company_column in self.metrics_df.columns:
                        if column in self.metrics_df.columns:
                            self.metrics_df[column] = self.metrics_df[column].fillna(
                                self.metrics_df[company_column]
                            )
                            self.metrics_df = self.metrics_df.drop(columns=[company_column])
                        else:
                            self.metrics_df = self.metrics_df.rename(
                                columns={company_column: column}
                            )

    @staticmethod
    def _first_existing_column(df: pd.DataFrame, names: Iterable[str]) -> Optional[str]:
        for name in names:
            if name in df.columns:
                return name
        return None

    def _metric_column(self, metric: str, df: pd.DataFrame) -> Optional[str]:
        return self._first_existing_column(df, _COLUMN_ALIASES.get(metric, (metric,)))

    def _apply_min_filter(self, df: pd.DataFrame, metric: str, threshold: Any) -> pd.DataFrame:
        column = self._metric_column(metric, df)
        if column is None or threshold is None:
            return df.copy()
        return df[df[column].ge(threshold).fillna(False)].copy()

    def _apply_max_filter(self, df: pd.DataFrame, metric: str, threshold: Any) -> pd.DataFrame:
        column = self._metric_column(metric, df)
        if column is None or threshold is None:
            return df.copy()
        return df[df[column].le(threshold).fillna(False)].copy()

    def apply_eps_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply quarterly EPS growth threshold."""
        return self._apply_min_filter(
            df, "quarterly_eps_growth", self.criteria.get("quarterly_eps_growth")
        )

    def apply_revenue_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply revenue growth threshold."""
        return self._apply_min_filter(
            df, "revenue_growth", self.criteria.get("revenue_growth")
        )

    def apply_all_filters(self, df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Apply all configured financial and basic market filters."""
        filtered = (self.metrics_df if df is None else df).copy()

        if "has_complete_data" in filtered.columns:
            filtered = filtered[filtered["has_complete_data"].fillna(False)].copy()

        filtered = self.apply_eps_filter(filtered)
        filtered = self._apply_min_filter(
            filtered, "annual_eps_cagr", self.criteria.get("annual_eps_cagr")
        )
        filtered = self.apply_revenue_filter(filtered)
        filtered = self._apply_min_filter(
            filtered, "profit_margin", self.criteria.get("profit_margin")
        )
        filtered = self._apply_min_filter(filtered, "roe", self.criteria.get("roe"))
        filtered = self._apply_max_filter(
            filtered, "debt_to_equity", self.criteria.get("debt_to_equity")
        )
        filtered = self._apply_min_filter(
            filtered, "market_cap", self.criteria.get("min_market_cap")
        )

        if self.criteria.get("outperform_sp500", False):
            outperformance_column = self._metric_column("sp500_outperformance", filtered)
            if outperformance_column:
                filtered = filtered[filtered[outperformance_column].gt(0).fillna(False)].copy()
            else:
                logger.warning("S&P outperformance is required, but comparison data is missing")
                filtered = filtered.iloc[0:0].copy()

        return filtered

    def screen_stocks(self, company_data: pd.DataFrame) -> pd.DataFrame:
        """
        Apply screening criteria to company data.

        Args:
            company_data: DataFrame with company financial and market data

        Returns:
            DataFrame with companies that pass all criteria
        """
        logger.info(f"Screening {len(company_data)} companies")
        filtered_df = self.apply_all_filters(company_data)
        logger.info(
            "Screening complete: %s companies passed out of %s",
            len(filtered_df),
            len(company_data),
        )
        return filtered_df
