"""Security classification helpers for profile-aware screening."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping, MutableMapping


FINANCIAL_SIC_START = 6000
FINANCIAL_SIC_END = 6999
ADR_NAME_TERMS = (
    "AMERICAN DEPOSITARY",
    "DEPOSITARY SHARE",
    "DEPOSITARY RECEIPT",
    " ADR",
    " ADS",
)
FOREIGN_ENTITY_TERMS = (
    " PLC",
    " N.V.",
    " NV",
    " S.A.",
    " SA",
    " LTD",
    " LIMITED",
)
FINANCIAL_TEXT_TERMS = (
    "FINANCIAL",
    "BANK",
    "BANKS",
    "INSURANCE",
    "CAPITAL MARKETS",
    "ASSET MANAGEMENT",
    "BROKERAGE",
    "CREDIT SERVICES",
)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _is_financial(company: Mapping[str, Any], reasons: list[str]) -> bool:
    sic_text = str(company.get("sic") or "").strip()
    try:
        sic = int(float(sic_text))
    except ValueError:
        sic = None
    if sic is not None and FINANCIAL_SIC_START <= sic <= FINANCIAL_SIC_END:
        reasons.append("sic_financial_range")
        return True

    haystack = " ".join(
        str(company.get(field) or "")
        for field in ("sector", "industry", "category", "name")
    ).upper()
    if any(term in haystack for term in FINANCIAL_TEXT_TERMS):
        reasons.append("financial_sector_or_name")
        return True
    return False


def _is_adr(company: Mapping[str, Any], reasons: list[str]) -> bool:
    name = str(company.get("name") or "").upper()
    category = str(company.get("category") or "").upper()
    if any(term in name for term in ADR_NAME_TERMS) or "ADR" in category or "ADS" in category:
        reasons.append("depositary_receipt_name")
        return True
    if any(term in name for term in FOREIGN_ENTITY_TERMS):
        reasons.append("foreign_entity_name")
        return True
    return False


def _listing_age_days(company: Mapping[str, Any], as_of: date) -> int | None:
    for field in ("first_price_date", "ipo_date", "listing_date", "first_trade_date"):
        parsed = _parse_date(company.get(field))
        if parsed:
            return max(0, (as_of - parsed).days)
    return None


def classify_company(
    company: Mapping[str, Any],
    *,
    as_of: date | None = None,
    recent_listing_days: int = 730,
) -> dict[str, Any]:
    """Return classification fields for a company/security row.

    The classifier is intentionally conservative and transparent: every positive
    classification records a reason in ``classification_reasons`` so ambiguous
    ADR/foreign/new-listing cases can be reviewed later.
    """
    today = as_of or date.today()
    reasons: list[str] = []
    financial = _is_financial(company, reasons)
    adr = _is_adr(company, reasons)
    listing_age = _listing_age_days(company, today)
    recent_listing = listing_age is not None and listing_age <= recent_listing_days
    if recent_listing:
        reasons.append("recent_listing_age")

    if recent_listing:
        profile = "ipo_spinoff"
    elif financial:
        profile = "financials"
    elif adr:
        profile = "adr_global"
    else:
        profile = "standard"

    return {
        "is_financial": financial,
        "is_adr": adr,
        "is_recent_listing": recent_listing,
        "listing_age_days": listing_age,
        "security_profile": profile,
        "classification_reasons": reasons,
    }


def apply_security_classification(
    company: MutableMapping[str, Any],
    *,
    as_of: date | None = None,
    recent_listing_days: int = 730,
) -> MutableMapping[str, Any]:
    """Add security classification fields to ``company`` in place."""
    company.update(
        classify_company(
            company,
            as_of=as_of,
            recent_listing_days=recent_listing_days,
        )
    )
    return company
