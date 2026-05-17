"""Step 1 — Universe pull (YF primary + FMP per-cap), merge, dedupe, cap-tag.

YF wins on duplicates (source="Y"). FMP fills the rest (source="F").
Returns a list of dicts ready to feed downstream stages.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from .cap_categorizer import tag_cap_categories
from .config import CFG
from .utils.fmp_client import FMPClient
from .utils.yf_client import day_gainers

log = logging.getLogger(__name__)


def _normalize_fmp(rows: list[dict]) -> list[dict]:
    """Map FMP screener/gainers rows to the common shape."""
    out = []
    for r in rows or []:
        sym = (r.get("symbol") or "").upper()
        if not sym:
            continue
        out.append({
            "symbol": sym,
            "price": r.get("price"),
            "change_pct": r.get("changesPercentage"),
            "market_cap": r.get("marketCap"),
            "avg_volume": r.get("avgVolume") or r.get("volume"),
            "name": r.get("name") or r.get("companyName"),
        })
    return out


def _passes_prescreen(row: dict) -> bool:
    p = row.get("price")
    v = row.get("avg_volume")
    cp = row.get("change_pct")
    if p is None or p < CFG.min_price:
        return False
    if v is None or v < CFG.min_avg_volume:
        return False
    if cp is None or cp < CFG.min_intraday_change_pct:
        return False
    return True


async def build_universe(fmp: FMPClient | None = None) -> list[dict]:
    """Return deduped, cap-tagged, pre-screened universe (≤ UNIVERSE_MAX)."""
    own_client = fmp is None
    if own_client:
        fmp = FMPClient()
        await fmp.__aenter__()
    try:
        # Parallel pulls
        yf_task = asyncio.create_task(day_gainers(count=100))
        fmp_broad_task = asyncio.create_task(fmp.gainers())
        fmp_small_task = asyncio.create_task(fmp.screener(
            mcap_min=CFG.cap_small_min, mcap_max=CFG.cap_small_max,
            volume_more_than=CFG.min_avg_volume, limit=50))
        fmp_mid_task = asyncio.create_task(fmp.screener(
            mcap_min=CFG.cap_small_max, mcap_max=CFG.cap_mid_max,
            volume_more_than=CFG.min_avg_volume, limit=50))
        fmp_large_task = asyncio.create_task(fmp.screener(
            mcap_min=CFG.cap_mid_max, mcap_max=CFG.cap_large_max,
            volume_more_than=CFG.min_avg_volume, limit=50))
        fmp_mega_task = asyncio.create_task(fmp.screener(
            mcap_min=CFG.cap_large_max, mcap_max=None,
            volume_more_than=CFG.min_avg_volume, limit=30))

        yf_rows = await yf_task
        fmp_rows = (
            _normalize_fmp(await fmp_broad_task)
            + _normalize_fmp(await fmp_small_task)
            + _normalize_fmp(await fmp_mid_task)
            + _normalize_fmp(await fmp_large_task)
            + _normalize_fmp(await fmp_mega_task)
        )
    finally:
        if own_client:
            await fmp.__aexit__(None, None, None)

    # Merge with dedupe — YF wins
    combined: dict[str, dict] = {}
    for r in yf_rows:
        r["source"] = "Y"
        combined[r["symbol"]] = r
    for r in fmp_rows:
        if r["symbol"] not in combined:
            r["source"] = "F"
            combined[r["symbol"]] = r

    # Rename symbol -> ticker for downstream
    rows = []
    for sym, r in combined.items():
        r["ticker"] = sym
        rows.append(r)

    # Pre-screen
    rows = [r for r in rows if _passes_prescreen(r)]

    # Cap tag (drops "skip")
    rows = tag_cap_categories(rows)

    # Sort + cap to UNIVERSE_MAX, change_pct desc for deterministic ordering
    rows.sort(key=lambda r: r.get("change_pct") or 0.0, reverse=True)
    return rows[: CFG.universe_max]


async def _main_cli() -> None:
    """`python -m s888.universe` — print the universe to stdout."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    rows = await build_universe()
    print(f"\nUniverse: {len(rows)} tickers")
    print(f"  Small : {sum(1 for r in rows if r['cap']=='small')}")
    print(f"  Mid   : {sum(1 for r in rows if r['cap']=='mid')}")
    print(f"  Large : {sum(1 for r in rows if r['cap']=='large')}")
    print(f"  Mega  : {sum(1 for r in rows if r['cap']=='mega')}")
    print(f"  Source: {sum(1 for r in rows if r['source']=='Y')} Y "
          f"+ {sum(1 for r in rows if r['source']=='F')} F")
    print()
    print(f"{'#':>3} {'ticker':<8} {'src':>3} {'cap':>5} {'chg%':>7} "
          f"{'price':>9} {'mcap($B)':>10}")
    print("-" * 60)
    for i, r in enumerate(rows[:30], 1):
        mc = (r.get("market_cap") or 0) / 1e9
        print(f"{i:>3} {r['ticker']:<8} {r['source']:>3} {r['cap']:>5} "
              f"{(r.get('change_pct') or 0):>6.2f}% {r.get('price') or 0:>9.2f} "
              f"{mc:>9.2f}B")


if __name__ == "__main__":
    asyncio.run(_main_cli())
