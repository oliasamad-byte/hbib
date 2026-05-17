"""
S5 - "Reversal Sprint, runner mode": same entry as S4 but no fixed target,
trail off SMA(5), extend max hold to 10 bars. Designed for live-monitored
trading where the user handles risk intraday.

Compared against S4 (the capped 5%-target version) so the runner-mode
trade-off (more profit per winner vs. larger gives-back) is visible.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from compare_strategies import (
    Trade, DATA_ROOT, SMALLCAP_MAX_MED, MIN_DAILY_BARS,
    one_per_period, report, rsi,
)
from run_s4 import s4_reversal_sprint


def s5_runner(ticker: str, daily: pd.DataFrame) -> list[Trade]:
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
    sma5 = pd.Series(c).rolling(5).mean().to_numpy()
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
    MAX_HOLD = 10
    while i < n - 1:
        if not fire[i]:
            i += 1
            continue
        entry_px = c[i]
        # Trail: exit at first close below SMA(5). Max hold 10 bars.
        exit_j = min(i + MAX_HOLD, n - 1)
        for j in range(i + 1, exit_j + 1):
            if np.isfinite(sma5[j]) and c[j] < sma5[j]:
                exit_j = j
                break
        trades.append(Trade(
            ticker=ticker,
            entry_date=dates[i],
            exit_date=dates[exit_j],
            entry=entry_px,
            exit=c[exit_j],
            bars_held=exit_j - i,
            score=-rsi2[i],
            ret=c[exit_j] / entry_px - 1.0,
        ))
        i = exit_j + 1
    return trades


def main() -> None:
    csvs = sorted(p for p in DATA_ROOT.glob("*/*.csv"))
    print(f"Found {len(csvs)} CSVs", file=sys.stderr)

    s4_all: list[Trade] = []
    s5_all: list[Trade] = []
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
        s4_all.extend(s4_reversal_sprint(p.stem, daily))
        s5_all.extend(s5_runner(p.stem, daily))
        if i % 2000 == 0:
            print(f"  [{i}/{len(csvs)}] loaded={n_loaded} small={n_small} "
                  f"s4={len(s4_all)} s5={len(s5_all)} ({time.monotonic()-t0:.0f}s)",
                  file=sys.stderr)

    print(f"\nLoaded {n_loaded}, small-cap subset {n_small}", file=sys.stderr)
    print(f"Raw trades  s4={len(s4_all)}  s5={len(s5_all)}", file=sys.stderr)

    s4_pick = one_per_period(s4_all, best="max")
    s5_pick = one_per_period(s5_all, best="max")

    report(s4_pick, "S4 REVERSAL SPRINT (target 5%, stop low, 5d)", bars_per_year=252)
    report(s5_pick, "S5 RUNNER MODE  (trail SMA5, no target, 10d)", bars_per_year=252)


if __name__ == "__main__":
    main()
