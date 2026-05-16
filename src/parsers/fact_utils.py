"""Low-level helpers for SEC companyfacts records."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

import pandas as pd


def item_end_date(item: Dict[str, Any]) -> Optional[str]:
    """Return the SEC fact end date across old and current JSON shapes."""
    if item.get("end"):
        return item.get("end")
    period = item.get("period", {})
    if isinstance(period, dict):
        return period.get("endDate")
    return None


def normalized_form(item: Dict[str, Any]) -> Optional[str]:
    """Normalize amended SEC forms to their base form."""
    form = item.get("form")
    if form in {"10-Q", "10-Q/A"}:
        return "10-Q"
    if form in {"10-K", "10-K/A"}:
        return "10-K"
    return None


def period_start_date(item: Dict[str, Any]) -> Optional[str]:
    if item.get("start"):
        return item.get("start")
    period = item.get("period", {})
    if isinstance(period, dict):
        return period.get("startDate")
    return None


def quarter_number(fp: Optional[str]) -> Optional[int]:
    if not fp:
        return None
    fp = str(fp).upper()
    if fp.startswith("Q") and fp[1:].isdigit():
        quarter = int(fp[1:])
        if 1 <= quarter <= 4:
            return quarter
    return None


def frame_period(frame: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """Extract calendar year/quarter from SEC frame labels like CY2025Q1."""
    if not frame:
        return None, None
    match = re.search(r"CY(\d{4})(?:Q([1-4]))?", str(frame).upper())
    if not match:
        return None, None
    year = int(match.group(1))
    quarter = int(match.group(2)) if match.group(2) else None
    return year, quarter


def quarter_from_end_date(end_date: Optional[str]) -> Optional[int]:
    """Infer a fiscal quarter from an end date when SEC fp/frame fields are absent."""
    if not end_date:
        return None
    try:
        month = pd.Timestamp(end_date).month
    except Exception:
        return None
    return ((month - 1) // 3) + 1


def period_year(record: Dict[str, Any]) -> Optional[int]:
    """
    Return the fiscal year represented by a fact's period.

    SEC companyfacts can repeat historical facts in a newer filing, so ``fy`` can
    occasionally describe the filing context rather than the period. Prefer SEC's
    fiscal year when it is plausible for the fact end date, but fall back to the
    frame/end year for clearly stale restatements.
    """
    end_year = None
    end_date = record.get("end")
    if end_date:
        try:
            end_year = int(pd.Timestamp(end_date).year)
        except Exception:
            end_year = None

    try:
        fy = int(record.get("fy"))
    except (ValueError, TypeError):
        fy = None

    if fy is not None:
        if end_year is None or abs(fy - end_year) <= 1:
            return fy

    frame_year, _ = frame_period(record.get("frame"))
    if frame_year:
        return frame_year
    if end_year is not None:
        return end_year
    return fy


def safe_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
        if pd.notna(parsed):
            return parsed
    except (ValueError, TypeError):
        return None
    return None
