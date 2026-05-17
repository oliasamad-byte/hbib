"""
S4 - "Reversal Sprint": 1-5 day swing on confirmed oversold bounce.

Synthesized from the user's TrendSpider scanners (Vortex 1/2/3, Vortex Bearish):
the common idea is oversold + reversal confirmation + volume.

Entry (all true on the same daily bar, "signal day"):
  RSI(2) < 10                                # oversold bottom
  Close > Open * 1.02                        # real green reversal bar
  Volume >= 1.5 * SMA(Volume, 20)            # volume confirmation
  Close > SMA(Close, 200)                    # uptrend filter

Exit (whichever first, scanning bars after entry):
  intraday High >= Entry * 1.05    -> exit at Entry*1.05  (5% target)
  Close < Entry-day Low            -> exit at Close       (stop)
  after 5 trading days             -> exit at Close       (time stop)

Compares to S2 (RSI-2) and S3 (52w-high momentum) from compare_strategies.py.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from compare_strategies import (
    Trade, DATA_ROOT, SMALLCAP_MAX_MED, MIN_DAILY_BARS,
    s2_rsi2, s3_momentum, one_per_period, report, rsi,
)


def s4_reversal_sprint(ticker: str, daily: pd.DataFrame) -> list[Trade]:
    if len(daily) < 260:
        return []
    o = daily["Open"].astype(float).to_numpy()
    h = daily["High"].astype(float).to_numpy()
    l = daily["Low"].astype(float).to_numpy()
    c = daily["Close"].astype(float).to_numpy()
    v = daily["Volume"].astype(float).to_numpy()
    dates = daily.index

    avg_v = pd.Series(v).rolling(20).mean().to_numpy()
    sma200 = pd.Series(c).rolling(200).mean().to_numpy()
    rsi2 = rsi(c, 2)

    with np.errstate(invalid="ignore", divide="ignore"):
        green_pct = (c - o) / o
        rel_v = v / avg_v

    fire = (
        (rsi2 < 10)
        & (green_pct >= 0.02)
        & (rel_v >= 1.5)
        & (c > sma200)
        & np.isfinite(sma200) & np.isfinite(avg_v)
    )

    trades: list[Trade] = []
    i = 200
    n = len(c)
    while i < n - 1:
        if not fire[i]:
            i += 1
            continue
        entry_px = c[i]
        entry_low = l[i]
        target = entry_px * 1.05
        exit_px = None
        exit_j = None
        # scan up to 5 bars forward (j = i+1 .. i+5)
        for j in range(i + 1, min(i + 6, n)):
            if h[j] >= target:                  # target hit
                exit_px = target
                exit_j = j
                break
            if c[j] < entry_low:                # stop hit on close
                exit_px = c[j]
                exit_j = j
                break
        if exit_px is None:
            exit_j = min(i + 5, n - 1)
            exit_px = c[exit_j]
        trades.append(Trade(
            ticker=ticker,
            entry_date=dates[i],
            exit_date=dates[exit_j],
            entry=entry_px,
            exit=exit_px,
            bars_held=exit_j - i,
            score=-rsi2[i],                     # lower RSI = more oversold = higher score
            ret=exit_px / entry_px - 1.0,
        ))
        i = exit_j + 1                          # don't re-enter same ticker until trade closes
    return trades


def main() -> None:
    csvs = sorted(p for p in DATA_ROOT.glob("*/*.csv"))
    print(f"Found {len(csvs)} CSVs", file=sys.stderr)

    s2_all: list[Trade] = []
    s3_all: list[Trade] = []
    s4_all: list[Trade] = []
    n_loaded = n_small = 0
    t0 = time.monotonic()

    for i, p in enumerate(csvs, 1):
        try:
            daily = pd.read_csv(p, parse_dates=["Date"]).set_index("Date").sort_index()
        except Exception:
            continue
        if daily.empty or "Close" not in daily.columns or len(daily) < MIN_DAILY_BARS:
            continue
        weekly = daily.resample("W-FRI").agg({"Open":"first","High":"max","Low":"min",
                                              "Close":"last","Volume":"sum"}).dropna(subset=["Close"])
        if len(weekly) < 60:
            continue
        n_loaded += 1
        if weekly["Close"].median() > SMALLCAP_MAX_MED:
            continue
        n_small += 1
        s2_all.extend(s2_rsi2(p.stem, daily))
        s3_all.extend(s3_momentum(p.stem, weekly))
        s4_all.extend(s4_reversal_sprint(p.stem, daily))
        if i % 2000 == 0:
            print(f"  [{i}/{len(csvs)}] loaded={n_loaded} small={n_small} "
                  f"s2={len(s2_all)} s3={len(s3_all)} s4={len(s4_all)} "
                  f"({time.monotonic()-t0:.0f}s)", file=sys.stderr)

    print(f"\nLoaded {n_loaded}, small-cap subset {n_small}", file=sys.stderr)
    print(f"Raw trades  s2={len(s2_all)}  s3={len(s3_all)}  s4={len(s4_all)}", file=sys.stderr)

    s2_pick = one_per_period(s2_all, best="max")
    s3_pick = one_per_period(s3_all, best="max")
    s4_pick = one_per_period(s4_all, best="max")

    report(s2_pick, "S2 RSI-2 MEAN-REV (1/day, lowest RSI)",         bars_per_year=252)
    report(s3_pick, "S3 52W-HIGH MOMENTUM (1/week, closest to high)", bars_per_year=52)
    report(s4_pick, "S4 REVERSAL SPRINT (1/day, lowest RSI)",         bars_per_year=252)


if __name__ == "__main__":
    main()
