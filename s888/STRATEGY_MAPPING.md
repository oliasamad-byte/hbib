# S888 ↔ Trading Strategy Mapping

Reference doc — explicit mapping from the user's live trading workflow
to the S888 spec design, so every remaining build stage can be justified
against the actual P&L goal.

---

## The user's live strategy (as of this build)

| | Value |
|---|---|
| Window | 6:00 PM – 10:00 PM GST (≈ 9:30 AM – 1:30 PM ET, market open + first 4h) |
| Entry | Buy ~10 stocks from S888's ranked top-gainers, near 6 PM |
| Exit | Sell all positions by 10 PM. **Strict intraday — zero overnight risk.** |
| Stops | Sell losers immediately on live monitoring (every 15 min) |
| Sizing | Equal weight (today); will move to conviction-weighted (top-3 = 2×) |
| **Current P&L** | **~60% win rate (6W/4L), ~2% net daily** |
| **Target** | **Lift win rate to 70%+ by eliminating 1–2 of the 4 daily losers** |
| Capital flow | No averaging down. Cut losers, ride winners. Add new positions = new picks (not pyramiding losers) |
| Secondary track | Weekly: hold ~5d for high-potential setups (catalyst ≥ 7, Stage 1–3, WTS ≥ 12) |

Constraint: **FMP API key is IP-whitelisted to office IP.** Code must be
machine-portable; runtime location matters.

---

## How S888 directly serves this strategy

### Goal 1 — Lift the daily win rate (the 60→70% problem)

The **4 losers per day** are the leverage point. Per our analysis, the most
likely loser patterns are:

| Loser pattern | S888 lever |
|---|---|
| Stock already up ≥ 8% at appearance (gap-fades) | Daily ranking sort + breakout component — needs filter |
| Catalyst is "pump_unclear" or "technical_only" | **Catalyst score 1–10 (§4)** — hard-block ≤ 5 |
| ER in next 1–3 days | **⚠️ earnings tag (§5c)** — currently informational, should *block* in the loser-prone window |
| Thin volume / wide spread | Universe pre-screen `avg_vol ≥ 200k`, `price ≥ $2` (§3.4) |
| Stage 4 weakness | DTS still ranks them; weekly hard-blocks them |
| Same sector concentration | Not yet in spec — candidate enhancement after `trade_logger` data |

`trade_logger.py` (already committed at repo root) is the **data
collection** that turns hunches into filters. After ~14 sessions of
logging, `python trade_logger.py analyze` ranks which of these (and
others) would have lifted expectancy most.

### Goal 2 — Surface highest-conviction names with **two** signals

A ticker that appears in **BOTH** the Daily ranking AND the Weekly
ranking (📆 cross-reference emoji, §8.3) is the strongest conviction
signal in the system — *intraday momentum* + *swing-quality setup* +
*catalyst* + *analyst alignment* all confirmed. These are the names that
should get larger position sizing in the user's workflow.

### Goal 3 — Separate small-cap from large-cap behavior

Spec §8.5 documents what the user already knows from live trading:
small-caps swing 5–50%, large-caps swing 1–8%, and merging them into
one ranking lets micro-cap pumps drown out clean large-cap setups.
**Two independent daily rankings** preserves the signal in each.

### Goal 4 — Weekly track = high-potential swing tier

For trades worth holding > 1 day: WTS ≥ 12 (out of 19) + catalyst ≥ 7
+ Stage ∈ {1,2,3} + breakout confirmation. Skips Stage 4 entirely. Sends
no message if 0 qualify — no notification spam.

---

## Architectural decisions locked in

1. **READ-ONLY.** S888 does not place trades, compute sizes, or trigger
   alerts beyond ranking. All execution stays in the user's hands.
2. **Three independent rankings, three Telegram messages** (default).
   `TELEGRAM_COMBINED` config can merge them later if desired.
3. **State diffing per-track** (🆕/👋) — user sees what entered/left
   each ranking between scans.
4. **AAS is bullish-only** (downgrades ignored, not penalized). Stock
   ranking by gainers already prices in bearish views; double-counting
   noises the signal.
5. **Stage 4 hard-blocked on weekly, allowed on daily.** Intraday
   momentum is independent of weekly trend regime.
6. **One ticker = one cap bucket.** Never appears in both daily lists.
7. **Earnings warning is cross-cutting** — tagged on every ranking that
   surfaces the ticker.
8. **Caching strategy** matches §11 — analyst pulled once/session,
   news every 30 min, bars every 10 min, calendar once/session.
9. **FMP Premium plan assumed** (750 req/min, 25k/day). Free tier won't
   sustain the ~14k req/session load.

---

## Credential reuse (§14)

S888 uses the **same** FMP API key, Telegram bot token, and chat ID as
the existing S3 project. No new accounts, no `@BotFather` flow.
Messages prefixed `📅 DAILY` / `📆 WEEKLY` to distinguish from S3 alerts
in the same chat.

---

## Build status snapshot

| Stage | Modules | Status |
|---|---|---|
| 1 | config, cache, FMP client, YF client, universe, cap categorizer | ✅ committed, 17 tests green |
| 2 | news (FMP + YF), Jaccard dedupe, catalyst (1–10), earnings calendar, AAS (0–3) | ⏳ next |
| 3 | Indicators (VWAP/EMA/RSI/CMF/ADX/Vol/OBV/Weinstein), breakout levels (ORB/PDH/PMH/20d/52w/8w high) | ⏳ |
| 4 | DTS (28+7+3=38), WTS (10+6+3=19), daily ranker (cap-segmented), weekly ranker (filtered) | ⏳ |
| 5 | Earnings tag, state diffing, three Telegram formatters + senders | ⏳ |
| 6 | Orchestrator (triple-track pipeline) + APScheduler | ⏳ |

**Each stage commits independently, with passing tests, before moving to
the next.** Total remaining estimate: ~6 hours of focused work split
across 4–5 more sessions.
