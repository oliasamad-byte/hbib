"""Analyst Activity Score (AAS, 0–3) — bullish actions only (spec §5.5).

Pulled once per session per ticker; cached in SQLite for 24h.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from . import cache
from .config import CFG
from .utils.fmp_client import FMPClient, FMPError

log = logging.getLogger(__name__)

BULLISH_RATINGS = frozenset({
    "strong buy", "buy", "outperform", "overweight",
    "market outperform", "sector outperform", "positive",
    "accumulate", "conviction buy", "top pick",
})


@dataclass
class AnalystResult:
    score: float = 0.0
    bull_counts: dict[str, int] = field(default_factory=lambda: {
        "upgrades": 0, "initiations_buy": 0, "reiterations_buy": 0, "pt_raises": 0,
    })
    ignored_counts: dict[str, int] = field(default_factory=lambda: {
        "downgrades": 0, "bearish_initiations": 0, "neutrals": 0,
    })
    raw_actions: list[dict] = field(default_factory=list)

    def tier_emoji(self) -> str:
        if self.score >= 3.0:
            return "🏆"
        if self.score >= 2.0:
            return "👍"
        if self.score >= 1.0:
            return "✓"
        return ""


def _is_bullish_grade(grade: str) -> bool:
    return (grade or "").strip().lower() in BULLISH_RATINGS


def compute_aas(raw_actions: list[dict],
                lookback_days: int | None = None,
                today: date | None = None) -> AnalystResult:
    """Compute AAS from a list of FMP grade actions. Bullish-only.
    Caps score at 3."""
    today = today or date.today()
    lookback = lookback_days or CFG.analyst_lookback_days
    cutoff = today - timedelta(days=lookback)

    result = AnalystResult(raw_actions=raw_actions or [])
    score = 0.0
    for a in raw_actions or []:
        date_str = a.get("publishedDate") or a.get("date") or ""
        try:
            d = datetime.fromisoformat(date_str[:10]).date()
        except (ValueError, TypeError):
            continue
        if d < cutoff:
            continue
        action = (a.get("action") or "").strip().lower()
        new_grade = a.get("newGrade") or a.get("newGrade", "")

        if action == "upgrade":
            result.bull_counts["upgrades"] += 1
            score += 1.0
        elif action == "initiation" or action == "init":
            if _is_bullish_grade(new_grade):
                result.bull_counts["initiations_buy"] += 1
                score += 1.0
            elif new_grade:
                grade_l = new_grade.strip().lower()
                if grade_l in {"sell", "strong sell", "underperform",
                               "underweight", "reduce", "negative"}:
                    result.ignored_counts["bearish_initiations"] += 1
                else:
                    result.ignored_counts["neutrals"] += 1
        elif action in {"maintain", "reiterate", "reiterated"}:
            if _is_bullish_grade(new_grade):
                result.bull_counts["reiterations_buy"] += 1
                score += 0.5
            else:
                result.ignored_counts["neutrals"] += 1
        elif action == "downgrade":
            result.ignored_counts["downgrades"] += 1
            # ignored, not penalized
        else:
            # unknown action — skip
            pass

    result.score = min(3.0, score)
    return result


async def fetch_aas(fmp: FMPClient, ticker: str,
                    today: date | None = None) -> AnalystResult:
    """Cached fetch + compute. Returns AnalystResult, never raises."""
    today = today or date.today()
    cached = cache.get_analyst(ticker, today.isoformat())
    if cached is not None:
        import json
        raw = json.loads(cached["raw_actions"]) if cached["raw_actions"] else []
        bull = json.loads(cached["bullish_counts"]) if cached["bullish_counts"] else {}
        ignored = json.loads(cached["ignored_counts"]) if cached["ignored_counts"] else {}
        return AnalystResult(
            score=cached["aas_score"],
            bull_counts={**AnalystResult().bull_counts, **bull},
            ignored_counts={**AnalystResult().ignored_counts, **ignored},
            raw_actions=raw,
        )
    try:
        raw = await fmp.grades(ticker)
    except FMPError as e:
        log.warning("FMP grades for %s failed: %s", ticker, e)
        raw = []
    result = compute_aas(raw or [], today=today)
    cache.save_analyst(ticker, today.isoformat(),
                       raw=raw or [], aas=result.score,
                       bull=result.bull_counts,
                       ignored=result.ignored_counts)
    return result
