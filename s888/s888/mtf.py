"""Multi-timeframe bar fetcher. Pulls all needed intervals for one ticker
concurrently, returns a dict of pandas DataFrames keyed by interval name."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pandas as pd

from .utils.fmp_client import FMPClient, FMPError

log = logging.getLogger(__name__)

# Spec §5.1 timeframes — name → (fmp interval, lookback bars to fetch)
TIMEFRAMES = {
    "1m":     ("1min",  120),
    "5m":     ("5min",  120),
    "15m":    ("15min", 80),
    "30m":    ("30min", 60),
    "1h":     ("1hour", 80),
    "daily":  ("1day",  250),
    "weekly": ("1week", 80),
}


def _to_dataframe(rows: list[dict], newest_first: bool = True) -> pd.DataFrame:
    """Convert FMP bars (list of dicts) to a sorted ascending DataFrame."""
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows)
    if "date" not in df.columns and "datetime" in df.columns:
        df["date"] = df["datetime"]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    # Normalize column names
    rename = {c: c.lower() for c in df.columns}
    df = df.rename(columns=rename)
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    return df[keep].astype(float)


def daily_to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Fallback weekly bars built from daily (Friday closes)."""
    if daily.empty:
        return daily
    agg = daily.resample("W-FRI").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna(subset=["close"])
    return agg


async def fetch_all(fmp: FMPClient, ticker: str,
                    timeframes: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Fetch all timeframes for one ticker concurrently. Failures return empty DF."""
    tfs = timeframes or list(TIMEFRAMES.keys())
    async def _one(tf: str) -> tuple[str, pd.DataFrame]:
        interval, _ = TIMEFRAMES[tf]
        try:
            if interval == "1week":
                # FMP /historical-price-full doesn't natively return weekly;
                # we always derive weekly from daily for consistency.
                daily_rows = await fmp.historical(ticker, "1day", limit=400)
                df = _to_dataframe(daily_rows)
                df = daily_to_weekly(df)
            elif interval == "1day":
                rows = await fmp.historical(ticker, "1day", limit=250)
                df = _to_dataframe(rows)
            else:
                rows = await fmp.intraday(ticker, interval)
                df = _to_dataframe(rows)
        except FMPError as e:
            log.warning("mtf fetch %s/%s failed: %s", ticker, tf, e)
            df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        return tf, df

    tasks = [_one(tf) for tf in tfs]
    out: dict[str, pd.DataFrame] = {}
    for tf, df in await asyncio.gather(*tasks):
        out[tf] = df
    return out
