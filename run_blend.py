"""S2 + S3 blended portfolio backtest with realistic frictions.

Builds on compare_strategies.py:
  - S2 = RSI-2 mean reversion in uptrend (daily, short-hold)
  - S3 = 52-week-high momentum (weekly, medium-hold)

What this adds:
  1. Blended sequential portfolio: alternates between S2 and S3 with
     configurable weights (default 60% S2 / 40% S3)
  2. Transaction costs:  ROUND_TRIP_BPS = 20 (10bp each side, realistic
     for small-cap retail with commission + half-spread)
  3. Decade breakdown:   stats per decade (1980s through 2020s) to see
     whether the edge has decayed over time
  4. Per-month equity curve: written to blend_equity.csv

Compare to the original single-strategy CAGRs from compare_strategies.py
to see (a) does diversification help, and (b) does the edge survive
realistic frictions.
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev

import numpy as np
import pandas as pd

from compare_strategies import (
    DATA_ROOT, MIN_DAILY_BARS, SMALLCAP_MAX_MED, Trade,
    one_per_period, s2_rsi2, s3_momentum, sequential,
)

ROUND_TRIP_BPS = 20      # 0.20% total per trade (entry + exit)
S2_WEIGHT = 0.60
S3_WEIGHT = 0.40


def apply_costs(t: Trade, bps: float) -> Trade:
    """Return a new Trade with ret reduced by bps/10000 round-trip."""
    cost = bps / 10000.0
    new_ret = t.ret - cost
    return Trade(t.ticker, t.entry_date, t.exit_date, t.entry,
                 t.exit * (1 - cost), t.bars_held, t.score, new_ret)


def blended_sequential(s2: list[Trade], s3: list[Trade],
                       s2_weight: float = 0.60) -> list[Trade]:
    """One position at a time, but allocate s2_weight of capital to S2
    setups and (1-s2_weight) to S3 setups when both fire. Simplest model:
    interleave them in time, take whichever fires next and isn't busy."""
    s2_seq = sequential(s2)
    s3_seq = sequential(s3)
    # Merge by entry_date, but scale each trade's "contribution" to portfolio
    merged: list[Trade] = []
    for t in s2_seq:
        scaled_ret = t.ret * s2_weight
        merged.append(Trade(t.ticker, t.entry_date, t.exit_date, t.entry,
                            t.exit, t.bars_held, t.score, scaled_ret))
    for t in s3_seq:
        scaled_ret = t.ret * (1 - s2_weight)
        merged.append(Trade(t.ticker, t.entry_date, t.exit_date, t.entry,
                            t.exit, t.bars_held, t.score, scaled_ret))
    merged.sort(key=lambda x: x.entry_date)
    return merged


def equity_and_dd(trades: list[Trade]) -> tuple[float, float, list]:
    """Return (CAGR, max DD, equity curve list of (date, equity))."""
    if not trades:
        return float("nan"), float("nan"), []
    eq = 1.0
    peak = 1.0
    dd = 0.0
    curve = []
    for t in trades:
        eq *= (1 + t.ret)
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1.0)
        curve.append((t.exit_date, eq))
    span_days = (trades[-1].exit_date - trades[0].entry_date).days
    years = max(span_days / 365.25, 0.01)
    cagr = eq ** (1 / years) - 1.0 if eq > 0 else -1.0
    return cagr, dd, curve


def stats_block(trades: list[Trade], label: str) -> None:
    if not trades:
        print(f"\n=== {label}: 0 trades ===")
        return
    rets = np.array([t.ret for t in trades])
    wins = rets > 0
    cagr, dd, _ = equity_and_dd(trades)
    print(f"\n=== {label}  (n={len(trades)}) ===")
    print(f"  win rate           {wins.mean()*100:6.2f}%")
    print(f"  mean / trade       {rets.mean()*100:+7.3f}%")
    print(f"  median / trade     {np.median(rets)*100:+7.3f}%")
    if wins.any() and (~wins).any():
        print(f"  avg win / loss     {rets[wins].mean()*100:+6.2f}% / "
              f"{rets[~wins].mean()*100:+6.2f}%")
    print(f"  sequential CAGR    {cagr*100:+7.2f}%   max DD {dd*100:+7.2f}%")


def decade_table(trades: list[Trade], label: str) -> None:
    """Group trades by decade of entry_date; report stats per decade."""
    by_dec = defaultdict(list)
    for t in trades:
        dec = (t.entry_date.year // 10) * 10
        by_dec[dec].append(t)
    print(f"\n=== {label} — DECADE BREAKDOWN ===")
    print(f"{'decade':>8} {'n':>6} {'win%':>7} {'mean%':>9} {'CAGR%':>9} {'maxDD%':>9}")
    print("-" * 50)
    for dec in sorted(by_dec.keys()):
        ts = by_dec[dec]
        if len(ts) < 5:
            continue
        rets = np.array([t.ret for t in ts])
        wins = (rets > 0).mean() * 100
        cagr, dd, _ = equity_and_dd(ts)
        print(f"{dec:>4}s   {len(ts):>6} {wins:>6.1f}% {rets.mean()*100:>+8.3f}% "
              f"{cagr*100:>+8.2f}% {dd*100:>+8.2f}%")


def main() -> None:
    csvs = sorted(p for p in DATA_ROOT.glob("*/*.csv"))
    print(f"Scanning {len(csvs)} CSVs for small-cap proxy...", file=sys.stderr)

    s2_all: list[Trade] = []
    s3_all: list[Trade] = []
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
        if i % 2000 == 0:
            print(f"  [{i}/{len(csvs)}] small={n_small} "
                  f"s2={len(s2_all)} s3={len(s3_all)} ({time.monotonic()-t0:.0f}s)",
                  file=sys.stderr)

    print(f"\nUniverse: {n_small} small-cap tickers", file=sys.stderr)
    print(f"Raw trades: s2={len(s2_all)}, s3={len(s3_all)}", file=sys.stderr)

    # 1-per-period filter
    s2_pick = one_per_period(s2_all, best="max")
    s3_pick = one_per_period(s3_all, best="max")

    # Apply transaction costs
    s2_costs = [apply_costs(t, ROUND_TRIP_BPS) for t in s2_pick]
    s3_costs = [apply_costs(t, ROUND_TRIP_BPS) for t in s3_pick]

    # Sequential (one-at-a-time) variants
    s2_seq = sequential(s2_costs)
    s3_seq = sequential(s3_costs)
    blend = blended_sequential(s2_costs, s3_costs, s2_weight=S2_WEIGHT)

    print("\n" + "=" * 60)
    print(f"SECTION 1 — With realistic frictions ({ROUND_TRIP_BPS} bps round-trip)")
    print("=" * 60)
    stats_block(s2_seq, "S2 RSI-2 (sequential, with costs)")
    stats_block(s3_seq, "S3 52w-High Momentum (sequential, with costs)")
    stats_block(blend,
                f"BLEND (S2 {int(S2_WEIGHT*100)}% / S3 {int((1-S2_WEIGHT)*100)}%, with costs)")

    print("\n" + "=" * 60)
    print("SECTION 2 — Decade breakdown (sequential, with costs)")
    print("=" * 60)
    decade_table(s2_seq, "S2 RSI-2")
    decade_table(s3_seq, "S3 52w Momentum")
    decade_table(blend, f"BLEND ({int(S2_WEIGHT*100)}/{int((1-S2_WEIGHT)*100)})")

    # Save equity curves
    out_dir = Path(".")
    for label, trades in [("s2", s2_seq), ("s3", s3_seq), ("blend", blend)]:
        cagr, dd, curve = equity_and_dd(trades)
        if not curve:
            continue
        df = pd.DataFrame(curve, columns=["date", "equity"])
        df.to_csv(out_dir / f"equity_{label}.csv", index=False)
    print("\nWrote equity_s2.csv, equity_s3.csv, equity_blend.csv")


if __name__ == "__main__":
    main()
