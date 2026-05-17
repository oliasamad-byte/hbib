"""
Run the TD Sequential Bullish (W, 3-bar lookback, 9-bar setup) scanner stats
over a local EOD dataset cloned from wumiq/us_stock_eod (~10K US tickers,
daily OHLC through 2022-03-25).

Filters tickers into a "small-cap proxy" bucket and reports stats for both
that bucket and the full universe.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from scanner_stats import HORIZONS, scan, summarize, Signal

DATA_ROOT = Path("/tmp/eod")

# Small-cap proxy: median weekly close <= this, plus min history
SMALLCAP_MEDIAN_PRICE_MAX = 20.0
MIN_WEEKLY_BARS = 260   # ~5 years


def load_weekly(csv_path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(csv_path, parse_dates=["Date"])
    except Exception:
        return None
    if df.empty or "Close" not in df.columns:
        return None
    df = df.set_index("Date").sort_index()
    # Resample daily -> weekly (Friday close)
    w = df.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min",
                                  "Close": "last", "Volume": "sum"}).dropna(how="all")
    w = w.dropna(subset=["Close"])
    if len(w) < MIN_WEEKLY_BARS:
        return None
    return w


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smallcap-max", type=float, default=SMALLCAP_MEDIAN_PRICE_MAX)
    ap.add_argument("--min-bars", type=int, default=MIN_WEEKLY_BARS)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("."))
    args = ap.parse_args()

    csvs = sorted(p for p in DATA_ROOT.glob("*/*.csv"))
    if args.limit:
        csvs = csvs[: args.limit]
    print(f"Found {len(csvs)} ticker CSVs in {DATA_ROOT}", file=sys.stderr)

    all_signals: list[Signal] = []
    small_signals: list[Signal] = []
    n_loaded = n_small = 0
    t0 = time.monotonic()

    for i, p in enumerate(csvs, 1):
        ticker = p.stem
        w = load_weekly(p)
        if w is None:
            continue
        n_loaded += 1
        med_price = w["Close"].median()
        is_small = med_price <= args.smallcap_max
        if is_small:
            n_small += 1
        sigs = scan(ticker, w)
        all_signals.extend(sigs)
        if is_small:
            small_signals.extend(sigs)
        if i % 500 == 0:
            elapsed = time.monotonic() - t0
            print(f"  [{i}/{len(csvs)}] loaded={n_loaded} small={n_small} "
                  f"signals_all={len(all_signals)} signals_small={len(small_signals)} "
                  f"({elapsed:.0f}s)", file=sys.stderr)

    print(f"\nLoaded {n_loaded} tickers ({n_small} pass small-cap proxy)", file=sys.stderr)
    print(f"Signals: {len(all_signals)} all  |  {len(small_signals)} small-cap proxy", file=sys.stderr)

    args.out.mkdir(parents=True, exist_ok=True)

    def write(signals: list[Signal], tag: str) -> pd.DataFrame:
        sig_df = pd.DataFrame([
            {"ticker": s.ticker, "date": s.date.date(), "entry": s.entry,
             **{f"fwd_{k}": s.fwd[k] for k in HORIZONS}}
            for s in signals
        ])
        sig_df.to_csv(args.out / f"signals_{tag}.csv", index=False)
        summary = summarize(signals)
        summary.to_csv(args.out / f"summary_{tag}.csv", index=False)
        return summary

    sum_all = write(all_signals, "all")
    sum_small = write(small_signals, "smallcap")

    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", None)
    fmt = lambda x: f"{x:8.2f}"

    print()
    print(f"=== ALL US STOCKS  (n_tickers={n_loaded}, n_signals={len(all_signals)}) ===")
    print(sum_all.to_string(index=False, float_format=fmt))
    print()
    print(f"=== SMALL-CAP PROXY  (median W close <= ${args.smallcap_max:.0f}, "
          f"n_tickers={n_small}, n_signals={len(small_signals)}) ===")
    print(sum_small.to_string(index=False, float_format=fmt))


if __name__ == "__main__":
    main()
