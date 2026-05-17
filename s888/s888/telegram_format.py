"""Shared formatters for the three Telegram messages.

The three messages (daily small / daily mlm / weekly) share most
formatting. Each has its own header and footer; the entry-row formatters
differ slightly per spec §12.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .earnings_warning import EarningsTag, warning_for
from .ranker_daily import ScoredTicker
from .tech_score_daily import ScoreResult
from .tech_score_weekly import WeeklyScoreResult


# ---------- helpers ----------

def _signed_pct(v: float | None) -> str:
    if v is None:
        return "  ?"
    return f"{v:+.2f}%" if v >= 0 else f"{v:.2f}%"


def _cap_subtag(cap: str) -> str:
    return {"small": "[Small]", "mid": "[Mid]", "large": "[Large]",
            "mega": "[Mega]"}.get(cap, "")


def _priority_emojis(score: ScoreResult, weekly_match: bool = False) -> str:
    """Stack tier + flags for display: 🔥🚀⚡🏆👍 + 📆."""
    parts = [score.tier_emoji()]
    if score.breakout >= 6:
        parts.append("⚡")
    elif score.breakout >= 4:
        parts.append("🚀")
    if score.analyst >= 3.0:
        parts.append("🏆")
    elif score.analyst >= 2.0:
        parts.append("👍")
    if weekly_match:
        parts.append("📆")
    return "".join(parts)


# ---------- daily entry rows ----------

def daily_top_block(rank: int, t: ScoredTicker,
                    score: ScoreResult,
                    weekly_match: bool,
                    earn: EarningsTag,
                    cap_subtag: bool = False) -> list[str]:
    """4–7 line detail block for ranks 1–3."""
    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
    flags = _priority_emojis(score, weekly_match)
    cap = f"  {_cap_subtag(t.cap)}" if cap_subtag else ""
    lines = [
        f"{medal} #{rank}  {t.ticker}({t.source})  {_signed_pct(t.change_pct)}"
        f"{cap}  DTS {int(score.total)}/38  {flags}",
        f"    Catalyst {t.catalyst_score}: {t.catalyst_category}"
        + (f" — {t.catalyst_evidence[:80]}" if t.catalyst_evidence else ""),
        f"    BO {score.breakout}/7 · ORB+{score.breakout_breakdown.get('orb', 0)}"
        f" · PDH/PMH+{score.breakout_breakdown.get('pdh_pmh', 0)}"
        f" · High+{score.breakout_breakdown.get('high_breakout', 0)}",
        f"    Analysts (15d): AAS {score.analyst:.1f}"
        + (f" {score.tier_emoji()}" if score.analyst >= 1.0 else ""),
    ]
    if earn.tag():
        lines.append(f"    {earn.tag()}")
    return lines


def daily_compact(rank: int, t: ScoredTicker, score: ScoreResult,
                  weekly_match: bool, earn: EarningsTag) -> str:
    """One-line compact row for ranks 4..N."""
    flags = _priority_emojis(score, weekly_match)
    parts = [
        f" #{rank:>2}  {t.ticker}({t.source})  {_signed_pct(t.change_pct)}",
        f"DTS {int(score.total):>2}  {flags}",
        f"Cat {t.catalyst_score} {t.catalyst_category[:12]}",
        f"BO {score.breakout}/7",
        f"A {score.analyst:.1f}",
    ]
    if earn.short():
        parts.append(earn.short())
    return "  ".join(parts)


# ---------- daily messages ----------

def _ts_header(scan_idx: int | None, scan_total: int | None) -> str:
    ts = datetime.utcnow().strftime("%H:%M UTC")
    extra = f"  ·  Scan {scan_idx}/{scan_total}" if scan_idx and scan_total else ""
    return f"{ts}{extra}"


def format_daily_small(picks: list[ScoredTicker],
                       scores: dict[str, ScoreResult],
                       weekly_match: set[str],
                       universe_size: int,
                       added: list[str], dropped: list[str],
                       n_detailed: int = 3,
                       scan_idx: int | None = None,
                       scan_total: int | None = None) -> str:
    return _format_daily(picks, scores, weekly_match, universe_size,
                         added, dropped, n_detailed, scan_idx, scan_total,
                         header_emoji="📅", header_label="SMALL CAP",
                         show_cap_subtag=False)


def format_daily_mlm(picks: list[ScoredTicker],
                     scores: dict[str, ScoreResult],
                     weekly_match: set[str],
                     universe_size: int,
                     added: list[str], dropped: list[str],
                     n_detailed: int = 3,
                     scan_idx: int | None = None,
                     scan_total: int | None = None) -> str:
    return _format_daily(picks, scores, weekly_match, universe_size,
                         added, dropped, n_detailed, scan_idx, scan_total,
                         header_emoji="📅", header_label="MID/LARGE/MEGA",
                         show_cap_subtag=True)


def _format_daily(picks, scores, weekly_match, universe_size,
                  added, dropped, n_detailed, scan_idx, scan_total,
                  header_emoji, header_label, show_cap_subtag):
    if not picks:
        return f"{header_emoji} DAILY {header_label} RANK  |  {_ts_header(scan_idx, scan_total)}\n" \
               f"  (0 tickers qualified)"

    src_y = sum(1 for t in picks if t.source == "Y")
    src_f = len(picks) - src_y
    lines = [
        f"{header_emoji} DAILY {header_label} RANK  |  {_ts_header(scan_idx, scan_total)}",
        "═" * 50,
        f"Universe: {universe_size} tickers  ·  Source: {src_y} Y + {src_f} F",
        f"Top {len(picks)} below",
        "",
    ]
    for i, t in enumerate(picks[:n_detailed], 1):
        s = scores.get(t.ticker)
        if s is None:
            continue
        earn = warning_for(t.ticker)
        lines.extend(daily_top_block(i, t, s, t.ticker in weekly_match,
                                     earn, cap_subtag=show_cap_subtag))
        lines.append("")
    if len(picks) > n_detailed:
        lines.append("─" * 50)
        for i, t in enumerate(picks[n_detailed:], n_detailed + 1):
            s = scores.get(t.ticker)
            if s is None:
                continue
            earn = warning_for(t.ticker)
            lines.append(daily_compact(i, t, s, t.ticker in weekly_match, earn))
    lines.append("─" * 50)
    pri = [t.ticker for t in picks if (scores.get(t.ticker) and scores[t.ticker].breakout >= 6)]
    conf = [t.ticker for t in picks
            if (scores.get(t.ticker) and 4 <= scores[t.ticker].breakout < 6)]
    lines.append(f"⚡ HIGH PRIORITY (BO ≥ 6): {', '.join(pri) or '(none)'}")
    lines.append(f"🚀 Confirmed (BO 4–5):    {', '.join(conf) or '(none)'}")
    if added:
        lines.append(f"🆕 Added: {', '.join(added)}")
    if dropped:
        lines.append(f"👋 Dropped: {', '.join(dropped)}")
    lines.append("Source: (Y) Yahoo Finance · (F) FMP per-cap pulls")
    lines.append("═" * 50)
    return "\n".join(lines)


# ---------- weekly message ----------

def format_weekly(picks: list[ScoredTicker],
                  wts_scores: dict[str, WeeklyScoreResult],
                  daily_ranks: dict[str, int],   # ticker -> "M/L/M #N" or "Small #N"
                  added: list[str], dropped: list[str],
                  scan_idx: int | None = None,
                  scan_total: int | None = None) -> str:
    if not picks:
        return ""   # empty weekly → no message per spec §9.3

    lines = [
        f"📆 WEEKLY TRADE RANK  |  {_ts_header(scan_idx, scan_total)}",
        "═" * 50,
        f"Filter: Stage ∈ {{1,2,3}} AND catalyst ≥ N AND WTS ≥ M",
        f"Qualifying: {len(picks)} tickers",
        "",
    ]
    for i, t in enumerate(picks[:3], 1):
        w = wts_scores.get(t.ticker)
        if w is None:
            continue
        earn = warning_for(t.ticker)
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}[i]
        flags = w.tier_emoji() + (" 🚀" if w.breakout >= 4 else "") + \
                (" 🏆" if w.analyst >= 3.0 else "") + \
                (" 👍" if 2.0 <= w.analyst < 3.0 else "")
        lines.append(
            f"{medal} #{i}  {t.ticker}({t.source})  WTS {int(w.total)}/19  "
            f"{flags}  {w.stage_emoji()} Stage {w.stage}  {_cap_subtag(t.cap)}"
        )
        lines.append(f"    Catalyst {t.catalyst_score}: {t.catalyst_category}")
        lines.append(f"    BO {w.breakout}/6 · Analysts AAS {w.analyst:.1f}")
        dr = daily_ranks.get(t.ticker)
        if dr:
            lines.append(f"    Daily: {dr}")
        if earn.tag():
            lines.append(f"    {earn.tag()}")
        lines.append("")
    if len(picks) > 3:
        lines.append("─" * 50)
        for i, t in enumerate(picks[3:], 4):
            w = wts_scores.get(t.ticker)
            if w is None:
                continue
            earn = warning_for(t.ticker)
            lines.append(
                f" #{i:>2}  {t.ticker}({t.source})  WTS {int(w.total):>2}  "
                f"{w.tier_emoji()}  {w.stage_emoji()} Stg {w.stage}  "
                f"{_cap_subtag(t.cap)}  Cat {t.catalyst_score} {t.catalyst_category[:12]}  "
                f"BO {w.breakout}/6  A {w.analyst:.1f}  {earn.short()}"
            )
    lines.append("─" * 50)
    if added:
        lines.append(f"🆕 Added to weekly: {', '.join(added)}")
    if dropped:
        lines.append(f"👋 Dropped from weekly: {', '.join(dropped)}")
    by_cap = {}
    for t in picks:
        by_cap[t.cap] = by_cap.get(t.cap, 0) + 1
    cap_summary = " · ".join(f"{k.title()}: {v}" for k, v in by_cap.items())
    lines.append(f"Cap breakdown: {cap_summary}")
    lines.append("═" * 50)
    return "\n".join(lines)
