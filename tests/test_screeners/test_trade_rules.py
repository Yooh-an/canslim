"""Tests for O'Neil-style buy and sell rule helpers."""

from src.screeners.trade_rules import calculate_trade_rules


def test_trade_rules_marks_stock_inside_pivot_buy_zone():
    result = calculate_trade_rules(
        current_price=102,
        pivot_price=100,
        breakout_volume_ratio=1.6,
        breakout_volume_ratio_min=1.3,
        base_depth=0.18,
    )

    assert result["buy_zone_low"] == 100
    assert result["buy_zone_high"] == 105
    assert result["in_buy_zone"] is True
    assert result["extended_from_pivot"] is False
    assert result["stop_loss_price"] == 92
    assert result["profit_target_low"] == 120
    assert result["profit_target_high"] == 125
    assert result["setup_status"] == "breakout_confirmed"
    assert result["setup_type"] == "breakout"
    assert result["pivot_distance_pct"] == 2.0
    assert any("volume confirmed" in reason for reason in result["setup_reasons"])


def test_trade_rules_marks_extended_stock_above_five_percent_buy_zone():
    result = calculate_trade_rules(current_price=108, pivot_price=100)

    assert result["in_buy_zone"] is False
    assert result["extended_from_pivot"] is True
    assert result["setup_status"] == "extended"
    assert result["buy_zone_low"] is None


def test_trade_rules_marks_near_pivot_watch_without_entry_plan():
    result = calculate_trade_rules(current_price=97, pivot_price=100, base_depth=0.20)

    assert result["setup_status"] == "near_pivot"
    assert result["setup_type"] == "pivot_watch"
    assert result["buy_zone_low"] is None
    assert result["pivot_distance_pct"] == -3.0
    assert any("within 5% below pivot" in reason for reason in result["setup_reasons"])


def test_trade_rules_suppresses_buy_plan_when_price_is_well_below_pivot():
    result = calculate_trade_rules(current_price=85, pivot_price=100)

    assert result["buy_zone_low"] is None
    assert result["buy_zone_high"] is None
    assert result["stop_loss_price"] is None
    assert result["profit_target_low"] is None
    assert result["profit_target_high"] is None
    assert result["setup_status"] == "below_pivot_not_actionable"
    assert result["pivot_price"] == 100
    assert result["pivot_distance_pct"] == -15.0
    assert any("more than 10% below pivot" in reason for reason in result["setup_reasons"])


def test_trade_rules_handles_missing_pivot():
    result = calculate_trade_rules(current_price=100, pivot_price=None)

    assert result["in_buy_zone"] is False
    assert result["extended_from_pivot"] is False
    assert result["buy_zone_low"] is None
