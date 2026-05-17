"""Async FMP client with rate-limit semaphore + retry-on-429.

All public methods return the parsed JSON (list[dict] or dict). They raise
FMPError on persistent failures. The client holds one httpx.AsyncClient
for the lifetime of an async-context-managed instance.

Usage:
    async with FMPClient() as fmp:
        gainers = await fmp.gainers()
        bars    = await fmp.historical("AAPL", interval="1day", limit=200)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from ..config import CFG

log = logging.getLogger(__name__)

BASE = "https://financialmodelingprep.com/api/v3"
BASE_STABLE = "https://financialmodelingprep.com/stable"

# Mapping from spec intervals to FMP path segments.
_INTRADAY_PATHS = {"1min", "5min", "15min", "30min", "1hour", "4hour"}


class FMPError(RuntimeError):
    pass


class FMPClient:
    def __init__(self,
                 api_key: str | None = None,
                 max_concurrent: int | None = None,
                 timeout: float = 30.0,
                 max_retries: int = 4):
        self.api_key = api_key or CFG.fmp_api_key
        if not self.api_key:
            raise FMPError("FMP_API_KEY not set")
        self._sem = asyncio.Semaphore(
            max_concurrent or CFG.fmp_concurrent_requests
        )
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> FMPClient:
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        if self._client is None:
            raise FMPError("FMPClient must be used as async context manager")
        params = {**(params or {}), "apikey": self.api_key}
        delay = 1.0
        for attempt in range(self._max_retries):
            async with self._sem:
                try:
                    r = await self._client.get(url, params=params)
                except httpx.RequestError as e:
                    if attempt == self._max_retries - 1:
                        raise FMPError(f"network: {e}") from e
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
            if r.status_code == 429:
                wait = float(r.headers.get("retry-after", delay))
                log.warning("FMP 429; sleeping %.1fs", wait)
                await asyncio.sleep(wait)
                delay *= 2
                continue
            if r.status_code == 404:
                return []
            if r.status_code != 200:
                raise FMPError(f"HTTP {r.status_code}: {r.text[:200]}")
            try:
                return r.json()
            except ValueError as e:
                raise FMPError(f"bad JSON from {url}: {e}") from e
        raise FMPError(f"gave up after {self._max_retries} retries: {url}")

    # ---------- universe ----------

    async def gainers(self) -> list[dict]:
        return await self._get(f"{BASE}/stock_market/gainers")

    async def screener(self,
                       mcap_min: int | None = None,
                       mcap_max: int | None = None,
                       volume_more_than: int | None = None,
                       limit: int = 50,
                       exchange: str = "NYSE,NASDAQ",
                       country: str = "US",
                       actively_trading: bool = True) -> list[dict]:
        params: dict[str, Any] = {
            "exchange": exchange,
            "country": country,
            "isActivelyTrading": "true" if actively_trading else "false",
            "limit": limit,
            "order": "changesPercentage,desc",
        }
        if mcap_min is not None:
            params["marketCapMoreThan"] = mcap_min
        if mcap_max is not None:
            params["marketCapLowerThan"] = mcap_max
        if volume_more_than is not None:
            params["volumeMoreThan"] = volume_more_than
        return await self._get(f"{BASE}/stock-screener", params=params)

    async def quote(self, ticker: str) -> dict | None:
        data = await self._get(f"{BASE}/quote/{ticker.upper()}")
        return data[0] if isinstance(data, list) and data else None

    # ---------- bars ----------

    async def historical(self, ticker: str,
                         interval: str = "1day",
                         limit: int = 200) -> list[dict]:
        """Daily/weekly/monthly bars: interval ∈ {'1day', '1week', '1month'}.
        Returns list of dicts with date/open/high/low/close/volume, newest first."""
        if interval == "1day":
            data = await self._get(
                f"{BASE}/historical-price-full/{ticker.upper()}",
                params={"timeseries": limit},
            )
            return (data or {}).get("historical", []) if isinstance(data, dict) else []
        if interval not in _INTRADAY_PATHS:
            raise FMPError(f"unknown interval {interval}")
        return await self._get(
            f"{BASE}/historical-chart/{interval}/{ticker.upper()}"
        )

    async def intraday(self, ticker: str, interval: str) -> list[dict]:
        """Intraday bars. Interval ∈ {1min, 5min, 15min, 30min, 1hour}."""
        if interval not in _INTRADAY_PATHS:
            raise FMPError(f"unknown intraday interval {interval}")
        return await self._get(
            f"{BASE}/historical-chart/{interval}/{ticker.upper()}"
        )

    # ---------- news + earnings + analyst ----------

    async def stock_news(self, ticker: str, limit: int = 10) -> list[dict]:
        return await self._get(
            f"{BASE}/stock_news",
            params={"tickers": ticker.upper(), "limit": limit},
        )

    async def press_releases(self, ticker: str, limit: int = 10) -> list[dict]:
        return await self._get(
            f"{BASE}/press-releases/{ticker.upper()}",
            params={"limit": limit},
        )

    async def earning_calendar(self, date_from: str, date_to: str) -> list[dict]:
        return await self._get(
            f"{BASE}/earning_calendar",
            params={"from": date_from, "to": date_to},
        )

    async def grades(self, ticker: str) -> list[dict]:
        """Stable endpoint first, V3 legacy fallback."""
        try:
            return await self._get(
                f"{BASE_STABLE}/grades", params={"symbol": ticker.upper()}
            )
        except FMPError:
            return await self._get(
                f"{BASE}/upgrades-downgrades/{ticker.upper()}"
            )
