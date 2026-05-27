"""Shared research-only disclosure metadata for web UI and exports."""

from __future__ import annotations

from typing import Any


DISCLOSURE_VERSION = 1
DISCLOSURE_TITLE = "Research aid only"
DISCLOSURE_TEXT = (
    "CANSLIM SEPA is a screening and research workflow. It is not financial, "
    "investment, tax, or legal advice."
)
DISCLOSURE_POINTS = [
    "Verify SEC filings, chart structure, liquidity, corporate actions, and data freshness before acting.",
    "Position sizing and guardrails are planning aids; they do not determine suitability or execution risk.",
    "Market data, third-party data, and local cache files can be stale, incomplete, or unavailable.",
]


def research_disclosure() -> dict[str, Any]:
    """Return disclosure metadata safe to embed in UI payloads and JSON exports."""
    return {
        "version": DISCLOSURE_VERSION,
        "title": DISCLOSURE_TITLE,
        "text": DISCLOSURE_TEXT,
        "points": list(DISCLOSURE_POINTS),
    }
