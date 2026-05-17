"""
TD Sequential Bullish (Weekly, 3-bar lookback) — forward-return stats via Polygon.

Same scanner logic as scanner_stats.py but fetches weekly OHLC from Polygon
instead of yfinance. Polygon gives you adjusted bars and includes delisted
tickers (no survivor bias).

Auth: set POLYGON_API_KEY in env. Never pass it on the command line.
Free tier: 5 req/min, 2 yrs of history. Paid Starter+: unlimited, 5+ yrs.

Requires: pip install pandas numpy requests
Run:
  export POLYGON_API_KEY=...
  python scanner_stats_polygon.py                       # full S&P 600, 5y
  python scanner_stats_polygon.py --years 10
  python scanner_stats_polygon.py --tickers UXIN,HBNB   # ad-hoc list
  python scanner_stats_polygon.py --limit 30            # smoke test
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from scanner_stats import (
    HORIZONS,
    Signal,
    fetch_sp600_tickers,
    scan,
    summarize,
)

BASE = "https://api.polygon.io"


class PolygonClient:
    def __init__(self, api_key: str, max_rpm: int = 5):
        self.key = api_key
        self.min_interval = 60.0 / max_rpm if max_rpm > 0 else 0.0
        self._last_call = 0.0
        self.session = requests.Session()

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def weekly_bars(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        """Return weekly OHLC for ticker as a DataFrame indexed by date."""
        url = f"{BASE}/v2/aggs/ticker/{ticker}/range/1/week/{start}/{end}"
        params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": self.key}
        for attempt in range(5):
            self._throttle()
            r = self.session.get(url, params=params, timeout=30)
            if r.status_code == 429:  # rate-limited
                time.sleep(15 * (attempt + 1))
                continue
            if r.status_code == 404:
                return pd.DataFrame()
            r.raise_for_status()
            data = r.json()
            results = data.get("results") or []
            if not results:
                return pd.DataFrame()
            df = pd.DataFrame(results)
            df["Date"] = pd.to_datetime(df["t"], unit="ms")
            return df.set_index("Date").rename(
                columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"}
            )[["Open", "High", "Low", "Close", "Volume"]]
        raise RuntimeError(f"polygon: gave up on {ticker} after rate-limit retries")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--tickers", type=str, default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--rpm", type=int, default=5, help="rate cap (5 for free tier, 0 to disable)")
    ap.add_argument("--out", type=Path, default=Path("."))
    args = ap.parse_args()

    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        print("error: set POLYGON_API_KEY in env", file=sys.stderr)
        return 2

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = fetch_sp600_tickers()
    if args.limit:
        tickers = tickers[: args.limit]
    print(f"universe: {len(tickers)} tickers", file=sys.stderr)

    client = PolygonClient(key, max_rpm=args.rpm)
    end = date.today()
    start = end - timedelta(days=int(args.years * 365.25) + 14)

    signals: list[Signal] = []
    n_with_data = 0
    for i, t in enumerate(tickers, 1):
        try:
            df = client.weekly_bars(t, start, end)
        except Exception as e:
            print(f"  [{i}/{len(tickers)}] {t}: ERROR {e}", file=sys.stderr)
            continue
        if df.empty:
            print(f"  [{i}/{len(tickers)}] {t}: no data", file=sys.stderr)
            continue
        n_with_data += 1
        sigs = scan(t, df)
        signals.extend(sigs)
        if sigs:
            print(f"  [{i}/{len(tickers)}] {t}: {len(sigs)} signal(s)", file=sys.stderr)

    print(f"\ndownloaded: {n_with_data}  signals: {len(signals)}", file=sys.stderr)

    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"ticker": s.ticker, "date": s.date.date(), "entry": s.entry,
             **{f"fwd_{k}": s.fwd[k] for k in HORIZONS}}
            for s in signals
        ]
    ).to_csv(args.out / "signals.csv", index=False)
    summary = summarize(signals)
    summary.to_csv(args.out / "summary.csv", index=False)

    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", None)
    print()
    print("=== TD Sequential Bullish (W, lookback=3, setup=9) — Polygon ===")
    print(f"universe={len(tickers)}  with_data={n_with_data}  signals={len(signals)}  years={args.years}")
    print()
    print(summary.to_string(index=False, float_format=lambda x: f"{x:8.2f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
