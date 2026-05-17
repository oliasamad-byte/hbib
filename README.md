# hbib

Backtest helper for the **TD Sequential Bullish (Weekly, 3-bar lookback)** scanner
shown in TrendSpider: 9 consecutive weekly bars where `close[t] < close[t-3]`.

## Run

```bash
pip install yfinance pandas numpy lxml requests
python scanner_stats.py                            # full S&P 600, 15y history
python scanner_stats.py --years 20                 # longer history
python scanner_stats.py --tickers UXIN,HBNB,OIS    # the 5 hits from the screenshot
python scanner_stats.py --limit 50                 # quick smoke test
```

Outputs `signals.csv` (every trigger + forward returns) and `summary.csv`
(aggregate stats per 1w / 4w / 12w / 26w horizon).

> Note: this script needs Yahoo Finance, which is blocked inside the Claude
> Code on the web sandbox. Run it locally.
