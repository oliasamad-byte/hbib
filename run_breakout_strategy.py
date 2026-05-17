"""
Backtest the daily 20-day breakout + relative-volume hunter.

Entry per ticker, per day:
  close == max(close, last 20 days)        # new 20d high on close
  volume >= 2.0 * mean(volume, last 50 d)  # volume confirmation
  close > SMA(close, 200)                  # trend filter

Exit:
  close < SMA(close, 10)                   # trail off the 10d SMA

Trade selection:
  Across all tickers firing on the same date, take the single one with the
  highest relative volume (volume / 50d-avg-volume). This is the "one stock
  per day" rule. We allow concurrent positions only if a later day's pick
  is on a different ticker.

Reports:
  - win rate, mean/median R, mean/median %
  - distribution of holding period
  - comparison vs. all-fires (no one-per-day filter) and vs. random baseline
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA_ROOT = Path("/tmp/eod")
SMALLCAP_MAX_MED = 20.0  # for small-cap subset
MIN_BARS = 260           # daily bars
VOL_MULT = 2.0
HIGH_LOOKBACK = 20
VOL_LOOKBACK = 50
TREND_SMA = 200
EXIT_SMA = 10


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry: float
    exit: float
    bars_held: int
    rel_vol: float
    ret: float


def find_trades(ticker: str, df: pd.DataFrame) -> list[Trade]:
    df = df.sort_index()
    if len(df) < TREND_SMA + 20:
        return []
    close = df["Close"].astype(float).to_numpy()
    vol = df["Volume"].astype(float).to_numpy()
    dates = df.index

    roll_high = pd.Series(close).rolling(HIGH_LOOKBACK).max().to_numpy()
    avg_vol = pd.Series(vol).rolling(VOL_LOOKBACK).mean().to_numpy()
    sma200 = pd.Series(close).rolling(TREND_SMA).mean().to_numpy()
    sma10 = pd.Series(close).rolling(EXIT_SMA).mean().to_numpy()

    with np.errstate(invalid="ignore", divide="ignore"):
        rel_vol = vol / avg_vol
    fire = (
        (close == roll_high)
        & (rel_vol >= VOL_MULT)
        & (close > sma200)
        & np.isfinite(sma200)
        & np.isfinite(avg_vol)
    )

    trades: list[Trade] = []
    i = TREND_SMA
    n = len(close)
    while i < n:
        if not fire[i]:
            i += 1
            continue
        entry_i = i
        entry_px = close[entry_i]
        j = entry_i + 1
        while j < n and (not np.isfinite(sma10[j]) or close[j] >= sma10[j]):
            j += 1
        exit_i = j if j < n else n - 1
        exit_px = close[exit_i]
        trades.append(
            Trade(
                ticker=ticker,
                entry_date=dates[entry_i],
                exit_date=dates[exit_i],
                entry=entry_px,
                exit=exit_px,
                bars_held=exit_i - entry_i,
                rel_vol=rel_vol[entry_i],
                ret=(exit_px / entry_px) - 1.0,
            )
        )
        i = exit_i + 1  # don't re-enter same ticker until current trade closes
    return trades


def one_per_day(trades: list[Trade]) -> list[Trade]:
    """For each calendar day, keep only the trade with the highest rel_vol."""
    if not trades:
        return []
    by_date: dict[pd.Timestamp, Trade] = {}
    for t in trades:
        cur = by_date.get(t.entry_date)
        if cur is None or t.rel_vol > cur.rel_vol:
            by_date[t.entry_date] = t
    return sorted(by_date.values(), key=lambda x: x.entry_date)


def stats(trades: list[Trade], label: str) -> dict:
    if not trades:
        print(f"\n=== {label}: NO TRADES ===")
        return {}
    rets = np.array([t.ret for t in trades])
    holds = np.array([t.bars_held for t in trades])
    wins = rets > 0
    print(f"\n=== {label}  (n={len(trades)}) ===")
    print(f"  win rate          {wins.mean()*100:6.2f}%")
    print(f"  mean return       {rets.mean()*100:+7.2f}%")
    print(f"  median return     {np.median(rets)*100:+7.2f}%")
    print(f"  std               {rets.std(ddof=1)*100:6.2f}%")
    if wins.any() and (~wins).any():
        avg_win = rets[wins].mean()
        avg_loss = rets[~wins].mean()
        expectancy = wins.mean() * avg_win + (1 - wins.mean()) * avg_loss
        payoff = -avg_win / avg_loss
        print(f"  avg win           {avg_win*100:+7.2f}%")
        print(f"  avg loss          {avg_loss*100:+7.2f}%")
        print(f"  payoff ratio      {payoff:6.2f}")
        print(f"  expectancy        {expectancy*100:+7.2f}% / trade")
    print(f"  holding (bars)    mean={holds.mean():.1f}  median={np.median(holds):.0f}  "
          f"p90={np.percentile(holds,90):.0f}")
    print(f"  P10 / P25 / P75 / P90  "
          f"{np.percentile(rets,10)*100:+6.2f}% / {np.percentile(rets,25)*100:+6.2f}% / "
          f"{np.percentile(rets,75)*100:+6.2f}% / {np.percentile(rets,90)*100:+6.2f}%")
    return {"win_rate": wins.mean(), "mean": rets.mean(), "median": np.median(rets)}


def main() -> None:
    csvs = sorted(p for p in DATA_ROOT.glob("*/*.csv"))
    print(f"Found {len(csvs)} CSVs", file=sys.stderr)

    all_trades_full: list[Trade] = []
    all_trades_small: list[Trade] = []
    n_loaded = n_small = 0
    t0 = time.monotonic()

    for i, p in enumerate(csvs, 1):
        try:
            df = pd.read_csv(p, parse_dates=["Date"]).set_index("Date").sort_index()
        except Exception:
            continue
        if df.empty or "Close" not in df.columns or len(df) < MIN_BARS:
            continue
        n_loaded += 1
        med_price = df["Close"].median()
        is_small = med_price <= SMALLCAP_MAX_MED
        if is_small:
            n_small += 1
        trs = find_trades(p.stem, df)
        all_trades_full.extend(trs)
        if is_small:
            all_trades_small.extend(trs)
        if i % 1000 == 0:
            print(f"  [{i}/{len(csvs)}] loaded={n_loaded} small={n_small} "
                  f"trades_full={len(all_trades_full)} trades_small={len(all_trades_small)} "
                  f"({time.monotonic()-t0:.0f}s)", file=sys.stderr)

    print(f"\nLoaded {n_loaded}, small-cap proxy {n_small}", file=sys.stderr)
    print(f"Raw trades:  {len(all_trades_full)} full universe | "
          f"{len(all_trades_small)} small-cap proxy", file=sys.stderr)

    # Per-day single-pick filter
    opd_full = one_per_day(all_trades_full)
    opd_small = one_per_day(all_trades_small)

    stats(all_trades_full, "ALL US — every fire (allow concurrent)")
    stats(opd_full,        "ALL US — one stock per day (highest rel-vol)")
    stats(all_trades_small, "SMALL-CAP proxy — every fire")
    stats(opd_small,        "SMALL-CAP proxy — one stock per day")

    # Random baseline: same number of (ticker, date, hold-bars) but random exits
    rng = np.random.default_rng(42)
    if all_trades_small:
        sampled_holds = rng.choice([t.bars_held for t in all_trades_small], size=len(opd_small))
        # Random-date baseline using small-cap signal dates
        baseline = []
        per_ticker = {t.ticker for t in all_trades_small}
        per_ticker_data: dict[str, pd.DataFrame] = {}
        # Re-load only the tickers we need for sampling
        for p in csvs:
            if p.stem in per_ticker:
                try:
                    df = pd.read_csv(p, parse_dates=["Date"]).set_index("Date").sort_index()
                    per_ticker_data[p.stem] = df
                except Exception:
                    pass
        tickers = list(per_ticker_data.keys())
        for k in range(len(opd_small)):
            t = rng.choice(tickers)
            df = per_ticker_data[t]
            h = int(sampled_holds[k])
            if len(df) < TREND_SMA + h + 2:
                continue
            idx = int(rng.integers(TREND_SMA, len(df) - h - 1))
            entry = df["Close"].iloc[idx]
            exit_ = df["Close"].iloc[idx + h]
            if not (np.isfinite(entry) and entry > 0 and np.isfinite(exit_)):
                continue
            baseline.append(Trade(t, df.index[idx], df.index[idx + h], entry, exit_,
                                  h, 1.0, (exit_ / entry) - 1.0))
        stats(baseline, "RANDOM BASELINE (small-cap, same N, same hold dist)")


if __name__ == "__main__":
    main()
