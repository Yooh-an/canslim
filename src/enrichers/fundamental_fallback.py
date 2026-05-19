"""Fallback enrichment for missing fundamental metrics."""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from src.api.simfin_client import SimFinClient
from src.utils.logger import setup_logger

logger = setup_logger("fundamental_fallback")

FUNDAMENTAL_FIELDS = [
    "quarterly_eps_growth",
    "annual_eps_cagr",
    "revenue_growth",
    "profit_margin",
    "roe",
    "debt_to_equity",
]


def _row_missing_any_metric(row: pd.Series) -> bool:
    return any(field not in row.index or pd.isna(row.get(field)) for field in FUNDAMENTAL_FIELDS)


def _should_enrich_row(row: pd.Series, only_missing: bool) -> bool:
    ticker = row.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        return False
    return _row_missing_any_metric(row) if only_missing else True


def _simfin_client(config: Dict[str, Any]) -> SimFinClient | None:
    fallback_config = config.get("fundamental_data", {})
    if not fallback_config.get("enabled", False):
        return None
    provider = str(fallback_config.get("provider", "simfin")).lower()
    if provider != "simfin":
        logger.warning("Unsupported fundamental fallback provider: %s", provider)
        return None
    client = SimFinClient(config)
    if not client.has_api_key():
        logger.warning("SimFin fallback enabled but API key is missing")
        return None
    return client


def enrich_company_fundamentals(company: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing fundamental metrics for one company, preserving existing SEC values."""
    output = dict(company)
    row = pd.Series(output)
    if not _should_enrich_row(row, only_missing=True):
        return output
    client = _simfin_client(config)
    if client is None:
        return output
    ticker = str(output.get("ticker") or "").upper()
    try:
        metrics = client.get_fundamental_metrics(ticker)
    except Exception as e:
        logger.warning("SimFin fallback failed for %s: %s", ticker, e)
        return output
    if not metrics:
        return output
    row_enriched = False
    for field in FUNDAMENTAL_FIELDS:
        if field in metrics and (field not in output or pd.isna(output.get(field))):
            output[field] = metrics[field]
            row_enriched = True
    if row_enriched:
        output["financial_data_source"] = metrics.get("financial_data_source", "simfin")
    return output


def enrich_missing_fundamentals(df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    """Fill missing SEC fundamental metrics from configured fallback provider.

    Currently supports ``provider=simfin``. Existing SEC values are preserved unless
    ``only_missing_sec_metrics`` is set to false.
    """
    output = df.copy()
    fallback_config = config.get("fundamental_data", {})
    only_missing = fallback_config.get("only_missing_sec_metrics", True)
    client = _simfin_client(config)
    if client is None:
        return output

    max_companies = fallback_config.get("max_companies")
    enriched_count = 0
    attempted = 0
    for idx, row in output.iterrows():
        if not _should_enrich_row(row, only_missing):
            continue
        if max_companies is not None and attempted >= max_companies:
            break
        ticker = str(row.get("ticker")).upper()
        attempted += 1
        try:
            metrics = client.get_fundamental_metrics(ticker)
        except Exception as e:
            logger.warning("SimFin fallback failed for %s: %s", ticker, e)
            continue
        if not metrics:
            continue

        row_enriched = False
        for field in FUNDAMENTAL_FIELDS:
            if field not in metrics:
                continue
            if only_missing and field in output.columns and pd.notna(output.at[idx, field]):
                continue
            output.at[idx, field] = metrics[field]
            row_enriched = True
        if row_enriched:
            output.at[idx, "financial_data_source"] = metrics.get("financial_data_source", "simfin")
            enriched_count += 1

    logger.info("SimFin fallback enriched %s/%s attempted companies", enriched_count, attempted)
    return output
