"""Tag tickers with cap category based on thresholds in CFG.

cap ∈ {small, mid, large, mega, skip}.
"""

from __future__ import annotations

from typing import Iterable

from .config import CFG


def cap_for(market_cap: float | None) -> str:
    if market_cap is None or market_cap <= 0:
        return "skip"
    if CFG.cap_small_min <= market_cap < CFG.cap_small_max:
        return "small"
    if CFG.cap_small_max <= market_cap < CFG.cap_mid_max:
        return "mid"
    if CFG.cap_mid_max <= market_cap < CFG.cap_large_max:
        return "large"
    if market_cap >= CFG.cap_large_max:
        return "mega"
    return "skip"


def tag_cap_categories(rows: Iterable[dict]) -> list[dict]:
    """Mutate each row to add `cap` field; drop rows with cap == 'skip'."""
    out = []
    for r in rows:
        r["cap"] = cap_for(r.get("market_cap"))
        if r["cap"] != "skip":
            out.append(r)
    return out
