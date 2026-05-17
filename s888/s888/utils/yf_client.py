"""yfinance wrappers — sync calls run in a thread executor when awaited.

yfinance itself isn't async, so we use asyncio.to_thread() for the
network-bound calls so they cooperate with the FMP async pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

YF_DAY_GAINERS = (
    "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
)


async def day_gainers(count: int = 100) -> list[dict]:
    """Pull Yahoo's `day_gainers` saved screener via direct REST.

    Returns a list of dicts with at least: symbol, regularMarketPrice,
    regularMarketChangePercent, marketCap, averageDailyVolume3Month.
    """
    params = {"scrIds": "day_gainers", "count": count}
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(YF_DAY_GAINERS, params=params, headers=headers)
    if r.status_code != 200:
        log.warning("YF day_gainers HTTP %d: %s", r.status_code, r.text[:200])
        return []
    try:
        body = r.json()
    except ValueError as e:
        log.warning("YF day_gainers bad JSON: %s", e)
        return []
    quotes = (body.get("finance", {}).get("result") or [{}])[0].get("quotes", [])
    return _normalize_yf_quotes(quotes)


def _normalize_yf_quotes(quotes: list[dict]) -> list[dict]:
    out: list[dict] = []
    for q in quotes:
        sym = q.get("symbol")
        if not sym:
            continue
        out.append({
            "symbol": sym.upper(),
            "price": q.get("regularMarketPrice"),
            "change_pct": q.get("regularMarketChangePercent"),
            "market_cap": q.get("marketCap"),
            "avg_volume": q.get("averageDailyVolume3Month"),
            "name": q.get("shortName") or q.get("longName"),
        })
    return out


async def news_for(ticker: str, limit: int = 10) -> list[dict]:
    """Per-ticker news via yfinance lib (sync, run in thread)."""
    def _fetch() -> list[dict]:
        import yfinance as yf
        try:
            items = yf.Ticker(ticker.upper()).news or []
        except Exception as e:
            log.warning("YF news for %s failed: %s", ticker, e)
            return []
        return items[:limit]
    return await asyncio.to_thread(_fetch)


async def recommendations(ticker: str) -> Any:
    """Fallback analyst snapshot from yfinance (used if FMP grades fails)."""
    def _fetch() -> Any:
        import yfinance as yf
        try:
            return yf.Ticker(ticker.upper()).recommendations
        except Exception as e:
            log.warning("YF recommendations for %s failed: %s", ticker, e)
            return None
    return await asyncio.to_thread(_fetch)
