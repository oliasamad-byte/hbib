"""S888 orchestrator — triple-track pipeline + APScheduler.

Run once:    python -m s888.orchestrator --once
Scheduled:   python -m s888.orchestrator       (5:30 PM – 10:30 PM GST)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime
from typing import Any

from . import (
    analyst_activity, breakout_levels, cache, catalyst, earnings_calendar,
    mtf, news_fmp, news_yf, news_merge, state, telegram_format,
    tech_score_daily, tech_score_weekly, universe,
)
from .config import CFG
from .indicators import weinstein_stage
from .ranker_daily import ScoredTicker, rank_both
from .ranker_weekly import rank_weekly
from .utils.fmp_client import FMPClient
from .utils.telegram_client import send_message

log = logging.getLogger(__name__)


# ---------- trade-logger bridge ----------

def _log_picks_to_trade_logger(scan_ts: str, picks: list) -> None:
    """Log every ranked pick to ../trade_logger.py's SQLite DB.

    Best-effort: silently skips if trade_logger isn't reachable. The
    user can drop the trade_logger.py at repo root or any sys.path
    location to enable this.
    """
    try:
        import sys
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        import trade_logger as tl
    except Exception as e:
        log.debug("trade_logger not loaded: %s", e)
        return
    date_str = scan_ts[:10]
    scan_hm = scan_ts[11:16]
    for i, t in enumerate(picks, 1):
        try:
            tl.log_pick(
                date=date_str,
                scan_time=scan_hm,
                rank=i,
                ticker=t.ticker,
                dts=float(t.dts_total),
                catalyst=float(t.catalyst_score),
                aas=float(t.dts_analyst),
                cap=t.cap,
                entry_price=float(t.price),
                gain_at_appear=float(t.change_pct or 0.0),
            )
        except Exception as e:
            log.warning("trade_logger.log_pick failed for %s: %s", t.ticker, e)
    log.info("trade_logger: logged %d picks for %s", len(picks), date_str)


# ---------- pipeline ----------

async def run_once(scan_idx: int | None = None,
                   scan_total: int | None = None) -> None:
    scan_ts = datetime.utcnow().isoformat(timespec="seconds")
    log.info("scan starting @ %s", scan_ts)
    today = date.today()

    async with FMPClient() as fmp:
        # Step 1 — Universe
        uni = await universe.build_universe(fmp)
        log.info("universe: %d tickers (S/M/L/Mega = %d/%d/%d/%d)",
                 len(uni),
                 sum(1 for r in uni if r["cap"] == "small"),
                 sum(1 for r in uni if r["cap"] == "mid"),
                 sum(1 for r in uni if r["cap"] == "large"),
                 sum(1 for r in uni if r["cap"] == "mega"))
        if not uni:
            log.warning("empty universe — skipping scan")
            return
        cache.save_universe(scan_ts, uni)

        # Step 2 — Calendars + per-ticker enrichment
        await earnings_calendar.refresh_calendar(fmp)
        tickers = [r["ticker"] for r in uni]

        # News (concurrent pull, both sources)
        log.info("pulling news for %d tickers...", len(tickers))
        fmp_news, yf_news = await asyncio.gather(
            news_fmp.pull_many(fmp, tickers, limit=10),
            news_yf.pull_many(tickers, limit=10),
        )
        merged_news = news_merge.merge_per_ticker(fmp_news, yf_news, threshold=0.7)
        er_dates = earnings_calendar.er_dates_map(tickers)

        # Catalyst per ticker
        catalysts = {t: catalyst.classify(t, merged_news.get(t, []),
                                          er_dates=er_dates, today=today)
                     for t in tickers}

        # AAS per ticker (parallel, cached daily)
        log.info("pulling analyst grades...")
        aas_results = await asyncio.gather(
            *[analyst_activity.fetch_aas(fmp, t, today=today) for t in tickers]
        )
        aas_map = {t: r for t, r in zip(tickers, aas_results)}

        # Step 3+4 — MTF bars + scoring per ticker
        log.info("fetching bars + scoring %d tickers...", len(tickers))
        scored: list[ScoredTicker] = []
        stages: dict[str, int] = {}
        daily_score_map: dict[str, tech_score_daily.ScoreResult] = {}
        wts_score_map: dict[str, tech_score_weekly.WeeklyScoreResult] = {}

        # Limit concurrency by chunking
        sem = asyncio.Semaphore(CFG.fmp_concurrent_requests)
        async def _score_one(row: dict) -> ScoredTicker | None:
            async with sem:
                try:
                    bars = await mtf.fetch_all(fmp, row["ticker"])
                except Exception as e:
                    log.warning("bars fetch %s failed: %s", row["ticker"], e)
                    return None
            price = row.get("price") or 0.0
            if not bars.get("1m", None).empty if bars.get("1m") is not None else True:
                if bars.get("1m") is not None and not bars["1m"].empty:
                    price = float(bars["1m"]["close"].iloc[-1])
            levels = breakout_levels.all_levels(
                bars.get("daily", None) or bars["daily"],
                bars.get("weekly", None) or bars["weekly"],
                bars.get("5m"), bars.get("1m"),
            )
            aas_val = aas_map[row["ticker"]].score
            d = tech_score_daily.compute_dts(bars, price, levels, aas=aas_val)
            w = tech_score_weekly.compute_wts(bars, levels, aas=aas_val)
            stages[row["ticker"]] = w.stage
            daily_score_map[row["ticker"]] = d
            wts_score_map[row["ticker"]] = w
            cat = catalysts[row["ticker"]]
            return ScoredTicker(
                ticker=row["ticker"], source=row["source"], cap=row["cap"],
                price=price, change_pct=row.get("change_pct") or 0.0,
                market_cap=row.get("market_cap") or 0.0,
                dts_total=d.total, dts_base=d.base, dts_breakout=d.breakout,
                dts_analyst=d.analyst, wts_total=w.total,
                catalyst_score=cat.score, catalyst_category=cat.category,
                catalyst_evidence=cat.evidence,
                breakdown=d.breakdown, breakout_breakdown=d.breakout_breakdown,
            )

        tasks = [_score_one(r) for r in uni]
        results = await asyncio.gather(*tasks)
        scored = [s for s in results if s is not None]
        log.info("scored: %d tickers", len(scored))

    # Step 5 — Rankings
    small, mlm = rank_both(scored, top_n=CFG.daily_top_n_list)
    weekly = rank_weekly(scored, stages, top_n=CFG.weekly_top_n)
    log.info("rankings: small=%d, mlm=%d, weekly=%d",
             len(small), len(mlm), len(weekly))

    weekly_set = {t.ticker for t in weekly}

    # Daily-rank cross-reference for weekly (which daily ranking + position)
    daily_ranks = {}
    for i, t in enumerate(small, 1):
        daily_ranks[t.ticker] = f"Small #{i}"
    for i, t in enumerate(mlm, 1):
        daily_ranks[t.ticker] = f"M/L/M #{i}"

    # State diffs (run BEFORE commit)
    s_added, s_dropped = state.diff("daily_small", [t.ticker for t in small])
    m_added, m_dropped = state.diff("daily_mlm",   [t.ticker for t in mlm])
    w_added, w_dropped = state.diff("weekly",      [t.ticker for t in weekly])

    # Save rankings to audit table
    cache.save_rankings(scan_ts, "daily_small",
                        [(i+1, t.ticker, t.dts_total,
                          {"base": t.dts_base, "breakout": t.dts_breakout,
                           "analyst": t.dts_analyst}) for i, t in enumerate(small)])
    cache.save_rankings(scan_ts, "daily_mlm",
                        [(i+1, t.ticker, t.dts_total,
                          {"base": t.dts_base, "breakout": t.dts_breakout,
                           "analyst": t.dts_analyst}) for i, t in enumerate(mlm)])
    cache.save_rankings(scan_ts, "weekly",
                        [(i+1, t.ticker, t.wts_total,
                          {"stage": stages.get(t.ticker, 0)})
                         for i, t in enumerate(weekly)])

    # Trade-logger hook: log every surfaced ticker so the loser-pattern
    # analyzer has data to work with. Safe to call — trade_logger lives
    # at repo root, only logs if importable.
    _log_picks_to_trade_logger(scan_ts, small + mlm)

    # Format + send
    if small or CFG.daily_small_send_if_empty:
        msg = telegram_format.format_daily_small(
            small, daily_score_map, weekly_set, len(uni),
            s_added, s_dropped,
            n_detailed=CFG.daily_top_n_detailed,
            scan_idx=scan_idx, scan_total=scan_total)
        await send_message(msg)
    if mlm or CFG.daily_midlargemega_send_if_empty:
        msg = telegram_format.format_daily_mlm(
            mlm, daily_score_map, weekly_set, len(uni),
            m_added, m_dropped,
            n_detailed=CFG.daily_top_n_detailed,
            scan_idx=scan_idx, scan_total=scan_total)
        await send_message(msg)
    if weekly or CFG.weekly_send_if_empty:
        msg = telegram_format.format_weekly(
            weekly, wts_score_map, daily_ranks,
            w_added, w_dropped,
            scan_idx=scan_idx, scan_total=scan_total)
        if msg:
            await send_message(msg)

    # Commit state for next scan
    state.commit("daily_small", [t.ticker for t in small])
    state.commit("daily_mlm",   [t.ticker for t in mlm])
    state.commit("weekly",      [t.ticker for t in weekly])

    log.info("scan complete: %s", scan_ts)


def _setup_logging(log_dir) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / f"s888-{date.today().isoformat()}.log"
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO, format=fmt,
        handlers=[logging.FileHandler(logfile), logging.StreamHandler(sys.stderr)],
    )


def schedule(loop_forever: bool = True) -> None:
    """Start APScheduler to run scans every SCAN_INTERVAL_MIN during the
    window. Single in-process scheduler."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    _setup_logging(CFG.log_dir)
    sched = BlockingScheduler()
    start_h, start_m = (int(x) for x in CFG.scan_start_gst.split(":"))
    end_h, end_m = (int(x) for x in CFG.scan_end_gst.split(":"))
    interval = CFG.scan_interval_min

    # cron with minute=*/N is simplest; window enforcement is inside the job.
    def _job() -> None:
        now = datetime.now()
        hm_now = now.hour * 60 + now.minute
        start_min = start_h * 60 + start_m
        end_min = end_h * 60 + end_m
        if not (start_min <= hm_now <= end_min):
            return
        try:
            asyncio.run(run_once())
        except Exception as e:
            log.exception("scan failed: %s", e)

    sched.add_job(_job, CronTrigger(minute=f"*/{interval}"))
    log.info("scheduler armed: every %dmin between %s and %s GST (clock=%s)",
             interval, CFG.scan_start_gst, CFG.scan_end_gst, CFG.master_clock)
    if loop_forever:
        try:
            sched.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("scheduler stopped by user")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="Run a single scan now and exit")
    args = ap.parse_args()
    _setup_logging(CFG.log_dir)
    if args.once:
        asyncio.run(run_once())
        return 0
    schedule()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
