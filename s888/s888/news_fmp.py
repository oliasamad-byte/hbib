"""FMP news + press-releases puller, normalized to common shape."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .utils.fmp_client import FMPClient, FMPError

log = logging.getLogger(__name__)


def _normalize(item: dict, source: str) -> dict:
    return {
        "ticker": (item.get("symbol") or "").upper(),
        "title": (item.get("title") or "").strip(),
        "url": item.get("url") or item.get("link") or "",
        "site": item.get("site") or item.get("publisher") or "",
        "published": item.get("publishedDate") or item.get("date") or "",
        "text": item.get("text") or "",
        "source": source,
    }


async def pull_fmp_news(fmp: FMPClient, ticker: str,
                       limit: int = 10) -> list[dict]:
    """Pull /stock_news + /press-releases for one ticker. Returns merged list."""
    async def _safe(coro):
        try:
            return await coro
        except FMPError as e:
            log.warning("FMP news for %s failed: %s", ticker, e)
            return []
    news_task = asyncio.create_task(_safe(fmp.stock_news(ticker, limit=limit)))
    pr_task = asyncio.create_task(_safe(fmp.press_releases(ticker, limit=limit)))
    news = await news_task
    pr = await pr_task
    out = [_normalize(n, "fmp_news") for n in (news or [])]
    out.extend(_normalize(p, "fmp_pr") for p in (pr or []))
    return out


async def pull_many(fmp: FMPClient, tickers: list[str],
                    limit: int = 10) -> dict[str, list[dict]]:
    """Pull news for many tickers concurrently. Returns {ticker: [items]}."""
    tasks = {t: asyncio.create_task(pull_fmp_news(fmp, t, limit)) for t in tickers}
    return {t: await tasks[t] for t in tickers}
