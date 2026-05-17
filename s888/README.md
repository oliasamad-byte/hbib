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
python -m s888.universe                  # current implementation: prints universe

# Future: full orchestrator
# python -m s888.orchestrator --once     # single scan now
# python -m s888.orchestrator            # scheduled, 5:30 PM – 10:30 PM GST
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
├── s888/
│   ├── config.py                # env loader
│   ├── cache.py                 # SQLite cache + state
│   ├── cap_categorizer.py       # small / mid / large / mega
│   ├── universe.py              # YF + FMP per-cap merge
│   └── utils/
│       ├── fmp_client.py        # async FMP REST client
│       └── yf_client.py         # yfinance + day_gainers wrappers
├── data/                        # SQLite DB lives here (gitignored)
├── logs/                        # daily log files (gitignored)
└── tests/
    ├── test_config.py
    ├── test_cache.py
    ├── test_cap_categorizer.py
    └── test_universe.py
```

## Build status

| Stage | Status |
|---|---|
| 1 — scaffold, config, cache, FMP client, YF wrapper, universe, cap categorizer | ✅ |
| 2 — news (FMP + YF), dedupe, catalyst classifier, earnings, analyst (AAS) | 🔜 |
| 3 — indicators, breakout reference levels | 🔜 |
| 4 — DTS / WTS scoring, daily + weekly rankers | 🔜 |
| 5 — telegram formatters + senders, state diffing | 🔜 |
| 6 — orchestrator + APScheduler | 🔜 |

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
