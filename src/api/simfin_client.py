"""SimFin Data API client for fundamental fallback metrics.

Docs: https://simfin.readme.io/reference/getting-started-1
The API key is passed as the ``Authorization`` header value.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

from src.utils.logger import setup_logger

logger = setup_logger("simfin_client")


class SimFinClient:
    """Small client for SimFin compact financial statements."""

    BASE_URL = "https://backend.simfin.com/api/v3"
    STATEMENTS_ENDPOINT = "companies/statements/compact"
    METRIC_FIELDS = [
        "quarterly_eps_growth",
        "annual_eps_cagr",
        "revenue_growth",
        "profit_margin",
        "roe",
        "debt_to_equity",
    ]

    def __init__(self, config: Dict[str, Any]):
        load_dotenv()
        self.config = config
        self.api_key = self._resolve_api_key(config)
        fundamental_config = config.get("fundamental_data", {})
        raw_dir = config.get("data_paths", {}).get("raw_data_dir", "data/raw")
        self.cache_dir = Path(fundamental_config.get("simfin_cache_dir", Path(raw_dir) / "simfin_fundamentals"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_max_age_days = fundamental_config.get("cache_max_age_days", 30)
        self.rate_limit_delay = fundamental_config.get("rate_limit_delay", 0.25)
        self.last_request_time = 0.0

    @staticmethod
    def _resolve_api_key(config: Dict[str, Any]) -> str:
        return str(
            config.get("optional_api_keys", {}).get("simfin_api_key")
            or os.getenv("SIMFIN_API_KEY")
            or os.getenv("simfin_API_key")
            or os.getenv("SIMFIN_API_key")
            or ""
        ).strip()

    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": self.api_key}

    def _request_params(self, ticker: str) -> Dict[str, str]:
        cfg = self.config.get("fundamental_data", {})
        return {
            "ticker": ticker.upper(),
            "statements": cfg.get("simfin_statements", "pl,bs,derived"),
            "period": cfg.get("simfin_periods", "q1,q2,q3,q4,fy"),
            "ttm": str(cfg.get("simfin_ttm", False)).lower(),
            "asreported": str(cfg.get("simfin_asreported", False)).lower(),
        }

    def _respect_rate_limit(self) -> None:
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def _cache_file(self, ticker: str) -> Path:
        safe = ticker.upper().replace("/", "-").replace(".", "-")
        return self.cache_dir / f"{safe}_statements.json"

    def _load_cached_payload(self, ticker: str) -> Any | None:
        path = self._cache_file(ticker)
        if not path.exists():
            return None
        if self.cache_max_age_days is not None:
            age_days = (time.time() - path.stat().st_mtime) / 86400
            if age_days > self.cache_max_age_days:
                return None
        try:
            with path.open("r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Could not read SimFin cache for %s: %s", ticker, e)
            return None

    def _save_cached_payload(self, ticker: str, payload: Any) -> None:
        try:
            with self._cache_file(ticker).open("w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.warning("Could not write SimFin cache for %s: %s", ticker, e)

    def fetch_statements(self, ticker: str) -> Any:
        """Fetch compact statements for one ticker, using local cache."""
        cached = self._load_cached_payload(ticker)
        if cached is not None:
            return cached
        if not self.has_api_key():
            logger.warning("SimFin API key is missing; skipping %s", ticker)
            return None

        self._respect_rate_limit()
        url = f"{self.BASE_URL}/{self.STATEMENTS_ENDPOINT}"
        response = requests.get(
            url,
            params=self._request_params(ticker),
            headers=self._headers(),
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        self._save_cached_payload(ticker, payload)
        return payload

    def get_fundamental_metrics(self, ticker: str) -> Dict[str, Any]:
        """Return CANSLIM-compatible metrics for one ticker from SimFin."""
        payload = self.fetch_statements(ticker)
        if payload is None:
            return {}
        return self.metrics_from_payload(payload)

    def metrics_from_payload(self, payload: Any) -> Dict[str, Any]:
        df = self._payload_to_dataframe(payload)
        if df.empty:
            return {}
        return self._metrics_from_dataframe(df)

    def _payload_to_dataframe(self, payload: Any) -> pd.DataFrame:
        records = self._extract_company_records(payload)
        frames: list[pd.DataFrame] = []
        for record in records:
            if not record or record.get("found") is False:
                continue
            if isinstance(record.get("statements"), list):
                frame = self._flatten_v3_company_record(record)
                if not frame.empty:
                    frames.append(frame)
                continue
            columns = record.get("columns") or record.get("cols") or []
            data = record.get("data") or []
            if columns and data:
                frame = pd.DataFrame(data, columns=columns)
                if record.get("ticker") and "Ticker" not in frame.columns:
                    frame["Ticker"] = record.get("ticker")
                frames.append(frame)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def _flatten_v3_company_record(self, record: Dict[str, Any]) -> pd.DataFrame:
        merged: Optional[pd.DataFrame] = None
        key_columns = ["Fiscal Period", "Fiscal Year", "Report Date"]
        for statement in record.get("statements", []):
            columns = statement.get("columns") or []
            data = statement.get("data") or []
            if not columns or not data:
                continue
            frame = pd.DataFrame(data, columns=columns)
            for key in key_columns:
                if key not in frame.columns:
                    frame[key] = None
            value_columns = [column for column in frame.columns if column not in key_columns]
            renamed = {
                column: column
                for column in value_columns
            }
            # Keep first occurrence of shared high-value fields; prefix only exact duplicates later.
            frame = frame[key_columns + value_columns].rename(columns=renamed)
            if merged is None:
                merged = frame
            else:
                duplicate_values = [column for column in value_columns if column in merged.columns]
                frame = frame.rename(
                    columns={column: f"{statement.get('statement', 'stmt')}_{column}" for column in duplicate_values}
                )
                merged = merged.merge(frame, on=key_columns, how="outer")
        if merged is None:
            return pd.DataFrame()
        if record.get("ticker") and "Ticker" not in merged.columns:
            merged["Ticker"] = record.get("ticker")
        return merged

    def _extract_company_records(self, payload: Any) -> list[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
            if payload.get("columns") and payload.get("data"):
                return [payload]
        return []

    def _metrics_from_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        work = df.copy()
        work.columns = [str(column).strip() for column in work.columns]
        column_map = {self._norm_col(column): column for column in work.columns}

        period_col = self._find_column(column_map, ["fiscal_period", "period", "fiscalperiod"])
        year_col = self._find_column(column_map, ["fiscal_year", "fyear", "fiscalyear"])
        date_col = self._find_column(column_map, ["report_date", "publish_date", "date"])
        ticker_col = self._find_column(column_map, ["ticker"])

        if period_col:
            work["_period"] = work[period_col].astype(str).str.lower().str.replace(" ", "", regex=False)
        else:
            work["_period"] = ""
        if year_col:
            work["_year"] = pd.to_numeric(work[year_col], errors="coerce")
        else:
            work["_year"] = pd.NA
        if date_col:
            work["_date"] = pd.to_datetime(work[date_col], errors="coerce")
        else:
            work["_date"] = pd.NaT

        metrics: Dict[str, Any] = {"financial_data_source": "simfin"}
        if ticker_col and work[ticker_col].notna().any():
            metrics["ticker"] = str(work[ticker_col].dropna().iloc[0]).upper()

        eps_col = self._find_column(column_map, ["eps_diluted", "diluted_eps", "earnings_per_share_diluted", "eps_basic", "earnings_per_share_basic", "eps"])
        revenue_col = self._find_column(column_map, ["revenue", "sales"])
        income_col = self._find_column(column_map, ["net_income", "net_income_loss", "profit_loss"])
        debt_col = self._find_column(column_map, ["total_debt", "debt"])
        equity_col = self._find_column(column_map, ["total_equity", "equity", "shareholders_equity"])
        roe_col = self._find_column(column_map, ["roe", "return_on_equity"])
        de_col = self._find_column(column_map, ["debt_to_equity", "debt_equity"])

        quarterly = self._sort_rows(work[work["_period"].isin(["q1", "q2", "q3", "q4"])])
        annual = self._sort_rows(work[work["_period"].isin(["fy", "ttm"])])

        eps_growth = self._same_period_growth(quarterly, eps_col)
        if eps_growth is not None:
            metrics["quarterly_eps_growth"] = eps_growth
        revenue_growth = self._same_period_growth(quarterly, revenue_col)
        if revenue_growth is not None:
            metrics["revenue_growth"] = revenue_growth
        annual_cagr = self._annual_cagr(annual, eps_col)
        if annual_cagr is not None:
            metrics["annual_eps_cagr"] = annual_cagr

        latest = self._latest_row(quarterly)
        if latest is None:
            latest = self._latest_row(annual)
        annual_latest = self._latest_row(annual)
        balance_row = annual_latest if annual_latest is not None else latest
        if balance_row is not None and self._value(balance_row, equity_col) is None and latest is not None:
            balance_row = latest
        if latest is not None:
            revenue = self._value(latest, revenue_col)
            income = self._value(latest, income_col)
            if revenue and revenue > 0 and income is not None:
                metrics["profit_margin"] = income / revenue
        if balance_row is not None:
            income_for_roe = self._value(balance_row, income_col)
            equity = self._value(balance_row, equity_col)
            debt = self._value(balance_row, debt_col)
            roe = self._value(balance_row, roe_col)
            if roe is not None:
                metrics["roe"] = self._normalize_ratio(roe)
            elif equity and equity > 0 and income_for_roe is not None:
                metrics["roe"] = income_for_roe / equity
            debt_to_equity = self._value(balance_row, de_col)
            if debt_to_equity is not None:
                metrics["debt_to_equity"] = self._normalize_ratio(debt_to_equity)
            elif equity and equity > 0 and debt is not None:
                metrics["debt_to_equity"] = debt / equity

        return {key: value for key, value in metrics.items() if value is not None and pd.notna(value)}

    @staticmethod
    def _norm_col(column: str) -> str:
        normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(column)).strip("_")
        while "__" in normalized:
            normalized = normalized.replace("__", "_")
        return normalized

    def _find_column(self, column_map: Dict[str, str], candidates: Iterable[str]) -> Optional[str]:
        normalized = [self._norm_col(candidate) for candidate in candidates]
        for candidate in normalized:
            if candidate in column_map:
                return column_map[candidate]
        for candidate in normalized:
            for norm, original in column_map.items():
                if candidate in norm:
                    return original
        return None

    @staticmethod
    def _sort_rows(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        return df.sort_values(["_year", "_date"], ascending=[False, False], na_position="last")

    @staticmethod
    def _latest_row(df: pd.DataFrame) -> Optional[pd.Series]:
        if df.empty:
            return None
        return df.iloc[0]

    @staticmethod
    def _value(row: pd.Series, column: Optional[str]) -> Optional[float]:
        if not column or column not in row:
            return None
        value = pd.to_numeric(row[column], errors="coerce")
        if pd.isna(value):
            return None
        return float(value)

    def _same_period_growth(self, df: pd.DataFrame, value_col: Optional[str]) -> Optional[float]:
        if df.empty or not value_col:
            return None
        latest = self._latest_row(df)
        if latest is None:
            return None
        period = latest.get("_period")
        latest_year = latest.get("_year")
        latest_value = self._value(latest, value_col)
        if pd.isna(latest_year) or latest_value is None:
            return None
        prior = df[(df["_period"] == period) & (df["_year"] == latest_year - 1)]
        prior_row = self._latest_row(prior)
        prior_value = self._value(prior_row, value_col) if prior_row is not None else None
        if prior_value is None or prior_value <= 0:
            return None
        return latest_value / prior_value - 1

    def _annual_cagr(self, df: pd.DataFrame, value_col: Optional[str]) -> Optional[float]:
        if df.empty or not value_col:
            return None
        rows = df.dropna(subset=["_year"]).copy()
        rows[value_col] = pd.to_numeric(rows[value_col], errors="coerce")
        rows = rows[rows[value_col] > 0].sort_values("_year", ascending=False)
        if len(rows) < 2:
            return None
        latest = rows.iloc[0]
        # Prefer a 2-3 year lookback; use the oldest positive row available.
        base = rows.iloc[min(len(rows) - 1, 2)]
        years = int(latest["_year"] - base["_year"])
        if years <= 0:
            return None
        return float(latest[value_col] / base[value_col]) ** (1 / years) - 1

    @staticmethod
    def _normalize_ratio(value: float) -> float:
        # SimFin ratio columns may be decimal ratios or percentage values.
        if abs(value) > 5:
            return value / 100.0
        return value
