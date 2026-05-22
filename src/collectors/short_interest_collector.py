"""Free FINRA short-interest enrichment helpers.

FINRA publishes bimonthly equity short-interest data for exchange-listed and
OTC securities. This module can read locally downloaded FINRA CSV/JSON files
and can optionally query the public FINRA data API for configured tickers.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import pandas as pd
import requests

logger = logging.getLogger(__name__)

DEFAULT_FINRA_SHORT_INTEREST_API_URL = "https://api.finra.org/data/group/otcMarket/name/EquityShortInterest"

TICKER_FIELDS = [
    "issueSymbolIdentifier",
    "symbolCode",
    "symbol",
    "ticker",
    "issueSymbol",
]
CURRENT_SHORT_FIELDS = [
    "currentShortShareNumber",
    "currentShortPositionQuantity",
    "currentShortPosition",
    "shortInterest",
    "shortInterestShares",
    "short_interest",
    "sharesShort",
]
PREVIOUS_SHORT_FIELDS = [
    "previousShortShareNumber",
    "previousShortPositionQuantity",
    "previousShortPosition",
    "previousShortInterest",
    "previous_short_interest",
    "sharesShortPriorMonth",
]
CHANGE_COUNT_FIELDS = [
    "percentageChangefromPreviousShort",
    "changePreviousNumber",
    "shortInterestChange",
    "short_interest_change",
    "change",
]
CHANGE_PERCENT_FIELDS = [
    "changePercent",
    "percentChangeFromPrevious",
    "shortInterestChangePct",
    "short_interest_change_pct",
]
AVERAGE_VOLUME_FIELDS = [
    "averageShortShareNumber",
    "averageDailyVolumeQuantity",
    "averageDailyVolume",
    "averageDailyShareVolume",
    "avgDailyVolume",
]
DAYS_TO_COVER_FIELDS = [
    "daysToCoverNumber",
    "daysToCoverQuantity",
    "daysToCover",
    "shortRatio",
]
SETTLEMENT_DATE_FIELDS = [
    "settlementDate",
    "settlement_date",
    "asOfDate",
    "reportDate",
    "date",
]
UPDATE_DATE_FIELDS = ["updateDatetime", "updateDate", "lastUpdateDate"]
FLOAT_SHARE_FIELDS = [
    "shares_float",
    "float_shares",
    "free_float_shares",
    "public_float_shares",
    "public_float_shares_estimate",
]


def normalize_ticker(value: Any) -> str:
    """Normalize symbols to FINRA's compact uppercase reporting form."""
    if value is None:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def _case_insensitive_value(row: Mapping[str, Any], fields: Sequence[str]) -> Any:
    lower_to_key = {str(key).lower(): key for key in row.keys()}
    for field in fields:
        key = lower_to_key.get(field.lower())
        if key is not None:
            return row.get(key)
    return None


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.upper() in {"N/A", "NA", "NULL", "NONE", "-"}:
            return None
        result = float(text.replace(",", "").replace("%", ""))
        if pd.notna(result):
            return result
    except (TypeError, ValueError):
        return None
    return None


def _to_int(value: Any) -> Optional[int]:
    number = _to_float(value)
    return int(round(number)) if number is not None else None


def _to_date_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{8}", text):
        parsed = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    else:
        parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return text
    return parsed.date().isoformat()


def _ratio_from_percent_value(value: Any) -> Optional[float]:
    percent = _to_float(value)
    if percent is None:
        return None
    return percent / 100 if abs(percent) > 1 else percent


def _extract_rows_from_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ["data", "results", "rows"]:
            rows = payload.get(key)
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, Mapping)]
        return [dict(payload)]
    return []


def parse_short_interest_rows(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize FINRA short-interest rows into screener fields."""
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        ticker_raw = _case_insensitive_value(row, TICKER_FIELDS)
        ticker = normalize_ticker(ticker_raw)
        if not ticker:
            continue

        current = _to_float(_case_insensitive_value(row, CURRENT_SHORT_FIELDS))
        previous = _to_float(_case_insensitive_value(row, PREVIOUS_SHORT_FIELDS))
        if current is None:
            continue

        if previous is not None:
            change = current - previous
            change_pct = change / previous if previous > 0 else None
        else:
            change = _to_float(_case_insensitive_value(row, CHANGE_COUNT_FIELDS))
            change_pct = None

        if change_pct is None:
            change_pct = _ratio_from_percent_value(_case_insensitive_value(row, CHANGE_PERCENT_FIELDS))

        average_volume = _to_float(_case_insensitive_value(row, AVERAGE_VOLUME_FIELDS))
        days_to_cover = _to_float(_case_insensitive_value(row, DAYS_TO_COVER_FIELDS))
        if days_to_cover is None and average_volume and average_volume > 0:
            days_to_cover = current / average_volume

        normalized.append(
            {
                "ticker": ticker,
                "short_interest_raw_ticker": str(ticker_raw).strip() if ticker_raw is not None else ticker,
                "short_interest": int(round(current)),
                "short_interest_previous": int(round(previous)) if previous is not None else None,
                "short_interest_change": int(round(change)) if change is not None else None,
                "short_interest_change_pct": change_pct,
                "short_average_daily_volume": int(round(average_volume)) if average_volume is not None else None,
                "short_days_to_cover": float(days_to_cover) if days_to_cover is not None else None,
                "short_interest_settlement_date": _to_date_string(
                    _case_insensitive_value(row, SETTLEMENT_DATE_FIELDS)
                ),
                "short_interest_report_date": _to_date_string(_case_insensitive_value(row, UPDATE_DATE_FIELDS)),
                "short_interest_source": "finra_equity_short_interest",
            }
        )
    return normalized


def _latest_short_interest_by_ticker(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    parsed = parse_short_interest_rows(rows)
    if not parsed:
        return {}

    df = pd.DataFrame(parsed)
    df["_date"] = pd.to_datetime(df["short_interest_settlement_date"], errors="coerce")
    df = df.sort_values(["ticker", "_date"], na_position="first")
    latest = df.groupby("ticker", as_index=False).tail(1).drop(columns=["_date"])
    return {row["ticker"]: row for row in latest.to_dict(orient="records")}


def _positive_float(value: Any) -> Optional[float]:
    number = _to_float(value)
    if number is None or number <= 0:
        return None
    return number


def apply_short_interest(
    companies: Sequence[Mapping[str, Any]],
    short_interest_by_ticker: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Apply latest short-interest metrics to company dictionaries."""
    output = [dict(company) for company in companies]
    if not short_interest_by_ticker:
        return output

    for company in output:
        ticker = normalize_ticker(company.get("ticker"))
        row = short_interest_by_ticker.get(ticker)
        if row is None:
            continue

        for field, value in row.items():
            if field == "ticker" or value is None:
                continue
            if hasattr(value, "item"):
                value = value.item()
            company[field] = value

        short_interest = _positive_float(company.get("short_interest"))
        float_shares = next(
            (
                shares
                for shares in (_positive_float(company.get(field)) for field in FLOAT_SHARE_FIELDS)
                if shares is not None
            ),
            None,
        )
        shares_outstanding = _positive_float(company.get("shares_outstanding"))
        if short_interest is not None and float_shares is not None:
            company["short_percent_float"] = short_interest / float_shares
        if short_interest is not None and shares_outstanding is not None:
            company["short_percent_shares_outstanding"] = short_interest / shares_outstanding
    return output


class ShortInterestCollector:
    """Load local FINRA files or query FINRA short-interest data for tickers."""

    def __init__(
        self,
        *,
        raw_dir: str = "data/raw/short_interest",
        api_url: str = DEFAULT_FINRA_SHORT_INTEREST_API_URL,
        symbol_field: str = "issueSymbolIdentifier",
        limit_per_ticker: int = 20,
        timeout: int = 30,
        session: Optional[Any] = None,
    ):
        self.raw_dir = Path(raw_dir)
        self.api_url = api_url
        self.symbol_field = symbol_field
        self.limit_per_ticker = max(1, int(limit_per_ticker or 20))
        self.timeout = timeout
        self.session = session or requests.Session()
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def load_local_rows(self) -> List[Dict[str, Any]]:
        """Load short-interest rows from local CSV/JSON/TXT/ZIP cache files."""
        rows: List[Dict[str, Any]] = []
        if not self.raw_dir.exists():
            return rows
        for path in sorted(self.raw_dir.glob("*")):
            if path.is_dir():
                continue
            rows.extend(self._load_path(path))
        return rows

    def _load_path(self, path: Path) -> List[Dict[str, Any]]:
        suffix = path.suffix.lower()
        try:
            if suffix in {".json", ".jsonl"}:
                return self._load_json_text(path.read_text(encoding="utf-8"))
            if suffix in {".csv", ".txt"}:
                return pd.read_csv(path, dtype=str, sep=None, engine="python").to_dict(orient="records")
            if suffix == ".zip":
                return self._load_zip(path)
        except Exception as exc:
            logger.warning("Could not load FINRA short-interest file %s: %s", path, exc)
        return []

    def _load_zip(self, path: Path) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                lower = name.lower()
                if lower.endswith("/"):
                    continue
                with archive.open(name) as handle:
                    text = io.TextIOWrapper(handle, encoding="utf-8").read()
                if lower.endswith((".json", ".jsonl")):
                    rows.extend(self._load_json_text(text))
                elif lower.endswith((".csv", ".txt")):
                    rows.extend(pd.read_csv(io.StringIO(text), dtype=str, sep=None, engine="python").to_dict(orient="records"))
        return rows

    @staticmethod
    def _load_json_text(text: str) -> List[Dict[str, Any]]:
        if not text.strip():
            return []
        try:
            return _extract_rows_from_payload(json.loads(text))
        except json.JSONDecodeError:
            return [json.loads(line) for line in text.splitlines() if line.strip()]

    def fetch_for_tickers(self, tickers: Iterable[Any]) -> List[Dict[str, Any]]:
        """Fetch short-interest rows from FINRA for the supplied tickers."""
        rows: List[Dict[str, Any]] = []
        unique_tickers = [ticker for ticker in dict.fromkeys(normalize_ticker(t) for t in tickers) if ticker]
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        for ticker in unique_tickers:
            payload = {
                "compareFilters": [
                    {
                        "compareType": "EQUAL",
                        "fieldName": self.symbol_field,
                        "fieldValue": ticker,
                    }
                ],
                "limit": self.limit_per_ticker,
            }
            try:
                response = self.session.post(self.api_url, json=payload, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                rows.extend(self._rows_from_response(response))
            except Exception as exc:  # pragma: no cover - defensive logging around live API calls
                logger.warning("Failed to fetch FINRA short interest for %s: %s", ticker, exc)
        return rows

    @staticmethod
    def _rows_from_response(response: Any) -> List[Dict[str, Any]]:
        content_type = str(getattr(response, "headers", {}).get("Content-Type", "")).lower()
        if "json" in content_type:
            return _extract_rows_from_payload(response.json())
        text = response.text
        try:
            return _extract_rows_from_payload(json.loads(text))
        except Exception:
            return pd.read_csv(io.StringIO(text), dtype=str, sep=None, engine="python").to_dict(orient="records")


def enrich_companies_with_short_interest_data(
    companies: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    *,
    session: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Enrich company dictionaries with free FINRA short-interest data."""
    short_config = config.get("short_interest_data", {}) if isinstance(config, Mapping) else {}
    if not short_config.get("enabled", False):
        return [dict(company) for company in companies]

    data_paths = config.get("data_paths", {}) if isinstance(config, Mapping) else {}
    raw_dir = short_config.get(
        "raw_short_interest_dir",
        os.path.join(data_paths.get("raw_data_dir", "data/raw"), "short_interest"),
    )
    collector = ShortInterestCollector(
        raw_dir=raw_dir,
        api_url=short_config.get("finra_api_url", DEFAULT_FINRA_SHORT_INTEREST_API_URL),
        symbol_field=short_config.get("symbol_field", "issueSymbolIdentifier"),
        limit_per_ticker=short_config.get("limit_per_ticker", 20),
        timeout=short_config.get("timeout_seconds", 30),
        session=session,
    )

    rows = collector.load_local_rows()
    if short_config.get("fetch_live", False):
        rows.extend(collector.fetch_for_tickers(company.get("ticker") for company in companies))

    latest_by_ticker = _latest_short_interest_by_ticker(rows)
    return apply_short_interest(companies, latest_by_ticker)
