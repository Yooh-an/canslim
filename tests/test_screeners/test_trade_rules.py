"""Tests for O'Neil-style buy and sell rule helpers."""

from src.screeners.trade_rules import calculate_trade_rules


def test_trade_rules_marks_stock_inside_pivot_buy_zone():
    result = calculate_trade_rules(current_price=102, pivot_price=100)

    assert result["buy_zone_low"] == 100
    assert result["buy_zone_high"] == 105
    assert result["in_buy_zone"] is True
    assert result["extended_from_pivot"] is False
    assert result["stop_loss_price"] == 92
    assert result["profit_target_low"] == 120
    assert result["profit_target_high"] == 125


def test_trade_rules_marks_extended_stock_above_five_percent_buy_zone():
    result = calculate_trade_rules(current_price=108, pivot_price=100)

    assert result["in_buy_zone"] is False
    assert result["extended_from_pivot"] is True


def test_trade_rules_handles_missing_pivot():
    result = calculate_trade_rules(current_price=100, pivot_price=None)

    assert result["in_buy_zone"] is False
    assert result["extended_from_pivot"] is False
    assert result["buy_zone_low"] is None
