"""
Head-to-head backtest of three daily/weekly strategies on the same small-cap
universe (wumiq/us_stock_eod, 1962-2022, median W close <= $20, >=5y history).

S1 - Breakout-on-strength (daily):
       entry: 20d high + vol >= 2x 50d avg + close > 200d SMA
       exit:  close < 10d SMA
       pick:  highest rel-vol per day  (one stock/day)

S2 - RSI(2) mean-reversion in uptrend (daily, "Connors"):
       entry: RSI(2) < 10 + close > 200d SMA + 200d SMA rising
       exit:  close > 5d SMA  (capped at 10 bars)
       pick:  lowest RSI(2) per day  (one stock/day)

S3 - 52-week-high momentum (weekly, "Jegadeesh-Titman / George-Hwang"):
       entry: close >= 95% of 52w high + close > 50w SMA + 50w SMA rising
              + 12w return >= +10%
       exit:  close < 10w SMA
       pick:  highest (close / 52w_high) ratio per week  (one stock/week)
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA_ROOT = Path("/tmp/eod")
SMALLCAP_MAX_MED = 20.0
MIN_DAILY_BARS = 260


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry: float
    exit: float
    bars_held: int
    score: float
    ret: float


# ---------------- helpers ----------------

def rsi(close: np.ndarray, period: int = 2) -> np.ndarray:
    delta = np.diff(close, prepend=close[0])
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)
    # Wilder smoothing
    avg_up = np.zeros_like(close)
    avg_dn = np.zeros_like(close)
    avg_up[:period] = np.nan
    avg_dn[:period] = np.nan
    avg_up[period - 1] = up[:period].mean()
    avg_dn[period - 1] = down[:period].mean()
    for i in range(period, len(close)):
        avg_up[i] = (avg_up[i - 1] * (period - 1) + up[i]) / period
        avg_dn[i] = (avg_dn[i - 1] * (period - 1) + down[i]) / period
    rs = avg_up / np.where(avg_dn == 0, 1e-12, avg_dn)
    return 100 - 100 / (1 + rs)


# ---------------- strategies ----------------

def s1_breakout(ticker: str, daily: pd.DataFrame) -> list[Trade]:
    if len(daily) < 260:
        return []
    c = daily["Close"].astype(float).to_numpy()
    v = daily["Volume"].astype(float).to_numpy()
    dates = daily.index
    roll_high = pd.Series(c).rolling(20).max().to_numpy()
    avg_v = pd.Series(v).rolling(50).mean().to_numpy()
    sma200 = pd.Series(c).rolling(200).mean().to_numpy()
    sma10 = pd.Series(c).rolling(10).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        rel_v = v / avg_v
    fire = (
        (c == roll_high) & (rel_v >= 2.0) & (c > sma200)
        & np.isfinite(sma200) & np.isfinite(avg_v)
    )
    trades = []
    i = 200
    while i < len(c):
        if not fire[i]:
            i += 1
            continue
        j = i + 1
        while j < len(c) and (not np.isfinite(sma10[j]) or c[j] >= sma10[j]):
            j += 1
        j = min(j, len(c) - 1)
        trades.append(Trade(ticker, dates[i], dates[j], c[i], c[j], j - i, rel_v[i],
                            c[j] / c[i] - 1.0))
        i = j + 1
    return trades


def s2_rsi2(ticker: str, daily: pd.DataFrame) -> list[Trade]:
    if len(daily) < 260:
        return []
    c = daily["Close"].astype(float).to_numpy()
    dates = daily.index
    sma200 = pd.Series(c).rolling(200).mean().to_numpy()
    sma5 = pd.Series(c).rolling(5).mean().to_numpy()
    rsi2 = rsi(c, 2)
    # 200d SMA rising = today's sma200 > sma200 30 bars ago
    sma200_30ago = np.concatenate([np.full(30, np.nan), sma200[:-30]])
    fire = (rsi2 < 10) & (c > sma200) & (sma200 > sma200_30ago) & np.isfinite(sma200_30ago)
    trades = []
    i = 200
    while i < len(c):
        if not fire[i]:
            i += 1
            continue
        # Connors exit: close > 5d SMA, max 10 bars
        max_hold = 10
        j = i + 1
        while j < len(c) and (j - i) <= max_hold and not (np.isfinite(sma5[j]) and c[j] > sma5[j]):
            j += 1
        j = min(j, len(c) - 1)
        trades.append(Trade(ticker, dates[i], dates[j], c[i], c[j], j - i, -rsi2[i],
                            c[j] / c[i] - 1.0))
        i = j + 1
    return trades


def s3_momentum(ticker: str, weekly: pd.DataFrame) -> list[Trade]:
    if len(weekly) < 60:
        return []
    c = weekly["Close"].astype(float).to_numpy()
    dates = weekly.index
    high52 = pd.Series(c).rolling(52).max().to_numpy()
    sma50w = pd.Series(c).rolling(50).mean().to_numpy()
    sma10w = pd.Series(c).rolling(10).mean().to_numpy()
    sma50w_8ago = np.concatenate([np.full(8, np.nan), sma50w[:-8]])
    ret12w = np.concatenate([np.full(12, np.nan), c[12:] / c[:-12] - 1.0])
    with np.errstate(invalid="ignore", divide="ignore"):
        prox = c / high52  # 1.0 = at the high
    fire = (
        (prox >= 0.95) & (c > sma50w) & (sma50w > sma50w_8ago)
        & (ret12w >= 0.10)
        & np.isfinite(sma50w_8ago) & np.isfinite(ret12w)
    )
    trades = []
    i = 50
    while i < len(c):
        if not fire[i]:
            i += 1
            continue
        max_hold = 12
        j = i + 1
        while j < len(c) and (j - i) <= max_hold and not (np.isfinite(sma10w[j]) and c[j] < sma10w[j]):
            j += 1
        j = min(j, len(c) - 1)
        trades.append(Trade(ticker, dates[i], dates[j], c[i], c[j], j - i, prox[i],
                            c[j] / c[i] - 1.0))
        i = j + 1
    return trades


# ---------------- one-per-period filter ----------------

def one_per_period(trades: list[Trade], best="max") -> list[Trade]:
    by_date: dict = {}
    for t in trades:
        cur = by_date.get(t.entry_date)
        if cur is None:
            by_date[t.entry_date] = t
        elif (best == "max" and t.score > cur.score) or (best == "min" and t.score < cur.score):
            by_date[t.entry_date] = t
    return sorted(by_date.values(), key=lambda x: x.entry_date)


def sequential(trades: list[Trade]) -> list[Trade]:
    """Sequential: only take a new trade if no position is open."""
    out, busy_until = [], None
    for t in sorted(trades, key=lambda x: x.entry_date):
        if busy_until is None or t.entry_date >= busy_until:
            out.append(t)
            busy_until = t.exit_date
    return out


# ---------------- reporting ----------------

def report(trades: list[Trade], label: str, bars_per_year: int) -> None:
    if not trades:
        print(f"\n=== {label}: 0 trades ===")
        return
    r = np.array([t.ret for t in trades])
    h = np.array([t.bars_held for t in trades])
    wins = r > 0
    avg_w = r[wins].mean() if wins.any() else 0.0
    avg_l = r[~wins].mean() if (~wins).any() else 0.0
    payoff = (-avg_w / avg_l) if avg_l < 0 else float("inf")
    exp_ = r.mean()
    # Sequential equity & drawdown
    seq = sequential(trades)
    if seq:
        equity = np.cumprod(1.0 + np.array([t.ret for t in seq]))
        peak = np.maximum.accumulate(equity)
        dd = (equity / peak - 1.0).min()
        total_bars = sum(t.bars_held for t in seq)
        years = total_bars / bars_per_year
        cagr = equity[-1] ** (1 / max(years, 0.01)) - 1.0 if equity[-1] > 0 else -1.0
    else:
        dd, cagr = float("nan"), float("nan")

    print(f"\n=== {label}  (n={len(trades)}) ===")
    print(f"  win rate           {wins.mean()*100:6.2f}%")
    print(f"  mean return        {r.mean()*100:+7.2f}%")
    print(f"  median return      {np.median(r)*100:+7.2f}%")
    print(f"  avg win / loss     {avg_w*100:+7.2f}% / {avg_l*100:+7.2f}%")
    print(f"  payoff ratio       {payoff:6.2f}")
    print(f"  expectancy         {exp_*100:+7.2f}% per trade")
    print(f"  hold (bars)        median={np.median(h):.0f}  mean={h.mean():.1f}  p90={np.percentile(h,90):.0f}")
    print(f"  sequential CAGR    {cagr*100:+7.2f}%   max DD {dd*100:+7.2f}%   n_seq={len(seq)}")


# ---------------- driver ----------------

def main() -> None:
    csvs = sorted(p for p in DATA_ROOT.glob("*/*.csv"))
    print(f"Found {len(csvs)} CSVs", file=sys.stderr)

    s1_all: list[Trade] = []
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
        # Small-cap filter on weekly median
        weekly = daily.resample("W-FRI").agg({"Open":"first","High":"max","Low":"min",
                                              "Close":"last","Volume":"sum"}).dropna(subset=["Close"])
        if len(weekly) < 60:
            continue
        n_loaded += 1
        if weekly["Close"].median() > SMALLCAP_MAX_MED:
            continue
        n_small += 1
        s1_all.extend(s1_breakout(p.stem, daily))
        s2_all.extend(s2_rsi2(p.stem, daily))
        s3_all.extend(s3_momentum(p.stem, weekly))
        if i % 1000 == 0:
            print(f"  [{i}/{len(csvs)}] loaded={n_loaded} small={n_small} "
                  f"s1={len(s1_all)} s2={len(s2_all)} s3={len(s3_all)} "
                  f"({time.monotonic()-t0:.0f}s)", file=sys.stderr)

    print(f"\nLoaded {n_loaded}, small-cap subset {n_small}", file=sys.stderr)
    print(f"Raw trades  s1={len(s1_all)}  s2={len(s2_all)}  s3={len(s3_all)}", file=sys.stderr)

    # 1-stock-per-period rule with strategy-appropriate ranking
    s1_pick = one_per_period(s1_all, best="max")  # highest rel-vol
    s2_pick = one_per_period(s2_all, best="max")  # highest -RSI = lowest RSI
    s3_pick = one_per_period(s3_all, best="max")  # closest to 52w high

    report(s1_pick, "S1 BREAKOUT (1/day, highest rel-vol)",          bars_per_year=252)
    report(s2_pick, "S2 RSI-2 MEAN-REVERSION (1/day, lowest RSI)",   bars_per_year=252)
    report(s3_pick, "S3 52W-HIGH MOMENTUM (1/week, closest to high)", bars_per_year=52)


if __name__ == "__main__":
    main()
