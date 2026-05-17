"""Daily ranker — cap-segmented, sort by DTS → breakout → catalyst → change_pct.

Per spec §8: two independent rankings (small / mid+L+M) on the same scored
universe. The Weekly ranker handles its own filter+sort separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ScoredTicker:
    ticker: str
    source: str                       # "Y" / "F"
    cap: str                          # small/mid/large/mega
    price: float
    change_pct: float
    market_cap: float
    dts_total: float
    dts_base: int
    dts_breakout: int
    dts_analyst: float
    wts_total: float                  # 0 if not in weekly track
    catalyst_score: int
    catalyst_category: str
    catalyst_evidence: str = ""
    breakdown: dict[str, Any] | None = None
    breakout_breakdown: dict[str, int] | None = None


def _key(t: ScoredTicker) -> tuple:
    return (-t.dts_total, -t.dts_breakout, -t.catalyst_score, -(t.change_pct or 0.0))


def rank_small_cap(scored: list[ScoredTicker], top_n: int = 20) -> list[ScoredTicker]:
    small = [t for t in scored if t.cap == "small"]
    small.sort(key=_key)
    return small[:top_n]


def rank_mid_large_mega(scored: list[ScoredTicker], top_n: int = 20) -> list[ScoredTicker]:
    mlm = [t for t in scored if t.cap in {"mid", "large", "mega"}]
    mlm.sort(key=_key)
    return mlm[:top_n]


def rank_both(scored: list[ScoredTicker], top_n: int = 20) \
        -> tuple[list[ScoredTicker], list[ScoredTicker]]:
    return rank_small_cap(scored, top_n), rank_mid_large_mega(scored, top_n)
