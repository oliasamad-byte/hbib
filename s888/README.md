# S888 — Top Gainers Triple-Track Ranker

Read-only intelligence feed that pulls top US gainers, scores them across
three independent tracks (Daily Small Cap, Daily Mid+L+M, Weekly), and
sends three ranked Telegram messages every 10 min during your monitoring
window.

**No trades. No alerts. No positions.** Pure ranker → you decide.

## Setup (5 minutes)

```bash
git clone https://github.com/oliasamad-byte/hbib.git
cd hbib/s888
python -m venv .venv && source .venv/bin/activate     # macOS/Linux
# or:  .venv\Scripts\activate                          # Windows
pip install -e .[dev]
```

### Configure

```bash
cp .env.example .env
```

Edit `.env` and fill in three values **reused from your S3 setup**:

```
FMP_API_KEY=...            # same value as your S3 .env
TELEGRAM_BOT_TOKEN=...     # same value as your S3 .env
TELEGRAM_CHAT_ID=...       # same value as your S3 .env
```

Leave everything else at defaults — tune later.

> ⚠️ **FMP IP whitelisting:** if your FMP key is restricted to specific IPs
> (e.g. office IP only), S888 must be run from a whitelisted IP. Add your
> home IP in the FMP dashboard if you want to run it from both locations.

## Run

```bash
# One-off scan (off-hours OK — sparse output but verifies the pipeline)
python -m s888.orchestrator --once       # single scan, sends 1–3 Telegram messages
python -m s888.universe                  # debug: prints merged universe only

# Scheduled mode (default 17:30–22:30 GST, every 10 min)
python -m s888.orchestrator
```

To run as a background service on Linux:
```bash
nohup python -m s888.orchestrator > logs/run.log 2>&1 &
```

## Tests

```bash
pytest                                    # all offline tests
pytest --cov=s888                         # with coverage
```

## Project layout

```
s888/
├── .env.example
├── pyproject.toml
├── requirements.txt
├── README.md
├── STRATEGY_MAPPING.md            # how S888 design serves your trading workflow
├── s888/
│   ├── config.py                  # env loader (single source of truth)
│   ├── cache.py                   # SQLite cache + state tables
│   ├── universe.py                # Step 1: YF + FMP per-cap merge
│   ├── cap_categorizer.py         # small / mid / large / mega tagging
│   ├── news_fmp.py                # Step 2a: FMP /stock_news + /press_releases
│   ├── news_yf.py                 # Step 2b: yfinance per-ticker news
│   ├── news_merge.py              # Step 2c: Jaccard dedupe (>0.7)
│   ├── catalyst.py                # Step 2d: 1–10 classifier
│   ├── earnings_calendar.py       # Step 2e: 14d ahead, cached
│   ├── analyst_activity.py        # §5.5: AAS 0–3, bullish-only, 24h cache
│   ├── mtf.py                     # async multi-TF bar fetcher (7 TFs)
│   ├── indicators.py              # VWAP, EMA, RSI, CMF, ADX, ATR, OBV, Weinstein
│   ├── breakout_levels.py         # ORB, PDH, PMH, 20d/52w/8w high
│   ├── tech_score_daily.py        # DTS 0–38 (28 base + 7 BO + 3 AAS)
│   ├── tech_score_weekly.py       # WTS 0–19 (10 base + 6 BO + 3 AAS)
│   ├── ranker_daily.py            # cap-segmented: small / mid+L+M
│   ├── ranker_weekly.py           # filter (Stage 4 hard-block) + sort
│   ├── earnings_warning.py        # ⚠️ / ⚠️⚠️ / ⚠️⚠️⚠️ tags per spec §10
│   ├── state.py                   # per-track 🆕/👋 diffing
│   ├── telegram_format.py         # 3 message formatters
│   ├── orchestrator.py            # pipeline + APScheduler
│   └── utils/
│       ├── fmp_client.py          # async FMP REST client (rate-limited)
│       ├── yf_client.py           # yfinance + day_gainers wrappers
│       └── telegram_client.py     # async Telegram sender (chunked for 4096 limit)
├── data/                          # SQLite DB lives here (gitignored)
├── logs/                          # daily log files (gitignored)
└── tests/                         # 96 passing offline tests
```

## Build status

| Stage | Status |
|---|---|
| 1 — scaffold, config, cache, FMP client, YF wrapper, universe, cap categorizer | ✅ |
| 2 — news (FMP + YF), Jaccard dedupe, catalyst, earnings calendar, AAS | ✅ |
| 3 — indicators (all 9), breakout reference levels (5), MTF fetcher | ✅ |
| 4 — DTS (0–38) + WTS (0–19), cap-segmented daily ranker, weekly ranker | ✅ |
| 5 — earnings warning, state diffing, 3 Telegram formatters + sender | ✅ |
| 6 — orchestrator (triple-track pipeline) + APScheduler | ✅ |

**All 25 spec commits delivered. 96 tests passing offline.**

Network code (FMP, YF, Telegram) is fully wired but cannot be exercised
inside the Claude Code on the web sandbox — those hosts are firewalled.
Verify the live paths on your office machine with `python -m s888.orchestrator --once`.

See `S888_SPEC.md` (in your home directory) for the full spec.

## Where to log trades

S888 ships a companion `trade_logger.py` (at repo root). After each
position closes, log it so the loser-pattern analyzer can find what to
hard-filter next.

```bash
python ../trade_logger.py log-trade --ticker UXIN --entry-time 18:32 \
                                     --entry 2.55 --exit-time 22:00 --exit 2.60
python ../trade_logger.py analyze    # after ~2 weeks of data
```
