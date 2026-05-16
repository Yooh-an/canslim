"""Free SEC 13F institutional sponsorship helpers.

The SEC 13F feed reports institutional investment manager holdings by CUSIP.
This module keeps the implementation dependency-free: it can parse local 13F
information-table XML files, optionally download recent filings for configured
manager CIKs, aggregate holder/value trends, and apply them to screener records.
"""

from __future__ import annotations

import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"
SEC_ARCHIVE_FILE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{filename}"


def normalize_cusip(cusip: Any) -> str:
    """Normalize a CUSIP to the SEC 13F nine-character alphanumeric form."""
    if cusip is None:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(cusip).upper())[:9]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_child_text(element: ET.Element, *names: str) -> Optional[str]:
    wanted = {name.lower() for name in names}
    for child in element.iter():
        if child is element:
            continue
        if _local_name(child.tag).lower() in wanted and child.text is not None:
            text = child.text.strip()
            if text:
                return text
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


def _to_int(value: Any) -> Optional[int]:
    number = _to_float(value)
    return int(number) if number is not None else None


def _normalize_name(value: Any) -> str:
    text = re.sub(r"[^A-Z0-9 ]", " ", str(value or "").upper())
    text = re.sub(
        r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|PLC|SA|NV|COM|CLASS|CL|THE)\b",
        " ",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def parse_13f_information_table(
    xml_content: str,
    *,
    manager_cik: Optional[str] = None,
    manager_name: Optional[str] = None,
    filing_date: Optional[str] = None,
    report_period: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Parse a SEC 13F information-table XML document into holding rows."""
    if not xml_content or not str(xml_content).strip():
        return []

    root = ET.fromstring(xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content)
    rows: List[Dict[str, Any]] = []
    manager_cik_padded = str(manager_cik).zfill(10) if manager_cik else None

    for node in root.iter():
        if _local_name(node.tag).lower() != "infotable":
            continue
        cusip = normalize_cusip(_find_child_text(node, "cusip"))
        if not cusip:
            continue
        value = _to_float(_find_child_text(node, "value"))
        shares = _to_int(_find_child_text(node, "sshPrnamt", "shrsOrPrnAmt"))
        row = {
            "cusip": cusip,
            "issuer": _find_child_text(node, "nameOfIssuer"),
            "title_of_class": _find_child_text(node, "titleOfClass"),
            "value_usd": int(value) if value is not None else None,
            "shares": shares,
            "manager_cik": manager_cik_padded,
            "manager_name": manager_name,
            "filing_date": filing_date,
            "report_period": report_period,
        }
        rows.append(row)
    return rows


def _manager_positions(holdings: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """Aggregate 13F holdings by CUSIP and manager."""
    if not holdings:
        return pd.DataFrame(columns=["cusip", "manager_key", "manager_name", "value_usd", "shares"])
    df = pd.DataFrame(holdings).copy()
    df["cusip"] = df.get("cusip", pd.Series(dtype=object)).map(normalize_cusip)
    df = df[df["cusip"] != ""]
    if df.empty:
        return pd.DataFrame(columns=["cusip", "manager_key", "manager_name", "value_usd", "shares"])
    if "manager_cik" not in df.columns:
        df["manager_cik"] = None
    if "manager_name" not in df.columns:
        df["manager_name"] = None
    df["manager_key"] = df["manager_cik"].fillna(df["manager_name"])
    df["manager_name"] = df["manager_name"].fillna(df["manager_key"])
    df["value_usd"] = pd.to_numeric(df.get("value_usd"), errors="coerce").fillna(0)
    df["shares"] = pd.to_numeric(df.get("shares"), errors="coerce").fillna(0)
    return df.groupby(["cusip", "manager_key"], dropna=True).agg(
        manager_name=("manager_name", "first"),
        value_usd=("value_usd", "sum"),
        shares=("shares", "sum"),
    ).reset_index()


def _institutional_flow_metrics(
    current_holdings: Sequence[Mapping[str, Any]],
    previous_holdings: Sequence[Mapping[str, Any]],
) -> pd.DataFrame:
    """Calculate manager-level new/increased/decreased/exited 13F flow metrics."""
    current = _manager_positions(current_holdings).rename(columns={"value_usd": "current_value", "shares": "current_shares"})
    previous = _manager_positions(previous_holdings).rename(columns={"value_usd": "previous_value", "shares": "previous_shares"})
    if current.empty and previous.empty:
        return pd.DataFrame(columns=["cusip"])
    merged = current.merge(previous, on=["cusip", "manager_key"], how="outer", suffixes=("_current", "_previous"))
    for column in ["current_value", "previous_value", "current_shares", "previous_shares"]:
        if column not in merged.columns:
            merged[column] = 0
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0)
    merged["manager_name"] = merged.get("manager_name_current", pd.Series(index=merged.index, dtype=object)).fillna(
        merged.get("manager_name_previous", pd.Series(index=merged.index, dtype=object))
    )
    merged["value_change"] = merged["current_value"] - merged["previous_value"]
    merged["is_new"] = (merged["current_value"] > 0) & (merged["previous_value"] <= 0)
    merged["is_exited"] = (merged["current_value"] <= 0) & (merged["previous_value"] > 0)
    merged["is_increased"] = (merged["current_value"] > merged["previous_value"]) & ~merged["is_new"]
    merged["is_decreased"] = (merged["current_value"] < merged["previous_value"]) & ~merged["is_exited"]

    rows: List[Dict[str, Any]] = []
    for cusip, group in merged.groupby("cusip"):
        top = group[group["value_change"] > 0].sort_values("value_change", ascending=False).head(3)
        rows.append(
            {
                "cusip": cusip,
                "new_holder_count": int(group["is_new"].sum()),
                "increased_holder_count": int(group["is_increased"].sum()),
                "decreased_holder_count": int(group["is_decreased"].sum()),
                "exited_holder_count": int(group["is_exited"].sum()),
                "top_accumulating_managers": [
                    {
                        "manager_name": row.get("manager_name"),
                        "manager_key": row.get("manager_key"),
                        "value_change": float(row.get("value_change", 0)),
                    }
                    for row in top.to_dict(orient="records")
                ],
            }
        )
    return pd.DataFrame(rows)


def _aggregate_holdings(holdings: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    if not holdings:
        return pd.DataFrame(columns=["cusip", "issuer", "institutional_holders", "institutional_value", "institutional_shares"])

    df = pd.DataFrame(holdings).copy()
    df["cusip"] = df["cusip"].map(normalize_cusip)
    df = df[df["cusip"] != ""]
    if df.empty:
        return pd.DataFrame(columns=["cusip", "issuer", "institutional_holders", "institutional_value", "institutional_shares"])

    if "issuer" not in df.columns:
        df["issuer"] = None
    df["manager_key"] = df.get("manager_cik", pd.Series(index=df.index, dtype=object)).fillna(
        df.get("manager_name", pd.Series(index=df.index, dtype=object))
    )
    df["value_usd"] = pd.to_numeric(df.get("value_usd"), errors="coerce").fillna(0)
    df["shares"] = pd.to_numeric(df.get("shares"), errors="coerce").fillna(0)

    grouped = df.groupby("cusip", dropna=True).agg(
        issuer=("issuer", lambda values: next((value for value in values if pd.notna(value) and value), None)),
        institutional_holders=("manager_key", lambda values: int(pd.Series(values).dropna().nunique())),
        institutional_value=("value_usd", "sum"),
        institutional_shares=("shares", "sum"),
    )
    return grouped.reset_index()


def aggregate_institutional_trends(
    current_holdings: Sequence[Mapping[str, Any]],
    previous_holdings: Sequence[Mapping[str, Any]],
) -> pd.DataFrame:
    """Aggregate current/previous 13F holdings into CUSIP-level trend metrics."""
    current = _aggregate_holdings(current_holdings)
    previous = _aggregate_holdings(previous_holdings).rename(
        columns={
            "institutional_holders": "institutional_holders_previous",
            "institutional_value": "institutional_value_previous",
            "institutional_shares": "institutional_shares_previous",
        }
    )

    if current.empty and previous.empty:
        return pd.DataFrame()
    if current.empty:
        current = pd.DataFrame({"cusip": previous["cusip"]})

    flow_metrics = _institutional_flow_metrics(current_holdings, previous_holdings)

    keep_previous = [
        column for column in [
            "cusip",
            "institutional_holders_previous",
            "institutional_value_previous",
            "institutional_shares_previous",
        ]
        if column in previous.columns
    ]
    trends = current.merge(previous[keep_previous], on="cusip", how="outer") if keep_previous else current.copy()
    if not flow_metrics.empty:
        trends = trends.merge(flow_metrics, on="cusip", how="left")

    for column in [
        "institutional_holders",
        "institutional_value",
        "institutional_shares",
        "institutional_holders_previous",
        "institutional_value_previous",
        "institutional_shares_previous",
    ]:
        if column not in trends.columns:
            trends[column] = 0
        trends[column] = pd.to_numeric(trends[column], errors="coerce").fillna(0)

    trends["institutional_holders_qoq_change"] = (
        trends["institutional_holders"] - trends["institutional_holders_previous"]
    ).astype(int)
    trends["institutional_shares_qoq_change"] = [
        None if previous <= 0 else current / previous - 1
        for current, previous in zip(trends["institutional_shares"], trends["institutional_shares_previous"])
    ]
    trends["institutional_value_qoq_change"] = [
        None if previous <= 0 else current / previous - 1
        for current, previous in zip(trends["institutional_value"], trends["institutional_value_previous"])
    ]
    for column in ["institutional_shares_qoq_change", "institutional_value_qoq_change"]:
        trends[column] = trends[column].astype(object)
        trends.loc[trends[column].isna(), column] = None
    for column in ["new_holder_count", "increased_holder_count", "decreased_holder_count", "exited_holder_count"]:
        if column not in trends.columns:
            trends[column] = 0
        trends[column] = pd.to_numeric(trends[column], errors="coerce").fillna(0).astype(int)
    if "top_accumulating_managers" not in trends.columns:
        trends["top_accumulating_managers"] = [[] for _ in range(len(trends))]
    trends["top_accumulating_managers"] = trends["top_accumulating_managers"].map(lambda value: value if isinstance(value, list) else [])
    trends["institutional_accumulation_score"] = [
        max(
            0,
            min(
                100,
                50
                + row["new_holder_count"] * 10
                + row["increased_holder_count"] * 5
                - row["decreased_holder_count"] * 5
                - row["exited_holder_count"] * 10
                + (0 if row["institutional_value_qoq_change"] is None else float(row["institutional_value_qoq_change"]) * 20),
            ),
        )
        for _, row in trends.iterrows()
    ]
    trends["institutional_data_source"] = "sec_13f"
    return trends.where(pd.notna(trends), None)


def _name_tokens(value: Any) -> set[str]:
    return {token for token in _normalize_name(value).split() if len(token) > 1}


def _name_similarity(left: Any, right: Any) -> float:
    left_tokens = _name_tokens(left)
    right_tokens = _name_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    return overlap / max(len(left_tokens), len(right_tokens))


def build_cusip_ticker_mapping(
    companies: Sequence[Mapping[str, Any]],
    holdings: Sequence[Mapping[str, Any]],
    *,
    min_score: float = 0.67,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Infer a CUSIP-to-ticker map from 13F issuer names and company names.

    This is a convenience bootstrapper. Persist and review its output before
    relying on it for production screening because issuer names can be ambiguous.
    """
    company_rows = [
        {"ticker": str(company.get("ticker") or "").upper().replace(".", "-"), "name": company.get("name")}
        for company in companies
        if company.get("ticker") and company.get("name")
    ]
    mapping: Dict[str, str] = {}
    suggestions: List[Dict[str, Any]] = []
    seen_cusips: set[str] = set()
    for holding in holdings:
        cusip = normalize_cusip(holding.get("cusip"))
        if not cusip or cusip in seen_cusips:
            continue
        seen_cusips.add(cusip)
        issuer = holding.get("issuer")
        best_company = None
        best_score = 0.0
        for company in company_rows:
            score = _name_similarity(issuer, company["name"])
            if score > best_score:
                best_score = score
                best_company = company
        if best_company and best_score >= min_score:
            mapping[cusip] = best_company["ticker"]
        suggestions.append(
            {
                "cusip": cusip,
                "issuer": issuer,
                "suggested_ticker": best_company["ticker"] if best_company else None,
                "suggested_company": best_company["name"] if best_company else None,
                "score": best_score,
                "mapped": bool(best_company and best_score >= min_score),
            }
        )
    coverage = {
        "total_cusips": len(seen_cusips),
        "mapped_count": len(mapping),
        "unmapped_count": len(seen_cusips) - len(mapping),
        "mapping_rate": len(mapping) / len(seen_cusips) if seen_cusips else 0.0,
        "suggestions": suggestions,
    }
    return mapping, coverage


def export_cusip_mapping_coverage(coverage: Mapping[str, Any], path: str) -> str:
    """Write CUSIP mapping suggestions/coverage to CSV for manual review."""
    Path(os.path.dirname(path) or ".").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(coverage.get("suggestions", [])).to_csv(path, index=False)
    return path


def load_cusip_ticker_mapping(path: Optional[str]) -> Dict[str, str]:
    """Load optional CUSIP-to-ticker mapping from CSV or JSON."""
    if not path or not os.path.exists(path):
        return {}
    if path.endswith(".json"):
        with open(path, "r") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            return {normalize_cusip(cusip): str(ticker).upper() for cusip, ticker in payload.items() if normalize_cusip(cusip)}
        rows = payload if isinstance(payload, list) else []
    else:
        rows = pd.read_csv(path).to_dict(orient="records")

    mapping: Dict[str, str] = {}
    for row in rows:
        cusip = normalize_cusip(row.get("cusip") or row.get("CUSIP"))
        ticker = row.get("ticker") or row.get("Ticker") or row.get("symbol")
        if cusip and ticker:
            mapping[cusip] = str(ticker).upper().replace(".", "-")
    return mapping


def apply_institutional_trends(
    companies: Sequence[Mapping[str, Any]],
    trends: pd.DataFrame,
    cusip_ticker_mapping: Optional[Mapping[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Apply CUSIP-level 13F trend metrics to company dictionaries."""
    output = [dict(company) for company in companies]
    if trends is None or trends.empty:
        return output

    mapping = {normalize_cusip(cusip): str(ticker).upper().replace(".", "-") for cusip, ticker in (cusip_ticker_mapping or {}).items()}
    trends_by_cusip = {row["cusip"]: row for row in trends.to_dict(orient="records") if row.get("cusip")}
    trends_by_ticker = {ticker: trends_by_cusip[cusip] for cusip, ticker in mapping.items() if cusip in trends_by_cusip}
    trends_by_name = {
        _normalize_name(row.get("issuer")): row
        for row in trends.to_dict(orient="records")
        if _normalize_name(row.get("issuer"))
    }

    metric_fields = [
        "cusip",
        "institutional_holders",
        "institutional_value",
        "institutional_shares",
        "institutional_holders_previous",
        "institutional_value_previous",
        "institutional_shares_previous",
        "institutional_holders_qoq_change",
        "institutional_value_qoq_change",
        "institutional_shares_qoq_change",
        "new_holder_count",
        "increased_holder_count",
        "decreased_holder_count",
        "exited_holder_count",
        "institutional_accumulation_score",
        "top_accumulating_managers",
    ]

    for company in output:
        company_cusip = normalize_cusip(company.get("cusip"))
        ticker = str(company.get("ticker") or "").upper().replace(".", "-")
        row = trends_by_cusip.get(company_cusip) if company_cusip else None
        source = "sec_13f"
        if row is None and ticker:
            row = trends_by_ticker.get(ticker)
        if row is None:
            row = trends_by_name.get(_normalize_name(company.get("name")))
            source = "sec_13f_name_match"
        if row is None:
            continue

        for field in metric_fields:
            if field in row and row[field] is not None:
                value = row[field]
                if hasattr(value, "item"):
                    value = value.item()
                company[field] = value
        company["institutional_data_source"] = source
    return output


class Institutional13FCollector:
    """Download and parse latest/previous SEC 13F holdings for configured managers."""

    def __init__(self, sec_client: Any, raw_dir: str = "data/raw/institutional_13f"):
        self.sec_client = sec_client
        self.raw_dir = Path(raw_dir)
        self.current_dir = self.raw_dir / "current"
        self.previous_dir = self.raw_dir / "previous"
        self.current_dir.mkdir(parents=True, exist_ok=True)
        self.previous_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normalize_cik(cik: Any) -> str:
        return re.sub(r"\D", "", str(cik or "")).zfill(10)

    def _get_recent_13f_filings(self, cik: str) -> Tuple[str, List[Dict[str, Any]]]:
        padded = self._normalize_cik(cik)
        url = SEC_SUBMISSIONS_URL.format(cik=padded)
        payload = self.sec_client._make_request(url).json()
        recent = payload.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        filings: List[Dict[str, Any]] = []
        for index, form in enumerate(forms):
            if str(form).upper() not in {"13F-HR", "13F-HR/A"}:
                continue
            accession = accessions[index]
            filings.append(
                {
                    "cik": padded,
                    "accession": accession,
                    "accession_nodash": str(accession).replace("-", ""),
                    "filing_date": filing_dates[index] if index < len(filing_dates) else None,
                    "report_period": report_dates[index] if index < len(report_dates) else None,
                }
            )
        filings.sort(key=lambda row: (row.get("report_period") or "", row.get("filing_date") or ""), reverse=True)
        return payload.get("name") or padded, filings

    def _find_information_table_url(self, cik: str, accession_nodash: str) -> str:
        cik_no_zero = str(int(cik))
        index_url = SEC_FILING_INDEX_URL.format(cik=cik_no_zero, accession=accession_nodash)
        payload = self.sec_client._make_request(index_url).json()
        items = payload.get("directory", {}).get("item", [])
        xml_items = [item for item in items if str(item.get("name", "")).lower().endswith(".xml")]
        preferred = [
            item for item in xml_items
            if "info" in str(item.get("name", "")).lower() or "table" in str(item.get("name", "")).lower()
        ]
        non_primary = [item for item in xml_items if str(item.get("name", "")).lower() != "primary_doc.xml"]
        candidates = preferred or non_primary or xml_items
        selected = max(candidates, key=lambda item: int(item.get("size") or 0)) if candidates else None
        if not selected:
            raise FileNotFoundError(f"No XML information table found for {cik} {accession_nodash}")
        return SEC_ARCHIVE_FILE_URL.format(cik=cik_no_zero, accession=accession_nodash, filename=selected["name"])

    def _download_holding_file(self, manager_name: str, filing: Mapping[str, Any], target_dir: Path) -> List[Dict[str, Any]]:
        url = self._find_information_table_url(filing["cik"], filing["accession_nodash"])
        xml_content = self.sec_client._make_request(url).text
        output_file = target_dir / f"{filing['cik']}_{filing.get('report_period') or filing['accession_nodash']}.xml"
        output_file.write_text(xml_content, encoding="utf-8")
        return parse_13f_information_table(
            xml_content,
            manager_cik=filing["cik"],
            manager_name=manager_name,
            filing_date=filing.get("filing_date"),
            report_period=filing.get("report_period"),
        )

    def fetch_latest_and_previous_holdings(self, manager_ciks: Iterable[Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Fetch latest and previous 13F holdings for each manager CIK."""
        current_holdings: List[Dict[str, Any]] = []
        previous_holdings: List[Dict[str, Any]] = []
        for cik in manager_ciks:
            manager_name, filings = self._get_recent_13f_filings(str(cik))
            if not filings:
                logger.warning("No recent 13F filings found for manager CIK %s", cik)
                continue
            try:
                current_holdings.extend(self._download_holding_file(manager_name, filings[0], self.current_dir))
                if len(filings) > 1:
                    previous_holdings.extend(self._download_holding_file(manager_name, filings[1], self.previous_dir))
            except Exception as exc:  # pragma: no cover - defensive logging around live SEC calls
                logger.warning("Failed to fetch 13F holdings for manager CIK %s: %s", cik, exc)
        return current_holdings, previous_holdings

    def load_local_holdings(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Load existing current/previous XML files from raw_dir."""
        return self._load_dir(self.current_dir), self._load_dir(self.previous_dir)

    def _load_dir(self, directory: Path) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for path in sorted(directory.glob("*.xml")):
            match = re.match(r"(?P<cik>\d{10})_(?P<period>[^.]+)", path.name)
            manager_cik = match.group("cik") if match else None
            report_period = match.group("period") if match else None
            rows.extend(
                parse_13f_information_table(
                    path.read_text(encoding="utf-8"),
                    manager_cik=manager_cik,
                    report_period=report_period,
                )
            )
        return rows


def enrich_companies_with_13f_data(companies: Sequence[Mapping[str, Any]], config: Mapping[str, Any], sec_client: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Enrich company dictionaries with configured SEC 13F institutional trends."""
    institutional_config = config.get("institutional_data", {}) if isinstance(config, Mapping) else {}
    if not institutional_config.get("enabled", False):
        return [dict(company) for company in companies]

    data_paths = config.get("data_paths", {}) if isinstance(config, Mapping) else {}
    raw_dir = institutional_config.get(
        "raw_13f_dir",
        os.path.join(data_paths.get("raw_data_dir", "data/raw"), "institutional_13f"),
    )
    collector = Institutional13FCollector(sec_client, raw_dir=raw_dir) if sec_client is not None else None

    manager_ciks = institutional_config.get("manager_ciks", [])
    if collector is not None and manager_ciks:
        current_holdings, previous_holdings = collector.fetch_latest_and_previous_holdings(manager_ciks)
    elif collector is not None:
        current_holdings, previous_holdings = collector.load_local_holdings()
    else:
        # No SEC client was supplied; load local XML files only.
        from types import SimpleNamespace

        local_collector = Institutional13FCollector(SimpleNamespace(), raw_dir=raw_dir)
        current_holdings, previous_holdings = local_collector.load_local_holdings()

    trends = aggregate_institutional_trends(current_holdings, previous_holdings)
    mapping_path = institutional_config.get(
        "cusip_ticker_mapping",
        data_paths.get("cusip_ticker_mapping", "data/processed/cusip_ticker_mapping.csv"),
    )
    mapping = load_cusip_ticker_mapping(mapping_path)
    return apply_institutional_trends(companies, trends, mapping)
