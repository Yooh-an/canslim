"""O'Neil-style setup, buy-zone, and risk-management helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


def _round_price(value: float) -> float:
    return round(float(value), 2)


def _round_pct(value: float) -> float:
    return round(float(value) * 100, 2)


def _empty_trade_plan(
    *,
    pivot_price: Optional[float],
    pct_from_pivot: Optional[float],
    setup_status: str,
    setup_type: str,
    setup_reasons: list[str],
) -> Dict[str, Any]:
    return {
        "pivot_price": _round_price(pivot_price) if pivot_price is not None and pd.notna(pivot_price) else pivot_price,
        "buy_zone_low": None,
        "buy_zone_high": None,
        "in_buy_zone": False,
        "extended_from_pivot": bool(pct_from_pivot is not None and pct_from_pivot > 0.05),
        "stop_loss_price": None,
        "profit_target_low": None,
        "profit_target_high": None,
        "pct_from_pivot": float(pct_from_pivot) if pct_from_pivot is not None else None,
        "pivot_distance_pct": _round_pct(pct_from_pivot) if pct_from_pivot is not None else None,
        "setup_status": setup_status,
        "setup_type": setup_type,
        "setup_reasons": setup_reasons,
    }


def calculate_trade_rules(
    current_price: Optional[float],
    pivot_price: Optional[float],
    *,
    buy_zone_pct: float = 0.05,
    stop_loss_pct: float = 0.08,
    profit_target_low_pct: float = 0.20,
    profit_target_high_pct: float = 0.25,
    breakout_volume_ratio: Optional[float] = None,
    breakout_volume_ratio_min: float = 1.3,
    base_depth: Optional[float] = None,
    base_depth_min: float = 0.10,
    base_depth_max: float = 0.35,
) -> Dict[str, Any]:
    """Calculate setup-aware CAN SLIM trade levels.

    Buy/stop/target levels are only actionable when price is within the pivot
    buy zone. A distant pivot candidate is reported as watch/no-setup context,
    not as an executable trade plan.
    """
    if (
        current_price is None
        or pivot_price is None
        or not pd.notna(current_price)
        or not pd.notna(pivot_price)
        or current_price <= 0
        or pivot_price <= 0
    ):
        return _empty_trade_plan(
            pivot_price=pivot_price,
            pct_from_pivot=None,
            setup_status="no_valid_pivot",
            setup_type="no_setup",
            setup_reasons=["missing current price or pivot candidate"],
        )

    pct_from_pivot = current_price / pivot_price - 1
    reasons: list[str] = []

    if base_depth is not None and pd.notna(base_depth):
        if base_depth < base_depth_min:
            reasons.append(f"base depth {base_depth:.1%} is shallower than normal base range")
        elif base_depth > base_depth_max:
            reasons.append(f"base depth {base_depth:.1%} is deeper than preferred base range")
        else:
            reasons.append(f"base depth {base_depth:.1%} is within preferred range")

    if pct_from_pivot < -0.10:
        reasons.append("price is more than 10% below pivot candidate")
        return _empty_trade_plan(
            pivot_price=pivot_price,
            pct_from_pivot=pct_from_pivot,
            setup_status="below_pivot_not_actionable",
            setup_type="no_setup",
            setup_reasons=reasons,
        )

    if pct_from_pivot < -buy_zone_pct:
        reasons.append("price is 5-10% below pivot; base may still be forming")
        return _empty_trade_plan(
            pivot_price=pivot_price,
            pct_from_pivot=pct_from_pivot,
            setup_status="forming_base",
            setup_type="base_candidate",
            setup_reasons=reasons,
        )

    if pct_from_pivot < 0:
        reasons.append("price is within 5% below pivot; watch for breakout")
        return _empty_trade_plan(
            pivot_price=pivot_price,
            pct_from_pivot=pct_from_pivot,
            setup_status="near_pivot",
            setup_type="pivot_watch",
            setup_reasons=reasons,
        )

    if pct_from_pivot > buy_zone_pct:
        reasons.append("price is more than 5% above pivot; extended from proper buy zone")
        return _empty_trade_plan(
            pivot_price=pivot_price,
            pct_from_pivot=pct_from_pivot,
            setup_status="extended",
            setup_type="extended",
            setup_reasons=reasons,
        )

    volume_confirmed = (
        breakout_volume_ratio is not None
        and pd.notna(breakout_volume_ratio)
        and breakout_volume_ratio >= breakout_volume_ratio_min
    )
    if volume_confirmed:
        reasons.append(f"breakout volume confirmed at {breakout_volume_ratio:.2f}x")
        setup_status = "breakout_confirmed"
    else:
        reasons.append("price is in buy zone but breakout volume is not confirmed")
        setup_status = "breakout_unconfirmed"

    buy_zone_high = pivot_price * (1 + buy_zone_pct)
    return {
        "pivot_price": _round_price(pivot_price),
        "buy_zone_low": _round_price(pivot_price),
        "buy_zone_high": _round_price(buy_zone_high),
        "in_buy_zone": True,
        "extended_from_pivot": False,
        "stop_loss_price": _round_price(pivot_price * (1 - stop_loss_pct)),
        "profit_target_low": _round_price(pivot_price * (1 + profit_target_low_pct)),
        "profit_target_high": _round_price(pivot_price * (1 + profit_target_high_pct)),
        "pct_from_pivot": float(pct_from_pivot),
        "pivot_distance_pct": _round_pct(pct_from_pivot),
        "setup_status": setup_status,
        "setup_type": "breakout",
        "setup_reasons": reasons,
    }


def add_trade_rules(company: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of a company record enriched with setup and trade levels."""
    enriched = dict(company)
    current_price = (
        enriched.get("current_price")
        or enriched.get("price")
        or enriched.get("latest_close")
        or enriched.get("pivot_price")
    )
    pivot_price = enriched.get("pivot_price")
    enriched.update(
        calculate_trade_rules(
            current_price,
            pivot_price,
            breakout_volume_ratio=enriched.get("breakout_volume_ratio"),
            breakout_volume_ratio_min=enriched.get("breakout_volume_ratio_min", 1.3),
            base_depth=enriched.get("base_depth_65d"),
        )
    )
    return enriched
