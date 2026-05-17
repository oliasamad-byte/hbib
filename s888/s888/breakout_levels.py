"""Breakout reference levels per spec §5.1.

OR_HIGH  — max of 9:30–9:45 ET first three 5m bars (locked at 9:45 ET)
PDH      — prior trading day's daily high
PMH      — pre-market session high (4:00–9:30 ET)
20d/50d/52w high  — from daily bars
8w high  — from weekly bars
"""

from __future__ import annotations

from datetime import time
from typing import Any

import numpy as np
import pandas as pd

# US Eastern times — we keep bars in their original tz (FMP returns ET).
ORB_START = time(9, 30)
ORB_END = time(9, 45)
PREMARKET_START = time(4, 0)
MARKET_OPEN = time(9, 30)


def _today_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Subset to the most recent calendar date in the index."""
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.empty:
        return bars
    last_date = bars.index[-1].normalize()
    return bars[bars.index.normalize() == last_date]


def opening_range_high(bars_5m: pd.DataFrame) -> float:
    """Max high across the first three 5m bars of the session (9:30, 9:35, 9:40).
    Returns NaN before the third bar closes. Locks after 9:45."""
    today = _today_bars(bars_5m)
    if today.empty:
        return float("nan")
    or_bars = today[(today.index.time >= ORB_START) &
                    (today.index.time < ORB_END)]
    if len(or_bars) < 3:
        return float("nan")
    return float(or_bars["high"].iloc[:3].max())


def opening_range_low(bars_5m: pd.DataFrame) -> float:
    today = _today_bars(bars_5m)
    if today.empty:
        return float("nan")
    or_bars = today[(today.index.time >= ORB_START) &
                    (today.index.time < ORB_END)]
    if len(or_bars) < 3:
        return float("nan")
    return float(or_bars["low"].iloc[:3].min())


def prior_day_high(daily_bars: pd.DataFrame) -> float:
    if len(daily_bars) < 2:
        return float("nan")
    return float(daily_bars["high"].iloc[-2])


def premarket_high(bars_1m: pd.DataFrame) -> float:
    """Highest 1m high between 4:00 ET and 9:30 ET on the latest session."""
    today = _today_bars(bars_1m)
    if today.empty:
        return float("nan")
    pm = today[(today.index.time >= PREMARKET_START) &
               (today.index.time < MARKET_OPEN)]
    if pm.empty:
        return float("nan")
    return float(pm["high"].max())


def nday_high(daily_bars: pd.DataFrame, n: int, exclude_today: bool = True) -> float:
    """Highest high over the last N daily bars. If exclude_today=True,
    exclude the most recent bar (so 'today closes above 20d-high' is
    a real new-high event)."""
    if daily_bars.empty:
        return float("nan")
    bars = daily_bars.iloc[:-1] if exclude_today else daily_bars
    if len(bars) < n:
        return float("nan")
    return float(bars["high"].iloc[-n:].max())


def nweek_high(weekly_bars: pd.DataFrame, n: int = 8, exclude_current: bool = True) -> float:
    if weekly_bars.empty:
        return float("nan")
    bars = weekly_bars.iloc[:-1] if exclude_current else weekly_bars
    if len(bars) < n:
        return float("nan")
    return float(bars["high"].iloc[-n:].max())


def all_levels(daily_bars: pd.DataFrame,
               weekly_bars: pd.DataFrame,
               bars_5m: pd.DataFrame | None = None,
               bars_1m: pd.DataFrame | None = None) -> dict[str, float]:
    """Convenience: compute all breakout reference levels at once."""
    return {
        "or_high":     opening_range_high(bars_5m) if bars_5m is not None else float("nan"),
        "or_low":      opening_range_low(bars_5m) if bars_5m is not None else float("nan"),
        "pdh":         prior_day_high(daily_bars),
        "pmh":         premarket_high(bars_1m) if bars_1m is not None else float("nan"),
        "high_20d":    nday_high(daily_bars, 20),
        "high_50d":    nday_high(daily_bars, 50),
        "high_52w":    nday_high(daily_bars, 252),
        "high_8w":     nweek_high(weekly_bars, 8),
    }
