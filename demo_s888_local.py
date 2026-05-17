"""Demo: run S888's scoring + ranking + formatting pipeline against the
local /tmp/eod/ OHLC dataset (wumiq/us_stock_eod, daily bars 1962-2022).

What this exercises:
  ✅ universe build (top gainers on a chosen historical date)
  ✅ cap categorization (synthesized from price × avg_vol proxy)
  ✅ Weinstein Stage on weekly bars
  ✅ Daily breakout levels (PDH, 20d/52w/8w high)
  ✅ Daily-TF subset of DTS (RSI/CMF/ADX/EMA/Vol/OBV on daily)
  ✅ WTS scoring (mostly works — uses weekly + daily bars only)
  ✅ Both rankers (cap-segmented daily + weekly with Stage 4 block)
  ✅ Telegram formatters → printed to stdout

What this CANNOT exercise (needs live FMP/YF):
  ❌ intraday checks (1m/5m/15m/30m/1h) — score density ~12/38 instead of 38/38
  ❌ ORB/PMH breakout levels (need intraday)
  ❌ Catalyst score (no news source)  → defaulted to 3 (technical_only)
  ❌ AAS (no FMP grades)               → defaulted to 0
  ❌ Earnings warning                  → defaulted to no ER
  ❌ Telegram send                     → printed instead

Run: python demo_s888_local.py [--date YYYY-MM-DD] [--limit N]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date as Date
from pathlib import Path

# Make s888 importable when running from repo root
sys.path.insert(0, str(Path(__file__).with_name("s888")))

import numpy as np
import pandas as pd

from s888 import (
    breakout_levels, cap_categorizer, indicators, ranker_daily, ranker_weekly,
    state, tech_score_daily, tech_score_weekly, telegram_format,
)
from s888.catalyst import CatalystResult

DATA_ROOT = Path("/tmp/eod")


# ---------- universe from local data ----------

def load_universe_for_date(target: Date,
                           prescreen_min_change: float = 2.5,
                           min_price: float = 2.0,
                           min_avg_vol: int = 200_000,
                           limit: int = 100) -> list[dict]:
    """Build a universe of top gainers ending on target date from local CSVs.

    change_pct = (close[target] / close[prior_trading_day]) - 1
    """
    out = []
    csvs = sorted(DATA_ROOT.glob("*/*.csv"))
    target_ts = pd.Timestamp(target)
    print(f"scanning {len(csvs)} tickers for date {target}...", file=sys.stderr)
    t0 = time.monotonic()
    for i, p in enumerate(csvs, 1):
        if i % 1000 == 0:
            print(f"  [{i}/{len(csvs)}] {time.monotonic()-t0:.0f}s, "
                  f"qualifying so far: {len(out)}", file=sys.stderr)
        try:
            df = pd.read_csv(p, parse_dates=["Date"]).set_index("Date").sort_index()
        except Exception:
            continue
        if df.empty or "Close" not in df.columns:
            continue
        # Find target row + prior row
        if target_ts not in df.index:
            continue
        idx_pos = df.index.get_loc(target_ts)
        if idx_pos == 0:
            continue
        prior_close = float(df["Close"].iloc[idx_pos - 1])
        cur_close = float(df["Close"].iloc[idx_pos])
        if prior_close <= 0:
            continue
        chg_pct = (cur_close / prior_close - 1.0) * 100
        if chg_pct < prescreen_min_change:
            continue
        if cur_close < min_price:
            continue
        avg_vol = float(df["Volume"].iloc[max(0, idx_pos - 20):idx_pos].mean())
        if avg_vol < min_avg_vol:
            continue
        # Synthesize a market_cap proxy from price + avg_vol (NOT real mcap —
        # used only so cap_categorizer fires; live FMP gives true mcap)
        synth_mcap = cur_close * avg_vol * 30   # rough liquidity proxy
        out.append({
            "ticker": p.stem,
            "source": "L",  # "L" = local CSV
            "price": cur_close,
            "change_pct": chg_pct,
            "market_cap": synth_mcap,
            "avg_volume": avg_vol,
            "_idx": idx_pos,
            "_path": p,
        })
    out.sort(key=lambda r: r["change_pct"], reverse=True)
    return out[:limit]


# ---------- per-ticker scoring (daily-only flavor) ----------

def daily_bars_to_dict(df: pd.DataFrame, target_idx: int,
                       daily_lookback: int = 250) -> dict[str, pd.DataFrame]:
    """Return bars dict in S888's expected schema. Intraday TFs empty.
    Weekly derived from daily."""
    sub = df.iloc[max(0, target_idx - daily_lookback):target_idx + 1].rename(
        columns={"Open": "open", "High": "high", "Low": "low",
                 "Close": "close", "Volume": "volume"}
    )
    weekly = sub.resample("W-FRI").agg({"open": "first", "high": "max",
                                        "low": "min", "close": "last",
                                        "volume": "sum"}).dropna(subset=["close"])
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return {
        "1m": empty, "5m": empty, "15m": empty, "30m": empty, "1h": empty,
        "daily": sub[["open", "high", "low", "close", "volume"]],
        "weekly": weekly,
    }


def score_one(row: dict) -> ranker_daily.ScoredTicker | None:
    try:
        df = pd.read_csv(row["_path"], parse_dates=["Date"]).set_index("Date").sort_index()
    except Exception:
        return None
    bars = daily_bars_to_dict(df, row["_idx"])
    if bars["daily"].empty:
        return None
    price = float(bars["daily"]["close"].iloc[-1])
    levels = breakout_levels.all_levels(
        bars["daily"], bars["weekly"],
        bars_5m=bars["5m"], bars_1m=bars["1m"],
    )
    # AAS defaults to 0 (no FMP grades in this demo)
    dts = tech_score_daily.compute_dts(bars, price, levels, aas=0.0)
    wts = tech_score_weekly.compute_wts(bars, levels, aas=0.0)
    # Catalyst defaulted — no news in demo
    cat = CatalystResult(3, "technical_only", "")
    return ranker_daily.ScoredTicker(
        ticker=row["ticker"], source=row["source"], cap=row["cap"],
        price=price, change_pct=row["change_pct"],
        market_cap=row["market_cap"],
        dts_total=dts.total, dts_base=dts.base, dts_breakout=dts.breakout,
        dts_analyst=dts.analyst, wts_total=wts.total,
        catalyst_score=cat.score, catalyst_category=cat.category,
        catalyst_evidence=cat.evidence,
        breakdown=dts.breakdown, breakout_breakdown=dts.breakout_breakdown,
    ), dts, wts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2022-03-18",
                    help="historical 'today' (YYYY-MM-DD). Default picks "
                         "a known up-day late in the dataset.")
    ap.add_argument("--limit", type=int, default=80,
                    help="max universe size after gainer pre-screen")
    args = ap.parse_args()
    target = Date.fromisoformat(args.date)

    print(f"\n=== S888 LOCAL DEMO  ·  scan date {target} ===\n")
    universe = load_universe_for_date(target, limit=args.limit)
    universe = cap_categorizer.tag_cap_categories(universe)
    print(f"\nUniverse after pre-screen + cap tag: {len(universe)} tickers")
    by_cap = {}
    for r in universe:
        by_cap[r["cap"]] = by_cap.get(r["cap"], 0) + 1
    print(f"  by cap: {by_cap}")

    print("\nScoring (daily-TF only — intraday checks all 0 by design)...")
    scored = []
    dts_map = {}
    wts_map = {}
    stages = {}
    t0 = time.monotonic()
    for r in universe:
        result = score_one(r)
        if result is None:
            continue
        s, dts, wts = result
        scored.append(s)
        dts_map[s.ticker] = dts
        wts_map[s.ticker] = wts
        stages[s.ticker] = wts.stage
    print(f"  scored {len(scored)} tickers in {time.monotonic()-t0:.1f}s")

    # Rankings
    small, mlm = ranker_daily.rank_both(scored, top_n=10)
    weekly = ranker_weekly.rank_weekly(scored, stages, top_n=10)

    weekly_set = {t.ticker for t in weekly}
    daily_ranks = {t.ticker: f"Small #{i+1}" for i, t in enumerate(small)}
    daily_ranks.update({t.ticker: f"M/L/M #{i+1}" for i, t in enumerate(mlm)})

    # Reset state so the demo always shows everything as 🆕
    state.commit("daily_small", [])
    state.commit("daily_mlm", [])
    state.commit("weekly", [])
    s_added, s_dropped = state.diff("daily_small", [t.ticker for t in small])
    m_added, m_dropped = state.diff("daily_mlm",   [t.ticker for t in mlm])
    w_added, w_dropped = state.diff("weekly",      [t.ticker for t in weekly])

    print("\n" + "=" * 60)
    print("MESSAGE 1 — DAILY SMALL CAP")
    print("=" * 60)
    print(telegram_format.format_daily_small(
        small, dts_map, weekly_set, len(universe),
        s_added, s_dropped, n_detailed=3))

    print("\n" + "=" * 60)
    print("MESSAGE 2 — DAILY MID/LARGE/MEGA")
    print("=" * 60)
    print(telegram_format.format_daily_mlm(
        mlm, dts_map, weekly_set, len(universe),
        m_added, m_dropped, n_detailed=3))

    print("\n" + "=" * 60)
    print("MESSAGE 3 — WEEKLY (would skip if empty)")
    print("=" * 60)
    weekly_msg = telegram_format.format_weekly(
        weekly, wts_map, daily_ranks, w_added, w_dropped)
    print(weekly_msg if weekly_msg else "(no qualifying tickers — message skipped)")

    print("\n" + "=" * 60)
    print("DEMO NOTES")
    print("=" * 60)
    print(f"""
This is S888 running on local daily-only OHLC. Real S888 with FMP intraday
data would score much higher (DTS out of 38 here is capped at ~12 because
the 16 intraday-TF checks all return 0).

What you just saw exercised:
  ✓ universe build, pre-screen, cap categorization
  ✓ {len(scored)} tickers scored end-to-end
  ✓ Weinstein Stage on weekly bars (real)
  ✓ Daily breakout levels (PDH, 20d/52w/8w high — real)
  ✓ Daily-TF subset of DTS scoring (real)
  ✓ Cap-segmented daily ranker (real)
  ✓ Weekly ranker with Stage 4 block + WTS gate (real)
  ✓ All three Telegram formatters (real, printed to stdout)
  ✓ 🆕 / 👋 state diff machinery (real, reset for demo)

What was DEFAULTED (would be real with live FMP/YF):
  - Catalyst score: all = 3 (technical_only)
  - AAS: all = 0
  - Earnings warning: none triggered
  - Intraday TF checks: 0 / 16
  - ORB / PMH breakout points: 0 (no intraday bars)
""")


if __name__ == "__main__":
    main()
