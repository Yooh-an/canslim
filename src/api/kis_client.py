"""Korea Investment & Securities Open API client.

The client intentionally covers only the read-only overseas daily-price endpoint
needed by single-ticker analysis.  It returns a yfinance-compatible OHLCV
DataFrame so the rest of the screener can keep using the existing metrics code.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import requests
from dotenv import load_dotenv

from src.utils.logger import setup_logger

logger = setup_logger("kis_client")


class KISAPIError(RuntimeError):
    """Raised when KIS returns an API-level failure."""


class KISClient:
    """Small REST client for KIS overseas stock price history."""

    PROD_BASE_URL = "https://openapi.koreainvestment.com:9443"
    VIRTUAL_BASE_URL = "https://openapivts.koreainvestment.com:29443"
    TOKEN_ENDPOINT = "/oauth2/tokenP"
    OVERSEAS_DAILY_PRICE_ENDPOINT = "/uapi/overseas-price/v1/quotations/dailyprice"
    OVERSEAS_DAILY_PRICE_TR_ID = "HHDFS76240000"
    DEFAULT_US_EXCHANGES = ("NAS", "NYS", "AMS")
    EXCHANGE_ALIASES = {
        "NASDAQ": "NAS",
        "NASD": "NAS",
        "NAS": "NAS",
        "NYSE": "NYS",
        "NEW YORK": "NYS",
        "NYS": "NYS",
        "AMEX": "AMS",
        "NYSE AMERICAN": "AMS",
        "NYSE ARCA": "AMS",
        "ARCA": "AMS",
        "AMS": "AMS",
    }

    def __init__(
        self,
        *,
        app_key: str = "",
        app_secret: str = "",
        access_token: str = "",
        env: str = "prod",
        token_cache_file: str | Path | None = None,
        timeout_seconds: int = 30,
        rate_limit_delay: float = 0.05,
        session: requests.Session | None = None,
        exchange_overrides: Mapping[str, str] | None = None,
        symbol_overrides: Mapping[str, str] | None = None,
        exchange_order: Sequence[str] | None = None,
        max_pages: int = 10,
    ) -> None:
        self.app_key = str(app_key or "").strip()
        self.app_secret = str(app_secret or "").strip()
        self.access_token = str(access_token or "").strip()
        self.env = "vps" if str(env).lower() in {"vps", "demo", "paper", "virtual"} else "prod"
        self.base_url = self.VIRTUAL_BASE_URL if self.env == "vps" else self.PROD_BASE_URL
        self.token_cache_file = Path(token_cache_file) if token_cache_file else None
        self.timeout_seconds = int(timeout_seconds or 30)
        self.rate_limit_delay = float(rate_limit_delay or 0)
        self.session = session or requests.Session()
        self.exchange_overrides = {str(k).upper(): str(v).upper() for k, v in (exchange_overrides or {}).items()}
        self.symbol_overrides = {str(k).upper(): str(v).upper() for k, v in (symbol_overrides or {}).items()}
        self.exchange_order = tuple(self._normalize_exchange(exchange) for exchange in (exchange_order or self.DEFAULT_US_EXCHANGES))
        self.max_pages = int(max_pages or 10)
        self._last_request_time = 0.0

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "KISClient | None":
        """Build a client from config and environment variables.

        Returns None when the provider is disabled or credentials are missing.
        """
        load_dotenv()
        broker_config = config.get("broker_api", {}) if isinstance(config.get("broker_api", {}), Mapping) else {}
        if not broker_config.get("enabled", False):
            return None
        if str(broker_config.get("provider", "kis")).lower() != "kis":
            return None

        app_key_env = str(broker_config.get("app_key_env", "KIS_APP_KEY"))
        app_secret_env = str(broker_config.get("app_secret_env", "KIS_APP_SECRET"))
        access_token_env = str(broker_config.get("access_token_env", "KIS_ACCESS_TOKEN"))
        app_key = str(broker_config.get("app_key") or os.getenv(app_key_env) or "").strip()
        app_secret = str(broker_config.get("app_secret") or os.getenv(app_secret_env) or "").strip()
        access_token = str(broker_config.get("access_token") or os.getenv(access_token_env) or "").strip()
        if not app_key or not app_secret:
            return None

        raw_dir = config.get("data_paths", {}).get("raw_data_dir", "data/raw")
        token_cache_file = broker_config.get("token_cache_file", str(Path(raw_dir) / "kis_token.json"))
        return cls(
            app_key=app_key,
            app_secret=app_secret,
            access_token=access_token,
            env=str(broker_config.get("env", os.getenv("KIS_ENV", "prod"))),
            token_cache_file=token_cache_file,
            timeout_seconds=int(broker_config.get("timeout_seconds", 30)),
            rate_limit_delay=float(broker_config.get("rate_limit_delay", 0.05)),
            exchange_overrides=broker_config.get("exchange_overrides", {}),
            symbol_overrides=broker_config.get("symbol_overrides", {}),
            exchange_order=broker_config.get("exchange_order", cls.DEFAULT_US_EXCHANGES),
            max_pages=int(broker_config.get("max_pages", 10)),
        )

    def is_configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    def get_overseas_daily_history(
        self,
        ticker: str,
        *,
        period: str = "15mo",
        adjusted: bool = True,
        exchange: str | None = None,
    ) -> pd.DataFrame | None:
        """Return adjusted overseas daily OHLCV history for one ticker."""
        if not self.is_configured():
            return None

        symbol = self._broker_symbol(ticker)
        exchanges = self._exchange_candidates(ticker, exchange)
        last_error: Exception | None = None
        for exchange_code in exchanges:
            try:
                payload_rows = self._fetch_daily_price_rows(
                    symbol,
                    exchange_code,
                    adjusted=adjusted,
                )
                history = self._rows_to_history(payload_rows)
                if history is None or history.empty:
                    continue
                history = self._trim_history_period(history, period)
                history.attrs["source"] = "kis_dailyprice"
                history.attrs["exchange"] = exchange_code
                return history
            except Exception as exc:
                last_error = exc
                logger.debug("KIS daily price failed for %s on %s: %s", symbol, exchange_code, exc)

        if last_error:
            logger.info("KIS daily price unavailable for %s: %s", ticker, last_error)
        return None

    def _fetch_daily_price_rows(self, symbol: str, exchange: str, *, adjusted: bool) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        tr_cont = ""
        for _ in range(self.max_pages):
            self._respect_rate_limit()
            response = self.session.get(
                f"{self.base_url}{self.OVERSEAS_DAILY_PRICE_ENDPOINT}",
                headers=self._headers(tr_cont=tr_cont),
                params={
                    "AUTH": "",
                    "EXCD": exchange,
                    "SYMB": symbol,
                    "GUBN": "0",
                    "BYMD": "",
                    "MODP": "1" if adjusted else "0",
                },
                timeout=self.timeout_seconds,
            )
            if response.status_code != 200:
                raise KISAPIError(f"HTTP {response.status_code}: {response.text[:200]}")

            body = response.json()
            if str(body.get("rt_cd", "")) != "0":
                message = body.get("msg1") or body.get("msg_cd") or "unknown KIS error"
                raise KISAPIError(str(message))

            output = body.get("output2") or []
            if isinstance(output, dict):
                output = [output]
            rows.extend(row for row in output if isinstance(row, dict))

            next_cont = response.headers.get("tr_cont", "")
            if next_cont not in {"M", "F"}:
                break
            tr_cont = "N"
        return rows

    def _headers(self, *, tr_cont: str = "") -> dict[str, str]:
        token = self._get_access_token()
        return {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": self.OVERSEAS_DAILY_PRICE_TR_ID,
            "custtype": "P",
            "tr_cont": tr_cont,
        }

    def _get_access_token(self) -> str:
        if self.access_token:
            return self.access_token

        cached = self._load_cached_token()
        if cached:
            self.access_token = cached
            return cached

        response = self.session.post(
            f"{self.base_url}{self.TOKEN_ENDPOINT}",
            headers={
                "Content-Type": "application/json",
                "Accept": "text/plain",
                "charset": "UTF-8",
            },
            data=json.dumps(
                {
                    "grant_type": "client_credentials",
                    "appkey": self.app_key,
                    "appsecret": self.app_secret,
                }
            ),
            timeout=self.timeout_seconds,
        )
        if response.status_code != 200:
            raise KISAPIError(f"token HTTP {response.status_code}: {response.text[:200]}")
        payload = response.json()
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise KISAPIError("token response did not include access_token")
        self.access_token = token
        self._save_cached_token(payload)
        return token

    def _load_cached_token(self) -> str:
        if not self.token_cache_file or not self.token_cache_file.exists():
            return ""
        try:
            payload = json.loads(self.token_cache_file.read_text())
            expires_at = self._parse_expiration(payload.get("access_token_token_expired"))
            if expires_at and expires_at <= datetime.now() + timedelta(minutes=5):
                return ""
            return str(payload.get("access_token") or "").strip()
        except Exception as exc:
            logger.debug("Could not read KIS token cache: %s", exc)
            return ""

    def _save_cached_token(self, payload: Mapping[str, Any]) -> None:
        if not self.token_cache_file:
            return
        try:
            self.token_cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_cache_file.write_text(json.dumps(dict(payload), indent=2))
        except Exception as exc:
            logger.debug("Could not write KIS token cache: %s", exc)

    def _respect_rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if self.rate_limit_delay > 0 and elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _broker_symbol(self, ticker: str) -> str:
        normalized = str(ticker or "").upper().replace("/", "-")
        return self.symbol_overrides.get(normalized, normalized)

    def _exchange_candidates(self, ticker: str, exchange: str | None = None) -> list[str]:
        candidates: list[str] = []
        for candidate in (
            exchange,
            self.exchange_overrides.get(str(ticker or "").upper()),
            *self.exchange_order,
        ):
            normalized = self._normalize_exchange(candidate)
            if normalized and normalized not in candidates:
                candidates.append(normalized)
        return candidates

    @classmethod
    def _normalize_exchange(cls, exchange: str | None) -> str:
        raw = str(exchange or "").strip().upper()
        return cls.EXCHANGE_ALIASES.get(raw, raw)

    @staticmethod
    def _rows_to_history(rows: Sequence[Mapping[str, Any]]) -> pd.DataFrame | None:
        if not rows:
            return None
        frame = pd.DataFrame(rows)
        if "xymd" not in frame.columns:
            return None
        column_map = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "clos": "Close",
            "tvol": "Volume",
        }
        work = frame.rename(columns=column_map)
        available = [column for column in ["Open", "High", "Low", "Close", "Volume"] if column in work.columns]
        if not available:
            return None
        for column in available:
            work[column] = pd.to_numeric(work[column], errors="coerce")
        work.index = pd.to_datetime(work["xymd"], format="%Y%m%d", errors="coerce")
        work = work.loc[work.index.notna(), available]
        work = work.dropna(how="all")
        if work.empty:
            return None
        return work.sort_index()

    @staticmethod
    def _trim_history_period(history: pd.DataFrame, period: str) -> pd.DataFrame:
        start = KISClient._period_start(period)
        if start is None:
            return history
        trimmed = history[history.index >= start]
        return trimmed if not trimmed.empty else history

    @staticmethod
    def _period_start(period: str) -> pd.Timestamp | None:
        text = str(period or "").strip().lower()
        if not text:
            return None
        if text.endswith("mo"):
            unit = "mo"
            amount_text = text[:-2]
        else:
            unit = text[-1]
            amount_text = text[:-1]
        try:
            amount = int(amount_text)
        except ValueError:
            return None
        today = pd.Timestamp.utcnow().tz_localize(None).normalize()
        if unit == "d":
            return today - pd.DateOffset(days=amount)
        if unit == "mo":
            return today - pd.DateOffset(months=amount)
        if unit == "y":
            return today - pd.DateOffset(years=amount)
        return None
