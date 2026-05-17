"""O'Neil-style buy-zone and risk-management helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


def _round_price(value: float) -> float:
    return round(float(value), 2)


def calculate_trade_rules(
    current_price: Optional[float],
    pivot_price: Optional[float],
    *,
    buy_zone_pct: float = 0.05,
    stop_loss_pct: float = 0.08,
    profit_target_low_pct: float = 0.20,
    profit_target_high_pct: float = 0.25,
) -> Dict[str, Any]:
    """Calculate classic CAN SLIM buy zone, stop, and initial profit target levels."""
    if (
        current_price is None
        or pivot_price is None
        or not pd.notna(current_price)
        or not pd.notna(pivot_price)
        or current_price <= 0
        or pivot_price <= 0
    ):
        return {
            "buy_zone_low": None,
            "buy_zone_high": None,
            "in_buy_zone": False,
            "extended_from_pivot": False,
            "stop_loss_price": None,
            "profit_target_low": None,
            "profit_target_high": None,
            "pct_from_pivot": None,
        }

    pct_from_pivot = current_price / pivot_price - 1
    buy_zone_high = pivot_price * (1 + buy_zone_pct)
    return {
        "buy_zone_low": _round_price(pivot_price),
        "buy_zone_high": _round_price(buy_zone_high),
        "in_buy_zone": bool(0 <= pct_from_pivot <= buy_zone_pct),
        "extended_from_pivot": bool(pct_from_pivot > buy_zone_pct),
        "stop_loss_price": _round_price(pivot_price * (1 - stop_loss_pct)),
        "profit_target_low": _round_price(pivot_price * (1 + profit_target_low_pct)),
        "profit_target_high": _round_price(pivot_price * (1 + profit_target_high_pct)),
        "pct_from_pivot": float(pct_from_pivot),
    }


def add_trade_rules(company: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of a company record enriched with buy/sell rule levels."""
    enriched = dict(company)
    current_price = (
        enriched.get("current_price")
        or enriched.get("price")
        or enriched.get("latest_close")
        or enriched.get("pivot_price")
    )
    pivot_price = enriched.get("pivot_price")
    enriched.update(calculate_trade_rules(current_price, pivot_price))
    return enriched
