"""Vortex Triangle scanner — proxy backtest.

Approximates TrendSpider's "any triangle break-up + breakout bar" scanner
on daily bars. We can't replicate proprietary trendline detection, so we
use a defensible analog of the same IDEA: "price just broke a recent
resistance level it wasn't above 5 days ago, on a volume bar".

Entry signal (must all be true on bar D, daily):
  - close[D]     > max(high[D-LOOKBACK:D])         # new N-day high TODAY
  - close[D-5]   < max(high[D-LOOKBACK-5:D-5])     # was below that resistance 5 days ago
  - volume[D]    > 1.5 * SMA(volume, 20)           # Breakout Bar proxy: volume confirms
  - close[D]     > SMA(close, 200)                 # only count breakouts in established uptrends
                                                    # (TrendSpider doesn't require this, but it
                                                    # removes "dead-cat" breakouts that fade)

Stats reported:
  - n trades, win rate at 1d / 5d / 10d / 20d forward
  - mean / median return per horizon
  - hit rate vs. random-baseline same-universe
  - per-decade breakdown

Universes:
  - Small-cap proxy (median weekly close <= $20)
  - Full universe (~all US stocks)
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA_ROOT = Path("/tmp/eod")
LOOKBACK = 20            # how far back to compute the resistance level
LOOKBACK_PRIOR = 5       # how many days ago "wasn't above resistance"
VOL_MULT = 1.5           # breakout-bar volume proxy
HORIZONS = [1, 5, 10, 20]
MIN_BARS = 260
SMALLCAP_MAX_MED = 20.0


@dataclass
class Trade:
    ticker: str
    date: pd.Timestamp
    entry: float
    fwd_rets: dict[int, float]


def find_signals(ticker: str, df: pd.DataFrame) -> list[Trade]:
    if len(df) < 260:
        return []
    c = df["Close"].astype(float).to_numpy()
    h = df["High"].astype(float).to_numpy()
    v = df["Volume"].astype(float).to_numpy()
    dates = df.index

    sma200 = pd.Series(c).rolling(200).mean().to_numpy()
    avg_vol = pd.Series(v).rolling(20).mean().to_numpy()
    # Rolling 20-day max EXCLUDING today (shift by 1)
    res = pd.Series(h).rolling(LOOKBACK).max().shift(1).to_numpy()

    n = len(c)
    out: list[Trade] = []
    max_horizon = max(HORIZONS)
    for i in range(220, n - max_horizon):
        if not (np.isfinite(res[i]) and np.isfinite(sma200[i])
                and np.isfinite(avg_vol[i]) and avg_vol[i] > 0):
            continue
        # Today breaks resistance
        if c[i] <= res[i]:
            continue
        # 5 days ago was NOT above its own resistance
        j = i - LOOKBACK_PRIOR
        if j < LOOKBACK:
            continue
        if not np.isfinite(res[j]):
            continue
        if c[j] >= res[j]:
            continue
        # Volume confirms
        if v[i] < VOL_MULT * avg_vol[i]:
            continue
        # Trend filter
        if c[i] <= sma200[i]:
            continue

        entry = c[i]
        if entry <= 0:
            continue
        fwd = {}
        for hzn in HORIZONS:
            if i + hzn >= n:
                fwd[hzn] = np.nan
            else:
                fwd[hzn] = c[i + hzn] / entry - 1.0
        out.append(Trade(ticker=ticker, date=dates[i], entry=entry, fwd_rets=fwd))
    return out


def random_baseline(tickers_data: dict[str, pd.DataFrame], n_samples: int,
                    rng: np.random.Generator) -> list[Trade]:
    """Same N, random (ticker, date) pairs, same forward horizons."""
    out = []
    names = list(tickers_data.keys())
    max_horizon = max(HORIZONS)
    attempts = 0
    while len(out) < n_samples and attempts < n_samples * 5:
        attempts += 1
        t = rng.choice(names)
        df = tickers_data[t]
        if len(df) < 220 + max_horizon + 1:
            continue
        i = rng.integers(220, len(df) - max_horizon - 1)
        c = df["Close"].astype(float).to_numpy()
        entry = c[i]
        if entry <= 0 or not np.isfinite(entry):
            continue
        fwd = {h: c[i + h] / entry - 1.0 for h in HORIZONS}
        out.append(Trade(ticker=t, date=df.index[i], entry=entry, fwd_rets=fwd))
    return out


def report(trades: list[Trade], label: str) -> None:
    if not trades:
        print(f"\n=== {label}: 0 trades ===")
        return
    print(f"\n=== {label}  (n={len(trades)}) ===")
    print(f"{'horizon':>8}{'win%':>8}{'mean%':>9}{'median%':>10}"
          f"{'std%':>9}{'P25%':>9}{'P75%':>9}")
    print("-" * 62)
    for h in HORIZONS:
        rets = np.array([t.fwd_rets.get(h, np.nan) for t in trades])
        rets = rets[np.isfinite(rets)]
        if len(rets) == 0:
            continue
        wins = (rets > 0).mean() * 100
        print(f"{h:>4}d{wins:>7.1f}%{rets.mean()*100:>+8.2f}%"
              f"{np.median(rets)*100:>+9.2f}%{rets.std()*100:>+8.2f}%"
              f"{np.percentile(rets, 25)*100:>+8.2f}%"
              f"{np.percentile(rets, 75)*100:>+8.2f}%")


def decade_breakdown(trades: list[Trade], horizon: int = 5) -> None:
    by_dec = defaultdict(list)
    for t in trades:
        dec = (t.date.year // 10) * 10
        r = t.fwd_rets.get(horizon)
        if np.isfinite(r):
            by_dec[dec].append(r)
    print(f"\nDecade breakdown (horizon={horizon}d):")
    print(f"  {'decade':>8}{'n':>6}{'win%':>8}{'mean%':>9}")
    print(f"  {'-'*32}")
    for dec in sorted(by_dec):
        rets = np.array(by_dec[dec])
        if len(rets) < 10:
            continue
        wins = (rets > 0).mean() * 100
        print(f"  {dec:>4}s {len(rets):>6}{wins:>7.1f}%{rets.mean()*100:>+8.2f}%")


def main() -> None:
    csvs = sorted(p for p in DATA_ROOT.glob("*/*.csv"))
    print(f"Scanning {len(csvs)} CSVs...", file=sys.stderr)

    sigs_full: list[Trade] = []
    sigs_small: list[Trade] = []
    smallcap_data: dict[str, pd.DataFrame] = {}  # for random baseline
    n_loaded = n_small = 0
    t0 = time.monotonic()

    for i, p in enumerate(csvs, 1):
        try:
            df = pd.read_csv(p, parse_dates=["Date"]).set_index("Date").sort_index()
        except Exception:
            continue
        if df.empty or len(df) < MIN_BARS or "Close" not in df.columns:
            continue
        n_loaded += 1
        # cheap small-cap proxy: median close <= $20
        is_small = df["Close"].median() <= SMALLCAP_MAX_MED
        if is_small:
            n_small += 1
            smallcap_data[p.stem] = df

        trs = find_signals(p.stem, df)
        sigs_full.extend(trs)
        if is_small:
            sigs_small.extend(trs)
        if i % 2000 == 0:
            print(f"  [{i}/{len(csvs)}] loaded={n_loaded} small={n_small} "
                  f"sigs_full={len(sigs_full)} sigs_small={len(sigs_small)} "
                  f"({time.monotonic()-t0:.0f}s)", file=sys.stderr)

    print(f"\nLoaded {n_loaded}, small-cap proxy {n_small}", file=sys.stderr)
    print(f"Signals: full={len(sigs_full)} small={len(sigs_small)}", file=sys.stderr)

    # Stats per universe
    report(sigs_full, "FULL UNIVERSE — Vortex Triangle proxy")
    report(sigs_small, "SMALL-CAP PROXY — Vortex Triangle proxy")

    # Random baseline (small-cap, same N)
    rng = np.random.default_rng(42)
    baseline = random_baseline(smallcap_data, n_samples=len(sigs_small), rng=rng)
    report(baseline, "SMALL-CAP RANDOM BASELINE  (same N, random entries)")

    # Edge calculation per horizon
    print("\n=== EDGE OVER RANDOM (small-cap) ===")
    print(f"{'horizon':>8}{'sig win%':>10}{'rand win%':>11}{'edge':>8}"
          f"{'sig mean%':>11}{'rand mean%':>12}{'edge':>9}")
    print("-" * 70)
    for h in HORIZONS:
        sig_r = np.array([t.fwd_rets[h] for t in sigs_small if np.isfinite(t.fwd_rets[h])])
        rand_r = np.array([t.fwd_rets[h] for t in baseline if np.isfinite(t.fwd_rets[h])])
        if len(sig_r) == 0 or len(rand_r) == 0:
            continue
        sw = (sig_r > 0).mean() * 100
        rw = (rand_r > 0).mean() * 100
        sm = sig_r.mean() * 100
        rm = rand_r.mean() * 100
        print(f"{h:>4}d{sw:>9.1f}%{rw:>10.1f}%{sw-rw:>+7.1f}pt"
              f"{sm:>+10.2f}%{rm:>+11.2f}%{sm-rm:>+8.2f}pt")

    # Decade breakdown for small-cap
    decade_breakdown(sigs_small, horizon=5)
    decade_breakdown(sigs_small, horizon=20)


if __name__ == "__main__":
    main()
