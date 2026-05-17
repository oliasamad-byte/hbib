"""Score the user-supplied top-gainer list against S888 hard filters and
(where historical data exists) S888's daily-TF DTS/WTS scoring.

Input: hard-coded ticker list from the screenshot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).with_name("s888")))

from s888 import breakout_levels, indicators, tech_score_daily, tech_score_weekly

DATA_ROOT = Path("/tmp/eod")

# From the screenshot
GAINERS = [
    ("SATLW",  3.43,   30.92),
    ("HYLN",   4.62,   24.86),
    ("GETY",   0.8699, 21.16),
    ("JLHL",   23.26,  17.59),
    ("SG",     8.05,   16.84),
    ("NL",     7.50,   11.61),
    ("GENVR",  0.7105, 10.93),
    ("STRZ",   24.30,  10.81),
    ("CD",     8.30,   9.64),
    ("SPIR",   19.85,  8.83),
    ("SIDU",   3.96,   8.20),
    ("AEBI",   11.99,  7.53),
    ("FBIOP",  15.01,  7.06),
    ("WTI",    4.73,   6.29),
    ("OIO",    1.89,   6.18),
    ("GEMI",   5.58,   6.08),
    ("PNRG",   268.16, 5.84),
    ("ESOA",   18.43,  5.80),
    ("EGHT",   2.36,   5.36),
    ("XRX",    2.56,   5.35),
    ("DCBO",   17.23,  5.32),
]

# S888 hard pre-screens (from spec §3.4 + recommended loser-pattern filters)
MIN_PRICE = 2.00
MAX_GAP_EXTENDED = 15.0      # recommended "not chasing" filter (S888 enhancement)
MAX_GAP_FATAL    = 25.0      # parabolic — almost always fades same-day


def find_local(ticker: str) -> Path | None:
    """Find ticker file in local OHLC dataset (organized by first letter)."""
    p = DATA_ROOT / ticker[0].upper() / f"{ticker.upper()}.csv"
    return p if p.exists() else None


def historical_context(ticker: str) -> dict:
    """If ticker has historical bars (through 2022-03-25), compute the
    partial S888 metrics we can. Returns dict with whatever we can find."""
    p = find_local(ticker)
    if p is None:
        return {"data": "NONE"}
    try:
        df = pd.read_csv(p, parse_dates=["Date"]).set_index("Date").sort_index()
    except Exception:
        return {"data": "READ_ERROR"}
    if df.empty or len(df) < 50:
        return {"data": "TOO_SHORT", "n_bars": len(df)}

    sub = df.rename(columns={"Open":"open","High":"high","Low":"low",
                              "Close":"close","Volume":"volume"})
    weekly = sub.resample("W-FRI").agg({"open":"first","high":"max","low":"min",
                                         "close":"last","volume":"sum"}).dropna(subset=["close"])

    bars = {
        "1m": pd.DataFrame(), "5m": pd.DataFrame(),
        "15m": pd.DataFrame(), "30m": pd.DataFrame(),
        "1h": pd.DataFrame(), "daily": sub, "weekly": weekly,
    }
    levels = breakout_levels.all_levels(sub, weekly,
                                         bars_5m=None, bars_1m=None)
    last_price = float(sub["close"].iloc[-1])
    last_date = sub.index[-1].date().isoformat()
    dts = tech_score_daily.compute_dts(bars, last_price, levels, aas=0.0)
    wts = tech_score_weekly.compute_wts(bars, levels, aas=0.0)
    return {
        "data": "OK",
        "n_bars": len(df),
        "last_bar": last_date,
        "last_close": last_price,
        "dts_total": dts.total,
        "dts_base": dts.base,
        "dts_breakout": dts.breakout,
        "wts_total": wts.total,
        "stage": wts.stage,
        "high_20d": levels.get("high_20d"),
        "high_52w": levels.get("high_52w"),
    }


def filter_status(price: float, gap: float) -> tuple[str, str]:
    """Returns (verdict, reason). Verdicts: BLOCK / WATCH / OK."""
    if price < MIN_PRICE:
        return "BLOCK", f"price ${price:.2f} < ${MIN_PRICE} floor"
    if gap >= MAX_GAP_FATAL:
        return "BLOCK", f"gap +{gap:.1f}% — parabolic, fades >70% of the time"
    if gap >= MAX_GAP_EXTENDED:
        return "WATCH", f"gap +{gap:.1f}% — extended, high reversal risk"
    return "OK", ""


def main() -> None:
    print(f"\n{'='*82}")
    print("  S888 SCREEN: TODAY'S USER-SUPPLIED TOP GAINERS")
    print(f"{'='*82}\n")

    print(f"{'#':>3} {'TICKER':<7} {'PRICE':>8} {'GAP%':>7}  {'STATUS':<7} "
          f"{'REASON / S888 NOTES':<60}")
    print("-" * 82)

    rows = []
    for i, (ticker, price, gap) in enumerate(GAINERS, 1):
        verdict, reason = filter_status(price, gap)
        ctx = historical_context(ticker)
        # Compose notes
        notes_parts = [reason] if reason else []
        if ctx["data"] == "NONE":
            notes_parts.append("no historical data (newer than 2022 dataset)")
        elif ctx["data"] == "OK":
            stage = ctx["stage"]
            stage_emoji = {1: "🔵basing", 2: "🟢uptrend",
                            3: "🟡topping", 4: "🔴downtrend"}.get(stage, "?")
            notes_parts.append(
                f"hist({ctx['last_bar']}): Stage {stage_emoji}, "
                f"WTS {ctx['wts_total']:.0f}/19, DTS {ctx['dts_total']:.0f}/38"
            )
        else:
            notes_parts.append(f"data: {ctx['data']}")

        rows.append({
            "ticker": ticker, "price": price, "gap": gap,
            "verdict": verdict, "notes": " · ".join(notes_parts),
            "ctx": ctx,
        })

        print(f"{i:>3} {ticker:<7} {price:>8.2f} {gap:>+6.2f}%  {verdict:<7} "
              f"{' · '.join(notes_parts)[:60]}")

    # Summary buckets
    block = [r for r in rows if r["verdict"] == "BLOCK"]
    watch = [r for r in rows if r["verdict"] == "WATCH"]
    ok = [r for r in rows if r["verdict"] == "OK"]

    print(f"\n{'='*82}")
    print(f"  SUMMARY")
    print(f"{'='*82}\n")
    print(f"  ❌ BLOCK  ({len(block)} names): "
          f"{', '.join(r['ticker'] for r in block)}")
    print(f"  ⚠️ WATCH  ({len(watch)} names): "
          f"{', '.join(r['ticker'] for r in watch)}")
    print(f"  ✅ OK     ({len(ok)} names): "
          f"{', '.join(r['ticker'] for r in ok)}")

    print(f"\n{'='*82}")
    print(f"  TOP S888 PICKS (from OK bucket, ranked by available S888 data)")
    print(f"{'='*82}\n")
    # Rank OK rows by (1) has historical data, (2) Stage 2 > 1 > 3 > 4,
    # (3) higher WTS, (4) lower gap
    def rank_key(r):
        c = r["ctx"]
        has = 0 if c["data"] == "OK" else 1
        stage = c.get("stage", 99)
        stage_pri = {2: 0, 1: 1, 3: 2, 4: 3}.get(stage, 4)
        wts = -c.get("wts_total", 0)
        gap = r["gap"]
        return (has, stage_pri, wts, gap)

    ok_sorted = sorted(ok, key=rank_key)
    for i, r in enumerate(ok_sorted, 1):
        c = r["ctx"]
        if c["data"] == "OK":
            stage_emoji = {1: "🔵", 2: "🟢", 3: "🟡", 4: "🔴"}.get(c["stage"], "?")
            print(f"  #{i:>2}  {r['ticker']:<6}  ${r['price']:>7.2f}  +{r['gap']:>5.2f}%  "
                  f"Stage {stage_emoji}  WTS {c['wts_total']:.0f}/19  "
                  f"DTS {c['dts_total']:.0f}/38   "
                  f"(historical through {c['last_bar']})")
        else:
            print(f"  #{i:>2}  {r['ticker']:<6}  ${r['price']:>7.2f}  +{r['gap']:>5.2f}%  "
                  f"  NO HIST  (post-2022 IPO/listing — score blind)")


if __name__ == "__main__":
    main()
