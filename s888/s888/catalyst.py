"""Catalyst classifier (1–10). Keyword-driven against merged news.

Returns (score, category, headline_evidence) for the BEST item per ticker.
Categories per spec §4.2 (high to low):
  10 earnings_beat_HV    9 earnings_beat / regulatory_win / contract_award
  8 m_and_a_target / post_er_drift
  7 analyst_upgrade
  6 pre_er_window
  5 sector_sympathy
  3 technical_only
  1 pump_unclear
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

# Keyword sets — lowercase, matched as whole words.
_KW = {
    "earnings_beat":   re.compile(r"\b(beats|tops|exceeds|crushes|smashes)\b", re.I),
    "earnings_miss":   re.compile(r"\b(misses|disappoints|fall(s|en) short)\b", re.I),
    "regulatory_win":  re.compile(r"\b(fda approves|fda approval|court ruled|"
                                  r"wins\s+(case|lawsuit|approval|clearance)|"
                                  r"granted\s+(approval|patent))\b", re.I),
    "contract":        re.compile(r"\b(contract|deal|partnership|awarded|"
                                  r"selected by|signs\s+\w+\s+agreement)\b", re.I),
    "m_and_a":         re.compile(r"\b(to acquire|acquires?|merger|merges?|"
                                  r"buyout|takeover|in talks to buy|"
                                  r"announces (acquisition|merger))\b", re.I),
    "analyst_up":      re.compile(r"\b(upgrades?|raises (price target|pt)|"
                                  r"strong buy|reiterates buy|"
                                  r"initiated at (buy|outperform|overweight))\b", re.I),
    "pump":            re.compile(r"\b(soars?|rockets?|skyrocket|explodes?|"
                                  r"could (be|reach)|next big|"
                                  r"penny stock|alert)\b", re.I),
    "sector":          re.compile(r"\b(sector|industry|peers|group)\b", re.I),
}

# Low-tier publishers — anything from these alone caps catalyst at 1.
_LOW_TIER_SITES = frozenset({
    "investorshangout.com", "stocktwits.com", "promotionstocksecrets.com",
    "stockstotrade.com", "investorsobserver.com",
})


@dataclass(frozen=True)
class CatalystResult:
    score: int
    category: str
    evidence: str = ""

    def short_label(self) -> str:
        """Short token used in Telegram one-liners — first word of category."""
        return self.category.split("_")[0] if self.category else "none"


def _has_er_in_window(ticker: str, er_dates: dict[str, str] | None,
                      lookback_days: int = 5,
                      lookahead_days: int = 5,
                      today: date | None = None) -> tuple[bool, bool]:
    """Returns (had_recent_er, has_pre_er_window)."""
    today = today or date.today()
    er_str = (er_dates or {}).get(ticker)
    if not er_str:
        return False, False
    try:
        er = datetime.fromisoformat(er_str[:10]).date()
    except ValueError:
        return False, False
    delta_days = (er - today).days
    had_recent_er = -lookback_days <= delta_days <= 0
    has_pre_er = 0 < delta_days <= lookahead_days
    return had_recent_er, has_pre_er


def _classify_one(item: dict) -> CatalystResult | None:
    title = item.get("title", "")
    site = (item.get("site") or "").lower()
    if not title:
        return None
    if _KW["earnings_beat"].search(title):
        return CatalystResult(9, "earnings_beat", title)
    if _KW["regulatory_win"].search(title):
        return CatalystResult(9, "regulatory_win", title)
    # m_and_a checked before contract: "to acquire ... deal" is M&A, not a contract
    if _KW["m_and_a"].search(title):
        return CatalystResult(8, "m_and_a_target", title)
    if _KW["contract"].search(title):
        return CatalystResult(9, "contract_award", title)
    if _KW["analyst_up"].search(title):
        return CatalystResult(7, "analyst_upgrade", title)
    if _KW["sector"].search(title):
        return CatalystResult(5, "sector_sympathy", title)
    if _KW["pump"].search(title) or site in _LOW_TIER_SITES:
        return CatalystResult(1, "pump_unclear", title)
    return None


def classify(ticker: str,
             items: Iterable[dict],
             er_dates: dict[str, str] | None = None,
             sector_etf_change_pct: float | None = None,
             today: date | None = None) -> CatalystResult:
    """Return BEST catalyst for one ticker. Sector sympathy is upgraded
    when sector_etf_change_pct > 2.0. Pre/post-ER windows checked from
    er_dates map."""
    best: CatalystResult | None = None
    for it in items:
        r = _classify_one(it)
        if r is None:
            continue
        if best is None or r.score > best.score:
            best = r

    had_recent, has_pre = _has_er_in_window(ticker, er_dates, today=today)

    # Earnings beat detected within 5d → upgrade to HV (10)
    if best and best.category == "earnings_beat" and had_recent:
        # We can't check vol here without bars — leave as 9 unless caller
        # later upgrades via has_post_er_high_vol() helper.
        best = CatalystResult(9, "earnings_beat", best.evidence)

    # Post-ER drift if had recent ER and no other news
    if had_recent and (best is None or best.score < 8):
        if best is None or best.score < 8:
            best = CatalystResult(8, "post_er_drift",
                                  best.evidence if best else "")

    # Pre-ER window if no other news
    if has_pre and best is None:
        best = CatalystResult(6, "pre_er_window", "")

    # Sector sympathy upgrade
    if best is None and sector_etf_change_pct is not None \
            and sector_etf_change_pct > 2.0:
        best = CatalystResult(5, "sector_sympathy", "sector ETF up >2%")

    # Fallback
    if best is None:
        best = CatalystResult(3, "technical_only", "")

    return best


def upgrade_to_high_vol(result: CatalystResult, vol_ratio: float) -> CatalystResult:
    """Caller invokes after computing post-ER 1-day volume ratio. If ≥ 2.0
    and category is earnings_beat → upgrade to 10 (earnings_beat_HV)."""
    if result.category == "earnings_beat" and vol_ratio >= 2.0:
        return CatalystResult(10, "earnings_beat_HV", result.evidence)
    return result
