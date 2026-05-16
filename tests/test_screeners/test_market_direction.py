"""Tests for O'Neil-style market direction analysis."""

import pandas as pd

from src.screeners.market_direction import analyze_market_direction, count_distribution_days


def _history(closes, volumes):
    return pd.DataFrame(
        {"Close": closes, "Volume": volumes},
        index=pd.date_range("2026-01-01", periods=len(closes), freq="B"),
    )


def test_count_distribution_days_requires_price_decline_on_higher_volume():
    history = _history(
        [100, 99.7, 100.2, 99.8, 100.5],
        [1000, 1100, 900, 1200, 1300],
    )

    days = count_distribution_days(history["Close"], history["Volume"], lookback=4)

    assert days == 2


def test_follow_through_day_confirms_new_uptrend_on_day_four_to_ten():
    # Day 0 is the correction low. Day 4 closes +1.7% on higher volume.
    history = _history(
        [100, 101, 100.8, 101.2, 103.0, 103.5, 104.0],
        [1000, 900, 850, 900, 1200, 1100, 1050],
    )

    result = analyze_market_direction(history)

    assert result["market_direction_status"] == "confirmed_uptrend"
    assert result["follow_through_day"] is True
    assert result["rally_day_count"] == 5
    assert result["distribution_days_25d"] == 0
    assert result["recommended_exposure"] >= 0.6


def test_rally_attempt_without_follow_through_is_uptrend_under_pressure():
    history = _history(
        [100, 101, 101.2, 101.3, 101.4, 101.5],
        [1000, 900, 850, 875, 890, 880],
    )

    result = analyze_market_direction(history)

    assert result["market_direction_status"] == "uptrend_under_pressure"
    assert result["follow_through_day"] is False
    assert result["rally_day_count"] == 5
    assert result["recommended_exposure"] == 0.25


def test_distribution_pressure_cuts_confirmed_uptrend_exposure():
    history = _history(
        [100, 101, 100.8, 101.2, 103.0, 102.5, 102.0, 101.7, 101.2, 100.8],
        [1000, 900, 850, 900, 1200, 1300, 1400, 1500, 1600, 1700],
    )

    result = analyze_market_direction(history)

    assert result["follow_through_day"] is True
    assert result["distribution_days_25d"] >= 5
    assert result["market_direction_status"] == "uptrend_under_pressure"
    assert result["recommended_exposure"] == 0.3
