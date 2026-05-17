"""
TD Sequential Bullish (Weekly, 3-bar lookback) — forward-return stats.

Pattern: 9 consecutive weekly bars where close[i] < close[i+3], for i in 0..8
(i.e. close[0]<close[3], close[1]<close[4], ..., close[8]<close[11]).
This matches the TrendSpider scanner shown in the screenshot.

Universe: S&P 600 SmallCap. Pulled from Wikipedia at runtime, with fallback
to a local tickers.csv if Wikipedia is unreachable.

Outputs:
  signals.csv  — every (ticker, signal_date, fwd_1w, fwd_4w, fwd_12w, fwd_26w)
  summary.csv  — aggregate stats per horizon
  Prints the summary table to stdout.

Requires: pip install yfinance pandas numpy lxml requests
Run:      python scanner_stats.py [--years 15] [--tickers AAPL,MSFT] [--limit N]
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

HORIZONS = {"1w": 1, "4w": 4, "12w": 12, "26w": 26}
SETUP_LEN = 9          # bars in the setup
LOOKBACK = 3           # bar-vs-bar lookback (TrendSpider scanner uses 3, classic TD uses 4)
COOLDOWN_BARS = 9      # don't fire again within this many weeks per ticker


def fetch_sp600_tickers() -> list[str]:
    """Pull current S&P 600 constituents from Wikipedia. Fall back to tickers.csv."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        for t in tables:
            cols = [str(c).lower() for c in t.columns]
            for cand in ("symbol", "ticker"):
                if cand in cols:
                    col = t.columns[cols.index(cand)]
                    return sorted({s.replace(".", "-") for s in t[col].astype(str)})
        raise RuntimeError("no symbol column found")
    except Exception as e:
        print(f"[warn] Wikipedia fetch failed ({e}); falling back to tickers.csv", file=sys.stderr)
        p = Path(__file__).with_name("tickers.csv")
        if not p.exists():
            raise SystemExit(
                "Could not fetch S&P 600 from Wikipedia and tickers.csv is missing.\n"
                "Drop a one-column CSV named tickers.csv next to this script."
            )
        return sorted({s.strip().replace(".", "-") for s in p.read_text().splitlines() if s.strip()})


def download_weekly(tickers: list[str], years: int, batch: int = 50) -> dict[str, pd.DataFrame]:
    """Weekly OHLC via yfinance in batches. Returns {ticker: df}."""
    out: dict[str, pd.DataFrame] = {}
    period = f"{years}y"
    for i in range(0, len(tickers), batch):
        chunk = tickers[i : i + batch]
        print(f"  download {i + 1}-{i + len(chunk)} / {len(tickers)}", file=sys.stderr)
        df = yf.download(
            chunk,
            period=period,
            interval="1wk",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            for t in chunk:
                if t in df.columns.get_level_values(0):
                    sub = df[t].dropna(how="all")
                    if not sub.empty:
                        out[t] = sub
        else:
            out[chunk[0]] = df.dropna(how="all")
        time.sleep(0.3)  # polite
    return out


def detect_signals(close: pd.Series) -> np.ndarray:
    """
    Index of bars where the 9-bar bullish setup *completes* on that bar.
    Condition: for k in 0..SETUP_LEN-1, close[i-k] < close[i-k-LOOKBACK].
    Equivalently the last SETUP_LEN bars each satisfy close[t] < close[t-LOOKBACK].
    """
    c = close.to_numpy()
    n = len(c)
    if n < SETUP_LEN + LOOKBACK:
        return np.empty(0, dtype=int)
    cond = np.zeros(n, dtype=bool)
    cond[LOOKBACK:] = c[LOOKBACK:] < c[:-LOOKBACK]
    # bar i completes the setup if cond[i], cond[i-1], ..., cond[i-8] all True
    rolling = np.convolve(cond.astype(int), np.ones(SETUP_LEN, dtype=int), mode="valid")
    idx = np.where(rolling == SETUP_LEN)[0] + (SETUP_LEN - 1)
    if len(idx) == 0:
        return idx
    # de-dupe overlapping fires within COOLDOWN_BARS
    kept = [idx[0]]
    for j in idx[1:]:
        if j - kept[-1] >= COOLDOWN_BARS:
            kept.append(j)
    return np.array(kept, dtype=int)


@dataclass
class Signal:
    ticker: str
    date: pd.Timestamp
    entry: float
    fwd: dict[str, float]


def scan(ticker: str, df: pd.DataFrame) -> list[Signal]:
    if "Close" not in df.columns or len(df) < SETUP_LEN + LOOKBACK + max(HORIZONS.values()):
        return []
    close = df["Close"].astype(float).dropna()
    sig_idx = detect_signals(close)
    out: list[Signal] = []
    arr = close.to_numpy()
    dates = close.index
    for i in sig_idx:
        entry = arr[i]
        if not np.isfinite(entry) or entry <= 0:
            continue
        fwd = {}
        for name, h in HORIZONS.items():
            if i + h < len(arr):
                fut = arr[i + h]
                fwd[name] = (fut / entry - 1.0) if np.isfinite(fut) else np.nan
            else:
                fwd[name] = np.nan
        out.append(Signal(ticker, dates[i], entry, fwd))
    return out


def summarize(signals: list[Signal]) -> pd.DataFrame:
    rows = []
    for name in HORIZONS:
        vals = np.array([s.fwd[name] for s in signals], dtype=float)
        vals = vals[np.isfinite(vals)]
        if len(vals) == 0:
            rows.append({"horizon": name, "n": 0})
            continue
        rows.append(
            {
                "horizon": name,
                "n": len(vals),
                "mean_%": vals.mean() * 100,
                "median_%": np.median(vals) * 100,
                "std_%": vals.std(ddof=1) * 100,
                "win_rate_%": (vals > 0).mean() * 100,
                "p10_%": np.percentile(vals, 10) * 100,
                "p25_%": np.percentile(vals, 25) * 100,
                "p75_%": np.percentile(vals, 75) * 100,
                "p90_%": np.percentile(vals, 90) * 100,
                "min_%": vals.min() * 100,
                "max_%": vals.max() * 100,
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=15, help="history length (default 15)")
    ap.add_argument("--tickers", type=str, default="", help="comma list to override the universe")
    ap.add_argument("--limit", type=int, default=0, help="cap universe size for a quick test")
    ap.add_argument("--out", type=Path, default=Path("."), help="output directory")
    args = ap.parse_args()

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = fetch_sp600_tickers()
    if args.limit:
        tickers = tickers[: args.limit]
    print(f"universe: {len(tickers)} tickers", file=sys.stderr)

    data = download_weekly(tickers, years=args.years)
    print(f"downloaded: {len(data)} tickers with data", file=sys.stderr)

    signals: list[Signal] = []
    for t, df in data.items():
        signals.extend(scan(t, df))
    print(f"signals: {len(signals)}", file=sys.stderr)

    args.out.mkdir(parents=True, exist_ok=True)
    sig_df = pd.DataFrame(
        [
            {"ticker": s.ticker, "date": s.date.date(), "entry": s.entry, **{f"fwd_{k}": s.fwd[k] for k in HORIZONS}}
            for s in signals
        ]
    )
    sig_df.to_csv(args.out / "signals.csv", index=False)
    summary = summarize(signals)
    summary.to_csv(args.out / "summary.csv", index=False)

    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", None)
    print()
    print("=== TD Sequential Bullish (W, lookback=3, setup=9) ===")
    print(f"universe={len(tickers)}  with_data={len(data)}  signals={len(signals)}  years={args.years}")
    print()
    print(summary.to_string(index=False, float_format=lambda x: f"{x:8.2f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
