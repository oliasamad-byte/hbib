"""Earnings warning tag for a ticker per spec §10."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import earnings_calendar
from .config import CFG


@dataclass
class EarningsTag:
    days: int | None             # None if no upcoming ER
    timing: str = ""             # BMO / AMC / DMH
    er_date: str = ""

    def tag(self) -> str:
        """Return the spec-§10 emoji string, or empty string."""
        if self.days is None:
            return ""
        if self.days <= 1:
            return f"⚠️⚠️⚠️ ER {'TOMORROW' if self.days == 1 else 'TODAY'}"
        if self.days <= CFG.earnings_urgent_days:
            return f"⚠️⚠️ ER in {self.days}d"
        if self.days <= CFG.earnings_warn_days:
            return f"⚠️ ER in {self.days}d"
        return ""

    def short(self) -> str:
        """Compact form for one-line entries: '⚠️ ER 5d' or ''."""
        full = self.tag()
        if not full:
            return ""
        return full.replace(" in ", " ").replace(" days", "d")


def warning_for(ticker: str, today: date | None = None) -> EarningsTag:
    today = today or date.today()
    days = earnings_calendar.days_until_er(ticker, today=today)
    if days is None:
        return EarningsTag(days=None)
    from . import cache
    row = cache.get_earnings(ticker)
    timing = row["er_timing"] if row else ""
    er_date = row["er_date"] if row else ""
    return EarningsTag(days=days, timing=timing or "", er_date=er_date or "")
