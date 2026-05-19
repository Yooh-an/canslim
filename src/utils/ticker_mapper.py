"""
Ticker to CIK mapping utility.

This module maps SEC CIK numbers to stock ticker symbols.  The primary source is
SEC's listed-company master with exchange data.  Older SEC ``include/ticker.txt``
is kept only as a fallback because it can lag newly relisted/spun-off symbols
(e.g. SNDK / Sandisk Corp).
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd
import requests

from src.utils.logger import setup_logger

# Set up logger
logger = setup_logger("ticker_mapper")


class TickerMapper:
    """
    Maps between SEC CIK numbers and stock ticker symbols.

    Source priority:
      1. Local manual overrides
      2. SEC company_tickers_exchange.json
      3. SEC company_tickers.json
      4. Legacy SEC include/ticker.txt fallback
    """

    SEC_TICKER_URL = "https://www.sec.gov/include/ticker.txt"
    SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    SEC_COMPANY_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"

    SOURCE_PRIORITY = {
        "manual_override": 0,
        "company_tickers_exchange": 1,
        "company_tickers": 2,
        "ticker_txt": 3,
    }

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the TickerMapper.

        Args:
            config: Application configuration dictionary
        """
        self.config = config

        data_paths = config.get("data_paths", {})
        self.processed_data_dir = data_paths.get("processed_data_dir", "data/processed")
        self.mapping_file = data_paths.get(
            "cik_ticker_mapping",
            os.path.join(self.processed_data_dir, "cik_ticker_mapping.csv"),
        )
        self.overrides_file = data_paths.get(
            "ticker_overrides_file",
            os.path.join(self.processed_data_dir, "ticker_overrides.csv"),
        )

        Path(os.path.dirname(self.mapping_file) or ".").mkdir(parents=True, exist_ok=True)

        self.cik_to_ticker: Dict[str, str] = {}
        self.cik_to_tickers: Dict[str, List[str]] = {}
        self.cik_to_exchanges: Dict[str, List[str]] = {}
        self.ticker_to_cik: Dict[str, str] = {}
        self.ticker_to_exchange: Dict[str, str] = {}
        self.ticker_to_name: Dict[str, str] = {}

    def download_mapping(self, force: bool = False) -> bool:
        """
        Download or load CIK/ticker mapping.

        Args:
            force: If True, download even if file exists

        Returns:
            True if mapping is available, False otherwise
        """
        if os.path.exists(self.mapping_file) and not force:
            logger.info("Using existing ticker mapping file")
            self._load_mapping()
            return bool(self.ticker_to_cik)

        logger.info("Downloading ticker mapping from SEC")

        mapping_data: List[Dict[str, str]] = []
        for source_name, downloader in (
            ("company_tickers_exchange", self._download_exchange_mapping),
            ("company_tickers", self._download_company_tickers_mapping),
            ("ticker_txt", self._download_legacy_ticker_mapping),
        ):
            try:
                mapping_data = downloader()
                if mapping_data:
                    logger.info("Loaded %s mappings from %s", len(mapping_data), source_name)
                    break
            except Exception as e:
                logger.warning("Could not load ticker mapping from %s: %s", source_name, e)

        overrides = self._load_manual_overrides()
        if overrides:
            logger.info("Loaded %s manual ticker override(s)", len(overrides))
            mapping_data.extend(overrides)

        if not mapping_data:
            logger.error("No ticker mapping data could be loaded")
            return False

        df = self._rows_to_dataframe(mapping_data)
        df.to_csv(self.mapping_file, index=False)

        logger.info("Saved %s ticker mappings to %s", len(df), self.mapping_file)
        self._load_mapping()
        return bool(self.ticker_to_cik)

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        user_agent = self.config.get("sec_api", {}).get("user_agent")
        if user_agent:
            headers["User-Agent"] = user_agent
        return headers

    def _download_exchange_mapping(self) -> List[Dict[str, str]]:
        response = requests.get(self.SEC_COMPANY_TICKERS_EXCHANGE_URL, headers=self._headers())
        response.raise_for_status()
        payload = response.json()
        fields = [str(field).lower() for field in payload.get("fields", [])]
        rows = []
        for values in payload.get("data", []):
            record = dict(zip(fields, values))
            rows.append(
                {
                    "ticker": record.get("ticker", ""),
                    "cik": record.get("cik", ""),
                    "exchange": record.get("exchange", ""),
                    "name": record.get("name", ""),
                    "source": "company_tickers_exchange",
                }
            )
        return rows

    def _download_company_tickers_mapping(self) -> List[Dict[str, str]]:
        response = requests.get(self.SEC_COMPANY_TICKERS_URL, headers=self._headers())
        response.raise_for_status()
        payload = response.json()
        rows = []
        for record in payload.values():
            rows.append(
                {
                    "ticker": record.get("ticker", ""),
                    "cik": record.get("cik_str", ""),
                    "exchange": "",
                    "name": record.get("title", ""),
                    "source": "company_tickers",
                }
            )
        return rows

    def _download_legacy_ticker_mapping(self) -> List[Dict[str, str]]:
        response = requests.get(self.SEC_TICKER_URL, headers=self._headers())
        response.raise_for_status()
        rows = []
        for line in response.text.split("\n"):
            if not line.strip():
                continue
            try:
                ticker, cik_str = line.strip().split("\t")
            except ValueError:
                logger.warning("Skipping malformed line: %s", line)
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "cik": cik_str,
                    "exchange": "",
                    "name": "",
                    "source": "ticker_txt",
                }
            )
        return rows

    def _load_manual_overrides(self) -> List[Dict[str, str]]:
        if not os.path.exists(self.overrides_file):
            return []

        try:
            df = pd.read_csv(self.overrides_file, dtype=str).fillna("")
        except Exception as e:
            logger.warning("Could not read ticker overrides file %s: %s", self.overrides_file, e)
            return []

        rows = []
        for _, record in df.iterrows():
            rows.append(
                {
                    "ticker": record.get("ticker", ""),
                    "cik": record.get("cik", ""),
                    "exchange": record.get("exchange", ""),
                    "name": record.get("name", ""),
                    "source": "manual_override",
                }
            )
        return rows

    def _rows_to_dataframe(self, rows: List[Dict[str, Any]]) -> pd.DataFrame:
        normalized_rows = []
        for row in rows:
            ticker = str(row.get("ticker", "")).strip().upper()
            cik = str(row.get("cik", "")).strip()
            if not ticker or not cik:
                continue
            normalized_rows.append(
                {
                    "ticker": ticker,
                    "cik": cik.zfill(10),
                    "exchange": str(row.get("exchange", "") or "").strip(),
                    "name": str(row.get("name", "") or "").strip(),
                    "source": str(row.get("source", "") or "unknown").strip(),
                }
            )

        if not normalized_rows:
            return pd.DataFrame(columns=["ticker", "cik", "exchange", "name", "source"])

        df = pd.DataFrame(normalized_rows)
        df["_priority"] = df["source"].map(self.SOURCE_PRIORITY).fillna(99).astype(int)
        df = df.sort_values(["_priority", "ticker", "cik"])
        df = df.drop_duplicates(subset=["ticker", "cik"], keep="first")
        return df.drop(columns=["_priority"]).reset_index(drop=True)

    def _load_mapping(self) -> None:
        """Load the mapping from file into memory."""
        try:
            if not os.path.exists(self.mapping_file):
                logger.warning("Mapping file %s does not exist", self.mapping_file)
                return

            df = pd.read_csv(self.mapping_file, dtype=str).fillna("")
            for column in ["ticker", "cik", "exchange", "name", "source"]:
                if column not in df.columns:
                    df[column] = ""

            df["ticker"] = df["ticker"].str.upper().str.strip()
            df["cik"] = df["cik"].astype(str).str.zfill(10)
            df["_priority"] = df["source"].map(self.SOURCE_PRIORITY).fillna(99).astype(int)
            df = df.sort_values(["_priority", "ticker", "cik"])

            self.cik_to_ticker = {}
            self.cik_to_tickers = {}
            self.cik_to_exchanges = {}
            self.ticker_to_cik = {}
            self.ticker_to_exchange = {}
            self.ticker_to_name = {}

            for _, record in df.iterrows():
                ticker = record["ticker"]
                cik = record["cik"]
                if not ticker or not cik:
                    continue

                self.ticker_to_cik.setdefault(ticker, cik)
                self.ticker_to_exchange.setdefault(ticker, record.get("exchange", ""))
                self.ticker_to_name.setdefault(ticker, record.get("name", ""))

                tickers = self.cik_to_tickers.setdefault(cik, [])
                if ticker not in tickers:
                    tickers.append(ticker)
                exchanges = self.cik_to_exchanges.setdefault(cik, [])
                exchange = record.get("exchange", "")
                if exchange and exchange not in exchanges:
                    exchanges.append(exchange)
                self.cik_to_ticker.setdefault(cik, ticker)

            logger.info("Loaded %s ticker mappings", len(self.ticker_to_cik))

        except Exception as e:
            logger.error("Error loading ticker mapping: %s", e)

    def get_ticker(self, cik: str) -> Optional[str]:
        """Get primary ticker for a CIK."""
        cik_padded = str(cik).zfill(10)
        return self.cik_to_ticker.get(cik_padded)

    def get_tickers(self, cik: str) -> List[str]:
        """Get all known tickers for a CIK, in source-priority order."""
        cik_padded = str(cik).zfill(10)
        return list(self.cik_to_tickers.get(cik_padded, []))

    def get_exchanges(self, cik: str) -> List[str]:
        """Get all known exchanges for a CIK, in source-priority order."""
        cik_padded = str(cik).zfill(10)
        return list(self.cik_to_exchanges.get(cik_padded, []))

    def get_cik(self, ticker: str) -> Optional[str]:
        """Get CIK for a ticker."""
        return self.ticker_to_cik.get(str(ticker).upper())

    def enrich_companies_with_tickers(self, companies_data: Dict) -> Dict:
        """
        Add ticker symbols and exchange data to companies data.

        Args:
            companies_data: Dictionary of company data

        Returns:
            Updated companies data with ticker symbols
        """
        if not self.ticker_to_cik:
            self.download_mapping()

        if not self.ticker_to_cik:
            logger.warning("No ticker mapping available, returning original data")
            return companies_data

        enriched_count = 0
        for cik, company in companies_data.items():
            tickers = self.get_tickers(cik)
            exchanges = self.get_exchanges(cik)
            if not tickers:
                continue

            company.setdefault("tickers", [])
            company.setdefault("exchanges", [])

            before = len(company.get("tickers") or [])
            for ticker in tickers:
                if ticker not in company["tickers"]:
                    company["tickers"].append(ticker)
            for exchange in exchanges:
                if exchange and exchange not in company["exchanges"]:
                    company["exchanges"].append(exchange)
            if len(company.get("tickers") or []) > before:
                enriched_count += 1

        logger.info("Enriched %s companies with ticker symbols", enriched_count)
        return companies_data
