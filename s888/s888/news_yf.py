"""yfinance per-ticker news puller, normalized to common shape."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from .utils.yf_client import news_for

log = logging.getLogger(__name__)


def _normalize(item: dict) -> dict:
    # yfinance returns variable shapes across versions; handle both.
    payload = item.get("content") or item
    title = payload.get("title") or item.get("title") or ""
    publisher = payload.get("provider", {}).get("displayName") if isinstance(
        payload.get("provider"), dict) else (
        payload.get("publisher") or item.get("publisher") or "")
    pub_ts = payload.get("pubDate") or payload.get("providerPublishTime") or 0
    if isinstance(pub_ts, (int, float)) and pub_ts > 0:
        try:
            published = datetime.utcfromtimestamp(pub_ts).isoformat()
        except (OSError, ValueError):
            published = ""
    else:
        published = str(pub_ts) if pub_ts else ""
    link_obj = payload.get("canonicalUrl") or {}
    url = (link_obj.get("url") if isinstance(link_obj, dict) else None) \
          or payload.get("link") or item.get("link") or ""
    # tickers field
    rel = item.get("relatedTickers") or payload.get("finance", {}).get("stockTickers", [])
    ticker = (rel[0] if rel else "").upper() if isinstance(rel, list) else ""
    return {
        "ticker": ticker,
        "title": (title or "").strip(),
        "url": url,
        "site": publisher,
        "published": published,
        "text": payload.get("summary", "") or "",
        "source": "yf",
    }


async def pull_yf_news(ticker: str, limit: int = 10) -> list[dict]:
    items = await news_for(ticker, limit=limit)
    return [_normalize(i) for i in (items or [])]


async def pull_many(tickers: list[str], limit: int = 10) -> dict[str, list[dict]]:
    tasks = {t: asyncio.create_task(pull_yf_news(t, limit)) for t in tickers}
    return {t: await tasks[t] for t in tickers}
