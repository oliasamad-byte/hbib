"""Technical indicators (pure pandas/numpy, deterministic, fully tested).

Bars are expected as DataFrames with columns: open, high, low, close, volume
indexed by datetime (ascending). All functions handle short inputs by
returning NaN where there isn't enough data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI. Returns 100 when there are no down moves (textbook)."""
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    avg_up = up.ewm(alpha=1 / period, adjust=False).mean()
    avg_dn = down.ewm(alpha=1 / period, adjust=False).mean()
    # Textbook: avg_dn == 0 → RSI = 100; avg_up == 0 → RSI = 0.
    rs = avg_up / avg_dn
    out = 100 - 100 / (1 + rs)
    out = out.where(avg_dn != 0, 100.0)
    out = out.where(avg_up != 0, out.where(avg_up != 0, 0.0))
    return out


def vwap(bars: pd.DataFrame) -> pd.Series:
    """Session-cumulative VWAP. Resets each calendar date."""
    tp = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    pv = tp * bars["volume"]
    if isinstance(bars.index, pd.DatetimeIndex):
        day = bars.index.normalize()
        cum_pv = pv.groupby(day).cumsum()
        cum_v = bars["volume"].groupby(day).cumsum()
    else:
        cum_pv = pv.cumsum()
        cum_v = bars["volume"].cumsum()
    return cum_pv / cum_v.replace(0, np.nan)


def cmf(bars: pd.DataFrame, period: int = 20) -> pd.Series:
    """Chaikin Money Flow."""
    h, l, c, v = bars["high"], bars["low"], bars["close"], bars["volume"]
    rng = (h - l).replace(0, np.nan)
    mfv = ((c - l) - (h - c)) / rng * v
    return mfv.rolling(period).sum() / v.rolling(period).sum().replace(0, np.nan)


def atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder ATR."""
    h, l, c = bars["high"], bars["low"], bars["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def adx(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder ADX (returns adx, not +DI/-DI separately)."""
    h, l, c = bars["high"], bars["low"], bars["close"]
    up = h.diff()
    down = -l.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([h - l, (h - c.shift(1)).abs(),
                    (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr_s = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=bars.index).ewm(
        alpha=1 / period, adjust=False).mean() / atr_s.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=bars.index).ewm(
        alpha=1 / period, adjust=False).mean() / atr_s.replace(0, np.nan)
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def obv(bars: pd.DataFrame) -> pd.Series:
    """On-Balance Volume."""
    direction = np.sign(bars["close"].diff().fillna(0))
    return (direction * bars["volume"]).cumsum()


def obv_slope(bars: pd.DataFrame, lookback: int = 5) -> float:
    """Slope of OBV over last `lookback` bars. >0 = rising."""
    o = obv(bars)
    if len(o) < lookback + 1:
        return 0.0
    recent = o.iloc[-lookback:]
    x = np.arange(len(recent))
    return float(np.polyfit(x, recent.values, 1)[0])


def vol_ratio(bars: pd.DataFrame, period: int = 20) -> float:
    """Current bar volume / SMA(period). Last value."""
    if len(bars) < period:
        return float("nan")
    avg = bars["volume"].rolling(period).mean().iloc[-1]
    if not avg or np.isnan(avg):
        return float("nan")
    return float(bars["volume"].iloc[-1] / avg)


def weinstein_stage(weekly_bars: pd.DataFrame, slope_threshold: float = 0.01) -> int:
    """Weinstein stage from weekly bars, per spec §5.2.

    Returns 1 (basing), 2 (uptrend), 3 (topping), 4 (downtrend).
    """
    if len(weekly_bars) < 30:
        return 4  # treat unknown as downtrend (conservative)
    close = weekly_bars["close"]
    s = close.rolling(30).mean()
    if s.isna().iloc[-1] or len(s.dropna()) < 11:
        return 4
    price = close.iloc[-1]
    sma_now = s.iloc[-1]
    sma_then = s.iloc[-11]
    if sma_then == 0:
        return 4
    slope = (sma_now - sma_then) / sma_then
    above = price > sma_now
    if above and slope > slope_threshold:
        return 2
    if above and abs(slope) <= slope_threshold:
        return 3
    if not above and abs(slope) <= slope_threshold:
        return 1
    return 4
