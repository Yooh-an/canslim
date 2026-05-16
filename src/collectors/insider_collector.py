"""Free SEC Form 4 insider transaction helpers."""

from __future__ import annotations

import logging
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import pandas as pd

logger = logging.getLogger(__name__)

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"
SEC_ARCHIVE_FILE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{filename}"

BUY_CODES = {"P"}
SELL_CODES = {"S"}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _children(element: ET.Element, name: str) -> List[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == name]


def _first_path_text(element: ET.Element, *path: str) -> Optional[str]:
    nodes = [element]
    for name in path:
        next_nodes: List[ET.Element] = []
        for node in nodes:
            next_nodes.extend(_children(node, name))
        nodes = next_nodes
        if not nodes:
            return None
    for node in nodes:
        if node.text and node.text.strip():
            return node.text.strip()
    return None


def _first_descendant_text(element: ET.Element, name: str) -> Optional[str]:
    for node in element.iter():
        if _local_name(node.tag) == name and node.text and node.text.strip():
            return node.text.strip()
    return None


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        result = float(str(value).replace(",", ""))
        if pd.notna(result):
            return result
    except (TypeError, ValueError):
        return None
    return None


def _normalize_cik(cik: Any) -> str:
    digits = re.sub(r"\D", "", str(cik or ""))
    return digits.zfill(10) if digits else ""


def parse_form4_ownership_xml(
    xml_content: str,
    *,
    filing_date: Optional[str] = None,
    accession: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Parse non-derivative Form 4 open-market buy/sell transactions."""
    if not xml_content or not str(xml_content).strip():
        return []
    root = ET.fromstring(xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content)
    issuer_cik = _normalize_cik(_first_path_text(root, "issuer", "issuerCik"))
    ticker = (_first_path_text(root, "issuer", "issuerTradingSymbol") or "").upper()
    owner_name = _first_path_text(root, "reportingOwner", "reportingOwnerId", "rptOwnerName")
    owner_cik = _normalize_cik(_first_path_text(root, "reportingOwner", "reportingOwnerId", "rptOwnerCik"))

    rows: List[Dict[str, Any]] = []
    for transaction in root.iter():
        if _local_name(transaction.tag) != "nonDerivativeTransaction":
            continue
        code = (_first_descendant_text(transaction, "transactionCode") or "").upper()
        if code not in BUY_CODES | SELL_CODES:
            continue
        shares = _to_float(_first_path_text(transaction, "transactionAmounts", "transactionShares", "value"))
        price = _to_float(_first_path_text(transaction, "transactionAmounts", "transactionPricePerShare", "value"))
        transaction_date = _first_path_text(transaction, "transactionDate", "value")
        if shares is None:
            continue
        value = shares * (price or 0.0)
        if code in SELL_CODES:
            value = -value
        rows.append(
            {
                "ticker": ticker,
                "issuer_cik": issuer_cik,
                "owner_name": owner_name,
                "owner_cik": owner_cik,
                "transaction_code": code,
                "transaction_date": transaction_date,
                "shares": shares,
                "price": price,
                "transaction_value": value,
                "filing_date": filing_date,
                "accession": accession,
            }
        )
    return rows


def aggregate_insider_activity(
    transactions: Sequence[Mapping[str, Any]],
    *,
    as_of: Optional[Any] = None,
    lookback_days: int = 90,
) -> pd.DataFrame:
    """Aggregate Form 4 transactions into ticker-level recent insider activity metrics."""
    if not transactions:
        return pd.DataFrame(columns=["ticker"])
    df = pd.DataFrame(transactions).copy()
    df["ticker"] = df.get("ticker", pd.Series(dtype=object)).fillna("").astype(str).str.upper()
    df = df[df["ticker"] != ""]
    if df.empty:
        return pd.DataFrame(columns=["ticker"])
    df["transaction_value"] = pd.to_numeric(df.get("transaction_value"), errors="coerce").fillna(0)
    if "transaction_date" in df.columns:
        df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
        anchor = pd.to_datetime(as_of) if as_of is not None else df["transaction_date"].max()
        if pd.notna(anchor):
            cutoff = anchor - pd.Timedelta(days=lookback_days)
            df = df[df["transaction_date"].isna() | (df["transaction_date"] >= cutoff)]
    if df.empty:
        return pd.DataFrame(columns=["ticker"])
    df["is_buy"] = df["transaction_value"] > 0
    df["is_sell"] = df["transaction_value"] < 0

    grouped = df.groupby("ticker").agg(
        issuer_cik=("issuer_cik", "first"),
        insider_buy_count_90d=("is_buy", "sum"),
        insider_sell_count_90d=("is_sell", "sum"),
        gross_insider_buy_value_90d=("transaction_value", lambda values: float(pd.Series(values)[pd.Series(values) > 0].sum())),
        gross_insider_sell_value_90d=("transaction_value", lambda values: abs(float(pd.Series(values)[pd.Series(values) < 0].sum()))),
        net_insider_buy_value_90d=("transaction_value", "sum"),
    ).reset_index()
    grouped["insider_buy_count_90d"] = grouped["insider_buy_count_90d"].astype(int)
    grouped["insider_sell_count_90d"] = grouped["insider_sell_count_90d"].astype(int)
    grouped["insider_signal"] = grouped["net_insider_buy_value_90d"].map(
        lambda value: "net_buying" if value > 0 else "net_selling" if value < 0 else "neutral"
    )
    grouped["insider_data_source"] = "sec_form4"
    return grouped


def apply_insider_activity(companies: Sequence[Mapping[str, Any]], activity: pd.DataFrame) -> List[Dict[str, Any]]:
    """Apply ticker-level insider activity to company dictionaries."""
    output = [dict(company) for company in companies]
    if activity is None or activity.empty:
        return output
    by_ticker = {row["ticker"]: row for row in activity.to_dict(orient="records") if row.get("ticker")}
    fields = [
        "insider_buy_count_90d",
        "insider_sell_count_90d",
        "gross_insider_buy_value_90d",
        "gross_insider_sell_value_90d",
        "net_insider_buy_value_90d",
        "insider_signal",
        "insider_data_source",
    ]
    for company in output:
        ticker = str(company.get("ticker") or "").upper().replace(".", "-")
        row = by_ticker.get(ticker)
        if not row:
            continue
        for field in fields:
            if field in row and row[field] is not None:
                value = row[field]
                if hasattr(value, "item"):
                    value = value.item()
                company[field] = value
    return output


class InsiderForm4Collector:
    """Download recent Form 4 ownership XML filings for configured company CIKs."""

    def __init__(self, sec_client: Any, raw_dir: str = "data/raw/insider_form4"):
        self.sec_client = sec_client
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normalize_cik(cik: Any) -> str:
        return _normalize_cik(cik)

    def _recent_form4_filings(self, cik: Any, limit: int) -> List[Dict[str, Any]]:
        padded = self._normalize_cik(cik)
        payload = self.sec_client._make_request(SEC_SUBMISSIONS_URL.format(cik=padded)).json()
        recent = payload.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        filings: List[Dict[str, Any]] = []
        for index, form in enumerate(forms):
            if str(form).upper() != "4":
                continue
            accession = accessions[index]
            filings.append(
                {
                    "cik": padded,
                    "accession": accession,
                    "accession_nodash": str(accession).replace("-", ""),
                    "filing_date": filing_dates[index] if index < len(filing_dates) else None,
                }
            )
            if len(filings) >= limit:
                break
        return filings

    def _find_ownership_xml_url(self, cik: str, accession_nodash: str) -> str:
        cik_no_zero = str(int(cik))
        payload = self.sec_client._make_request(SEC_FILING_INDEX_URL.format(cik=cik_no_zero, accession=accession_nodash)).json()
        items = payload.get("directory", {}).get("item", [])
        xml_items = [item for item in items if str(item.get("name", "")).lower().endswith(".xml")]
        preferred = [item for item in xml_items if "owner" in str(item.get("name", "")).lower() or "ownership" in str(item.get("name", "")).lower()]
        candidates = preferred or xml_items
        selected = max(candidates, key=lambda item: int(item.get("size") or 0)) if candidates else None
        if not selected:
            raise FileNotFoundError(f"No ownership XML found for {cik} {accession_nodash}")
        return SEC_ARCHIVE_FILE_URL.format(cik=cik_no_zero, accession=accession_nodash, filename=selected["name"])

    def fetch_recent_transactions(self, company_ciks: Iterable[Any], *, limit_per_company: int = 20) -> List[Dict[str, Any]]:
        """Fetch recent Form 4 transactions for company CIKs."""
        rows: List[Dict[str, Any]] = []
        for cik in company_ciks:
            for filing in self._recent_form4_filings(cik, limit_per_company):
                try:
                    url = self._find_ownership_xml_url(filing["cik"], filing["accession_nodash"])
                    xml_content = self.sec_client._make_request(url).text
                    output_file = self.raw_dir / f"{filing['cik']}_{filing['accession_nodash']}.xml"
                    output_file.write_text(xml_content, encoding="utf-8")
                    rows.extend(
                        parse_form4_ownership_xml(
                            xml_content,
                            filing_date=filing.get("filing_date"),
                            accession=filing.get("accession"),
                        )
                    )
                except Exception as exc:  # pragma: no cover - live SEC defensive logging
                    logger.warning("Failed to fetch Form 4 %s for %s: %s", filing.get("accession"), cik, exc)
        return rows

    def load_local_transactions(self) -> List[Dict[str, Any]]:
        """Load Form 4 XML files already present in raw_dir."""
        rows: List[Dict[str, Any]] = []
        for path in sorted(self.raw_dir.glob("*.xml")):
            rows.extend(parse_form4_ownership_xml(path.read_text(encoding="utf-8")))
        return rows


def enrich_companies_with_insider_data(companies: Sequence[Mapping[str, Any]], config: Mapping[str, Any], sec_client: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Enrich company dictionaries with optional SEC Form 4 insider activity."""
    insider_config = config.get("insider_data", {}) if isinstance(config, Mapping) else {}
    if not insider_config.get("enabled", False):
        return [dict(company) for company in companies]
    data_paths = config.get("data_paths", {}) if isinstance(config, Mapping) else {}
    raw_dir = insider_config.get("raw_form4_dir", os.path.join(data_paths.get("raw_data_dir", "data/raw"), "insider_form4"))
    collector = InsiderForm4Collector(sec_client, raw_dir=raw_dir) if sec_client is not None else None
    ciks = insider_config.get("company_ciks") or [company.get("cik") for company in companies if company.get("cik")]
    if collector is not None and ciks:
        transactions = collector.fetch_recent_transactions(ciks, limit_per_company=insider_config.get("limit_per_company", 20))
    else:
        from types import SimpleNamespace

        transactions = InsiderForm4Collector(SimpleNamespace(), raw_dir=raw_dir).load_local_transactions()
    return apply_insider_activity(companies, aggregate_insider_activity(transactions))
