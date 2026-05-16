"""O'Neil-style market direction analysis helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


def _series(history: pd.DataFrame, field: str) -> pd.Series:
    """Extract a numeric OHLCV series from regular or yfinance MultiIndex data."""
    if history is None or history.empty:
        return pd.Series(dtype=float)
    if isinstance(history.columns, pd.MultiIndex):
        matches = [column for column in history.columns if str(column[0]).lower() == field.lower()]
        if matches:
            data = history.loc[:, matches[0]]
        else:
            matches = [column for column in history.columns if str(column[-1]).lower() == field.lower()]
            data = history.loc[:, matches[0]] if matches else pd.Series(dtype=float)
    else:
        data = history[field] if field in history.columns else pd.Series(dtype=float)
    result = pd.to_numeric(pd.Series(data), errors="coerce").dropna()
    result.index = pd.to_datetime(result.index, errors="coerce")
    result = result[~result.index.isna()]
    return result.sort_index()


def count_distribution_days(
    close: pd.Series,
    volume: pd.Series,
    lookback: int = 25,
    decline_threshold: float = -0.002,
) -> int:
    """Count IBD-style distribution days: price down meaningfully on higher volume."""
    aligned = pd.concat([close, volume], axis=1, join="inner").dropna()
    if len(aligned) < 2:
        return 0
    aligned.columns = ["close", "volume"]
    recent = aligned.tail(lookback + 1).copy()
    price_change = recent["close"].pct_change()
    volume_change = recent["volume"].diff()
    distribution = (price_change <= decline_threshold) & (volume_change > 0)
    return int(distribution.tail(lookback).sum())


def _find_recent_rally_low(close: pd.Series, lookback: int) -> Optional[int]:
    if close.empty:
        return None
    window = close.tail(min(lookback, len(close)))
    if window.empty:
        return None
    low_label = window.idxmin()
    return int(close.index.get_loc(low_label))


def _find_follow_through_day(
    close: pd.Series,
    volume: pd.Series,
    low_position: int,
    min_gain: float,
    min_day: int,
    max_day: int,
) -> Optional[int]:
    aligned = pd.concat([close, volume], axis=1, join="inner").dropna()
    aligned.columns = ["close", "volume"]
    if len(aligned) < low_position + min_day + 1:
        return None

    for position in range(low_position + min_day, min(len(aligned), low_position + max_day + 1)):
        gain = aligned["close"].iloc[position] / aligned["close"].iloc[position - 1] - 1
        volume_up = aligned["volume"].iloc[position] > aligned["volume"].iloc[position - 1]
        if gain >= min_gain and volume_up:
            return position
    return None


def analyze_market_direction(
    history: pd.DataFrame,
    *,
    benchmark: str = "SPY",
    rally_lookback: int = 30,
    distribution_lookback: int = 25,
    ftd_min_gain: float = 0.0125,
    ftd_min_day: int = 4,
    ftd_max_day: int = 10,
) -> Dict[str, Any]:
    """
    Analyze market direction using CAN SLIM/IBD-inspired rally and FTD rules.

    This is a deterministic proxy for O'Neil's market model: identify a recent
    rally low, look for a day-4-to-day-10 follow-through day on higher volume,
    and downgrade exposure when distribution days cluster.
    """
    close = _series(history, "Close")
    volume = _series(history, "Volume")
    if len(close) < 2:
        return {
            "benchmark": benchmark,
            "market_direction_status": "unknown",
            "recommended_exposure": 0.0,
            "follow_through_day": False,
            "rally_day_count": 0,
            "distribution_days_25d": 0,
        }

    low_position = _find_recent_rally_low(close, rally_lookback)
    if low_position is None:
        low_position = 0
    close_below_rally_low = bool(close.iloc[-1] < close.iloc[low_position])

    ftd_position = _find_follow_through_day(
        close,
        volume,
        low_position,
        ftd_min_gain,
        ftd_min_day,
        ftd_max_day,
    )
    follow_through_day = ftd_position is not None and not close_below_rally_low
    if follow_through_day:
        rally_day_count = int(ftd_position - low_position + 1)
    else:
        rally_day_count = max(0, int(len(close) - low_position - 1))

    distribution_days = count_distribution_days(close, volume, lookback=distribution_lookback)

    sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else np.nan
    sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else np.nan
    close_above_50 = bool(pd.notna(sma50) and close.iloc[-1] > sma50)
    sma50_above_200 = bool(pd.notna(sma50) and pd.notna(sma200) and sma50 > sma200)
    market_return_21d = close.iloc[-1] / close.iloc[-22] - 1 if len(close) >= 22 else np.nan

    if close_below_rally_low or distribution_days >= 7:
        status = "correction"
        exposure = 0.0
    elif follow_through_day and distribution_days >= 5:
        status = "uptrend_under_pressure"
        exposure = 0.3
    elif follow_through_day:
        status = "confirmed_uptrend"
        exposure = 0.75
    elif rally_day_count > 0:
        status = "uptrend_under_pressure"
        exposure = 0.25
    else:
        status = "correction"
        exposure = 0.0

    return {
        "benchmark": benchmark,
        "as_of": pd.Timestamp(close.index[-1]).date().isoformat(),
        "market_direction_status": status,
        "recommended_exposure": exposure,
        "follow_through_day": follow_through_day,
        "rally_day_count": rally_day_count,
        "rally_low_date": pd.Timestamp(close.index[low_position]).date().isoformat(),
        "rally_low": float(close.iloc[low_position]),
        "follow_through_date": (
            pd.Timestamp(close.index[ftd_position]).date().isoformat()
            if ftd_position is not None
            else None
        ),
        "distribution_days_25d": distribution_days,
        "close_above_50dma": close_above_50,
        "sma50_above_sma200": sma50_above_200,
        "market_return_21d": float(market_return_21d) if pd.notna(market_return_21d) else None,
        "latest_close": float(close.iloc[-1]),
        "sma50": float(sma50) if pd.notna(sma50) else None,
        "sma200": float(sma200) if pd.notna(sma200) else None,
    }
