"""FMP earnings calendar pull (once per session). Caches to SQLite."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Iterable

from . import cache
from .utils.fmp_client import FMPClient, FMPError

log = logging.getLogger(__name__)


def _normalize(row: dict) -> dict | None:
    sym = (row.get("symbol") or "").upper()
    er_date = row.get("date")
    if not sym or not er_date:
        return None
    return {
        "ticker": sym,
        "er_date": er_date,
        "er_timing": row.get("time") or row.get("timing") or "",
    }


async def refresh_calendar(fmp: FMPClient, lookahead_days: int = 14) -> int:
    """Pull next N days of earnings, cache to SQLite. Returns rows saved."""
    today = date.today()
    end = today + timedelta(days=lookahead_days)
    try:
        rows = await fmp.earning_calendar(today.isoformat(), end.isoformat())
    except FMPError as e:
        log.warning("earnings calendar pull failed: %s", e)
        return 0
    normalized = [n for n in (_normalize(r) for r in (rows or [])) if n is not None]
    cache.save_earnings(normalized)
    log.info("earnings calendar: cached %d rows through %s", len(normalized), end)
    return len(normalized)


def days_until_er(ticker: str, today: date | None = None) -> int | None:
    """Days from `today` until next earnings date. None if no ER cached."""
    row = cache.get_earnings(ticker)
    if row is None:
        return None
    try:
        er = date.fromisoformat(row["er_date"][:10])
    except ValueError:
        return None
    today = today or date.today()
    delta = (er - today).days
    return delta if delta >= 0 else None


def er_dates_map(tickers: Iterable[str]) -> dict[str, str]:
    """Convenience: {ticker: er_date_iso} for the given tickers (if any)."""
    out = {}
    for t in tickers:
        row = cache.get_earnings(t)
        if row is not None:
            out[t] = row["er_date"]
    return out
