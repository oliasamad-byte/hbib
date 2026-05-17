"""Merge FMP + YF news per ticker, dedupe by Jaccard similarity on title tokens."""

from __future__ import annotations

import re
from typing import Iterable

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an the and or of to in for on at by with from as is are be it that this".split())


def tokens(text: str) -> set[str]:
    return {w for w in _TOKEN_RE.findall(text.lower()) if w not in _STOP and len(w) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def dedupe(items: Iterable[dict], threshold: float = 0.7) -> list[dict]:
    """Greedy dedupe: keep first occurrence, drop any near-duplicate after.
    Source priority: fmp_news > fmp_pr > yf — sort input accordingly."""
    seen: list[tuple[set[str], dict]] = []
    out: list[dict] = []
    for it in items:
        toks = tokens(it.get("title", ""))
        if any(jaccard(toks, prev) >= threshold for prev, _ in seen):
            continue
        seen.append((toks, it))
        out.append(it)
    return out


def merge_per_ticker(fmp: dict[str, list[dict]],
                     yf: dict[str, list[dict]],
                     threshold: float = 0.7) -> dict[str, list[dict]]:
    """Returns {ticker: deduped_items}. FMP items sort before YF (priority)."""
    out: dict[str, list[dict]] = {}
    tickers = set(fmp) | set(yf)
    for t in tickers:
        # fmp_news first, then fmp_pr, then yf (each input already grouped)
        combined = (fmp.get(t, []) or []) + (yf.get(t, []) or [])
        # Stable: keep fmp_news above fmp_pr above yf
        priority = {"fmp_news": 0, "fmp_pr": 1, "yf": 2}
        combined.sort(key=lambda x: priority.get(x.get("source", ""), 9))
        out[t] = dedupe(combined, threshold=threshold)
    return out
