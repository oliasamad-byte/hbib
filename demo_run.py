"""
Demo runner — sandbox can't reach Yahoo, so we use a small CSV of daily closes
for AAPL, MSFT, INTC, AMZN, GS, SPY from 2010-01-01 to 2018-06-29 (from
py4fi2nd, MIT-licensed). We resample to weekly and run the same detection
logic from scanner_stats.py.

NOTE: these are large-caps, not the small-caps the scanner targets. Results
are for methodology demonstration only.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scanner_stats import HORIZONS, detect_signals, scan, summarize


def main() -> None:
    csv = Path(__file__).with_name("data") / "demo_eod_data.csv"
    raw = pd.read_csv(csv, parse_dates=["Date"], index_col="Date")

    # Keep equity-like columns only (drop currencies / commodities / indices)
    keep = {"AAPL.O": "AAPL", "MSFT.O": "MSFT", "INTC.O": "INTC",
            "AMZN.O": "AMZN", "GS.N": "GS", "SPY": "SPY"}
    daily = raw[list(keep)].rename(columns=keep).dropna(how="all")

    # Resample daily -> weekly (Friday close)
    weekly = daily.resample("W-FRI").last().dropna(how="all")
    print(f"weekly bars per ticker: {len(weekly)}  ({weekly.index.min().date()} -> {weekly.index.max().date()})")
    print()

    signals = []
    for ticker in weekly.columns:
        close = weekly[ticker].dropna()
        df = pd.DataFrame({"Close": close})
        sigs = scan(ticker, df)
        if sigs:
            print(f"  {ticker}: {len(sigs)} signal(s)")
            for s in sigs:
                fwd_str = "  ".join(f"{k}={s.fwd[k]*100:+6.2f}%" if np.isfinite(s.fwd[k]) else f"{k}=  n/a" for k in HORIZONS)
                print(f"    {s.date.date()}  entry={s.entry:7.2f}  {fwd_str}")
        signals.extend(sigs)

    print()
    print("=== Aggregate (real data, large-caps 2010-2018) ===")
    summary = summarize(signals)
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", None)
    print(summary.to_string(index=False, float_format=lambda x: f"{x:8.2f}"))


if __name__ == "__main__":
    main()
