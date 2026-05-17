# hbib

Backtest helper for the **TD Sequential Bullish (Weekly, 3-bar lookback)** scanner
shown in TrendSpider: 9 consecutive weekly bars where `close[t] < close[t-3]`.

## Run

Two data backends — same scanner logic, same output shape.

### yfinance (free, no key)

```bash
pip install yfinance pandas numpy lxml requests
python scanner_stats.py --years 15                 # full S&P 600
python scanner_stats.py --tickers UXIN,HBNB,OIS    # ad-hoc list
python scanner_stats.py --limit 50                 # smoke test
```

### Polygon (key required; no survivor bias, includes delistings)

```bash
pip install pandas numpy requests
export POLYGON_API_KEY=<your_key>
python scanner_stats_polygon.py --years 5          # free tier: 5 req/min, 2y max
python scanner_stats_polygon.py --years 10 --rpm 0 # paid tier: no rate cap
```

Both write `signals.csv` (every trigger + forward returns) and `summary.csv`
(aggregate stats per 1w / 4w / 12w / 26w horizon).

> Note: both Yahoo and Polygon are blocked inside the Claude Code on the web
> sandbox. Run locally, or loosen the environment's network policy.
