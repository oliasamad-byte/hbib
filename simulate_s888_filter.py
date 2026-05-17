"""Simulate the user's daily workflow + S888-style filters on local OHLC.

User's live workflow:
  - At market open, buy ~10 stocks that gapped up overnight (top gainers)
  - Sell by midday (~4 hours later)
  - Reports: 60% win rate, 2% net daily

This simulation approximates that with daily-only bars:
  - For each trading day D, identify stocks where (D.open / D-1.close - 1) >= GAP_PCT
  - "Trade outcome" = (D.close / D.open - 1)  -> open-to-close intraday return
  - This proxies the user's "buy at open, sell ~4h later" hold

Filters applied progressively (each row in the table adds a filter):
  - Baseline    : just gap >= 5% + price >= $2 + avg_vol >= 200k
  - +Above200d  : also close > SMA(200)  (S888 trend filter)
  - +Above50d   : also close > SMA(50)
  - +NewHigh    : also close > 20-day high (breakout)
  - +NotExtended: gap <= 15% (avoid chasing the very biggest movers — fade risk)
  - +AllFilters : everything above stacked

For each filter level, report:
  - Trades per day (avg)
  - Win rate (proxy for the user's live win rate)
  - Mean / median intraday return
  - Expected daily P&L given they buy 10 (or fewer if fewer pass)

Goal: quantify "if S888 filters out the bad gainers, how much does the
win rate move from baseline toward 70%+?"
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

DATA_ROOT = Path("/tmp/eod")
MIN_BARS = 260
MIN_PRICE = 2.0
MIN_AVG_VOL = 200_000
GAP_PCT = 5.0           # only consider stocks that gapped >=5% overnight
TOP_N_PER_DAY = 10      # user buys top 10 per day


def load_one(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path, parse_dates=["Date"]).set_index("Date").sort_index()
    except Exception:
        return None
    if df.empty or len(df) < MIN_BARS or "Close" not in df.columns:
        return None
    if "Open" not in df.columns:
        return None
    return df


def precompute(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Precompute everything we need per-day."""
    o = df["Open"].astype(float).to_numpy()
    h = df["High"].astype(float).to_numpy()
    l = df["Low"].astype(float).to_numpy()
    c = df["Close"].astype(float).to_numpy()
    v = df["Volume"].astype(float).to_numpy()

    prev_close = np.concatenate([[np.nan], c[:-1]])
    overnight_gap = (o / prev_close - 1.0) * 100

    sma200 = pd.Series(c).rolling(200).mean().to_numpy()
    sma50 = pd.Series(c).rolling(50).mean().to_numpy()
    high20 = pd.Series(c).rolling(20).max().to_numpy()
    avg_vol = pd.Series(v).rolling(20).mean().to_numpy()

    intraday_ret = (c / o - 1.0) * 100  # open-to-close %

    return {
        "open": o, "close": c, "vol": v,
        "prev_close": prev_close, "gap": overnight_gap,
        "sma200": sma200, "sma50": sma50,
        "high20": high20, "avg_vol": avg_vol,
        "intraday_ret": intraday_ret,
    }


FILTERS = {
    "Baseline":      lambda f, i: (f["gap"][i] >= GAP_PCT
                                    and f["open"][i] >= MIN_PRICE
                                    and (f["avg_vol"][i] or 0) >= MIN_AVG_VOL),
    "+Above200d":    lambda f, i: (f["gap"][i] >= GAP_PCT
                                    and f["open"][i] >= MIN_PRICE
                                    and (f["avg_vol"][i] or 0) >= MIN_AVG_VOL
                                    and np.isfinite(f["sma200"][i])
                                    and f["open"][i] > f["sma200"][i]),
    "+Above50d":     lambda f, i: (f["gap"][i] >= GAP_PCT
                                    and f["open"][i] >= MIN_PRICE
                                    and (f["avg_vol"][i] or 0) >= MIN_AVG_VOL
                                    and np.isfinite(f["sma200"][i])
                                    and f["open"][i] > f["sma200"][i]
                                    and np.isfinite(f["sma50"][i])
                                    and f["open"][i] > f["sma50"][i]),
    "+NewHigh":      lambda f, i: (f["gap"][i] >= GAP_PCT
                                    and f["open"][i] >= MIN_PRICE
                                    and (f["avg_vol"][i] or 0) >= MIN_AVG_VOL
                                    and np.isfinite(f["high20"][i-1] if i > 0 else np.nan)
                                    and f["open"][i] > f["high20"][i-1]),
    "+NotExtended":  lambda f, i: (5.0 <= f["gap"][i] <= 15.0
                                    and f["open"][i] >= MIN_PRICE
                                    and (f["avg_vol"][i] or 0) >= MIN_AVG_VOL),
    "S888AllStack":  lambda f, i: (5.0 <= f["gap"][i] <= 15.0
                                    and f["open"][i] >= MIN_PRICE
                                    and (f["avg_vol"][i] or 0) >= MIN_AVG_VOL
                                    and np.isfinite(f["sma200"][i])
                                    and f["open"][i] > f["sma200"][i]
                                    and np.isfinite(f["sma50"][i])
                                    and f["open"][i] > f["sma50"][i]
                                    and i > 0
                                    and np.isfinite(f["high20"][i-1])
                                    and f["open"][i] > f["high20"][i-1]),
}


def main() -> None:
    csvs = sorted(p for p in DATA_ROOT.glob("*/*.csv"))
    print(f"Loading {len(csvs)} CSVs...", file=sys.stderr)

    # per-day, per-filter: list of (ticker, intraday_ret, gap)
    by_day: dict[pd.Timestamp, dict[str, list]] = defaultdict(
        lambda: {fname: [] for fname in FILTERS}
    )
    n_loaded = 0
    t0 = time.monotonic()

    for i, p in enumerate(csvs, 1):
        df = load_one(p)
        if df is None:
            continue
        n_loaded += 1
        f = precompute(df)
        for j in range(200, len(df)):
            ret = f["intraday_ret"][j]
            if not np.isfinite(ret):
                continue
            d = df.index[j]
            for fname, pred in FILTERS.items():
                try:
                    if pred(f, j):
                        by_day[d][fname].append((p.stem, ret, f["gap"][j]))
                except (IndexError, TypeError):
                    pass
        if i % 2000 == 0:
            print(f"  [{i}/{len(csvs)}] loaded={n_loaded} days_covered={len(by_day)} "
                  f"({time.monotonic()-t0:.0f}s)", file=sys.stderr)

    print(f"\nLoaded {n_loaded} tickers across {len(by_day)} unique trading days",
          file=sys.stderr)

    # For each filter, simulate "buy top N by gap each day, take open-to-close"
    print(f"\n{'='*78}")
    print(f"  SIMULATED USER WORKFLOW (buy top {TOP_N_PER_DAY} gappers/day, "
          f"sell at close)")
    print(f"{'='*78}\n")
    print(f"{'Filter':<16}{'days':>8}{'avg/day':>10}{'win%':>9}"
          f"{'mean%':>10}{'med%':>10}{'expected $/day*':>18}")
    print("-" * 78)

    for fname in FILTERS:
        all_rets: list[float] = []
        days_with_picks = 0
        picks_per_day = []
        for d, picks in by_day.items():
            buckets = picks[fname]
            if not buckets:
                continue
            buckets.sort(key=lambda x: -x[2])  # sort by gap desc, take top N
            top = buckets[:TOP_N_PER_DAY]
            days_with_picks += 1
            picks_per_day.append(len(top))
            all_rets.extend([r for (_, r, _) in top])

        if not all_rets:
            print(f"{fname:<16}  no trades")
            continue
        rets = np.array(all_rets)
        wins = (rets > 0).mean() * 100
        avg_n = np.mean(picks_per_day)
        # "Expected $/day" assumes equal-weight $1000 per pick
        expected_per_pick = rets.mean() / 100 * 1000   # $ on $1000 position
        expected_per_day = expected_per_pick * avg_n
        print(f"{fname:<16}{days_with_picks:>8}{avg_n:>10.1f}"
              f"{wins:>8.1f}%{rets.mean():>+9.2f}%{np.median(rets):>+9.2f}%"
              f"{expected_per_day:>17.2f}")

    print(f"\n* Expected $/day = (mean return per trade) × (avg picks per day) × $1000/pick")
    print(f"  (equal-weight, ignores cost — subtract ~$2/trade for spread+commission)")


if __name__ == "__main__":
    main()
