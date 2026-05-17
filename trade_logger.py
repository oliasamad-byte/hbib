"""
S888 trade logger + loser-pattern analyzer.

Two tables:
  picks   — every ticker S888 surfaces (call log_pick() in your scan loop)
  trades  — actual trades you took (call log_trade() after the trade closes)

After ~2 weeks of data:  python trade_logger.py analyze
                          → ranked list of filters that would have cut losers
                          while keeping winners.

CLI:
  python trade_logger.py log-pick   --date 2026-05-17 --scan 18:30 --rank 3 \
                                    --ticker UXIN --dts 31 --cat 8 --aas 2 \
                                    --cap small --entry 2.54 --gain 6.3
  python trade_logger.py log-trade  --date 2026-05-17 --ticker UXIN \
                                    --entry-time 18:32 --entry 2.55 \
                                    --exit-time 22:00 --exit 2.60 --size 1000
  python trade_logger.py export                # write trades.csv
  python trade_logger.py analyze               # loser-pattern report
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from collections import defaultdict
from datetime import date as Date, datetime
from pathlib import Path
from statistics import mean, median

DB_PATH = Path(__file__).with_name("s888_trades.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS picks (
  date          TEXT NOT NULL,    -- YYYY-MM-DD
  scan_time     TEXT NOT NULL,    -- HH:MM (GST)
  rank          INTEGER NOT NULL, -- 1..20
  ticker        TEXT NOT NULL,
  dts           REAL,             -- 0..38
  catalyst      REAL,             -- 1..10
  aas           REAL,             -- 0..3
  cap           TEXT,             -- small/mid/large/mega
  entry_price   REAL,             -- price when surfaced
  gain_at_appear REAL,            -- % intraday change at surface time
  PRIMARY KEY (date, scan_time, ticker)
);

CREATE TABLE IF NOT EXISTS trades (
  date          TEXT NOT NULL,
  ticker        TEXT NOT NULL,
  entry_time    TEXT NOT NULL,
  entry_price   REAL NOT NULL,
  exit_time     TEXT,
  exit_price    REAL,
  position_usd  REAL,
  notes         TEXT,
  PRIMARY KEY (date, ticker, entry_time)
);

CREATE INDEX IF NOT EXISTS idx_picks_ticker_date ON picks(ticker, date);
"""


# ---------- DB helpers ----------

def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.executescript(SCHEMA)
    return c


def log_pick(date: str, scan_time: str, rank: int, ticker: str,
             dts: float, catalyst: float, aas: float, cap: str,
             entry_price: float, gain_at_appear: float) -> None:
    """Call this from S888 every scan, for every ranked ticker."""
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO picks VALUES (?,?,?,?,?,?,?,?,?,?)",
            (date, scan_time, rank, ticker.upper(), dts, catalyst, aas,
             cap, entry_price, gain_at_appear),
        )


def log_trade(date: str, ticker: str, entry_time: str, entry_price: float,
              exit_time: str | None = None, exit_price: float | None = None,
              position_usd: float | None = None, notes: str = "") -> None:
    """Call after a trade closes (or partial — exit_time/exit_price optional)."""
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO trades VALUES (?,?,?,?,?,?,?,?)",
            (date, ticker.upper(), entry_time, entry_price,
             exit_time, exit_price, position_usd, notes),
        )


# ---------- export ----------

def export_csv(out: Path = Path("trades.csv")) -> int:
    with conn() as c:
        rows = c.execute("""
            SELECT t.date, t.ticker, t.entry_time, t.entry_price,
                   t.exit_time, t.exit_price, t.position_usd, t.notes,
                   p.rank, p.dts, p.catalyst, p.aas, p.cap, p.gain_at_appear
              FROM trades t
              LEFT JOIN picks p
                ON p.ticker = t.ticker AND p.date = t.date
             ORDER BY t.date, t.entry_time
        """).fetchall()
    cols = ["date","ticker","entry_time","entry_price","exit_time","exit_price",
            "position_usd","notes","rank","dts","catalyst","aas","cap","gain_at_appear"]
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    return len(rows)


# ---------- analyzer ----------

def _trade_return_pct(row: sqlite3.Row) -> float | None:
    ep, xp = row["entry_price"], row["exit_price"]
    if ep is None or xp is None or ep <= 0:
        return None
    return (xp / ep - 1.0) * 100.0


def analyze() -> None:
    with conn() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("""
            SELECT t.*, p.rank, p.dts, p.catalyst, p.aas, p.cap, p.gain_at_appear
              FROM trades t
              LEFT JOIN picks p
                ON p.ticker = t.ticker AND p.date = t.date
             WHERE t.exit_price IS NOT NULL
        """).fetchall()

    if not rows:
        print("No closed trades yet. Log some with `log-trade` and re-run.")
        return

    closed = []
    for r in rows:
        ret = _trade_return_pct(r)
        if ret is None:
            continue
        closed.append({
            "date": r["date"], "ticker": r["ticker"], "ret": ret,
            "rank": r["rank"], "dts": r["dts"], "catalyst": r["catalyst"],
            "aas": r["aas"], "cap": r["cap"],
            "gain_at_appear": r["gain_at_appear"],
            "dow": datetime.strptime(r["date"], "%Y-%m-%d").strftime("%a"),
        })

    n = len(closed)
    winners = [t for t in closed if t["ret"] > 0]
    losers  = [t for t in closed if t["ret"] <= 0]
    wr = len(winners) / n if n else 0.0
    print(f"\n=== TRADE STATS (n={n}) ===")
    print(f"  win rate           {wr*100:5.1f}%")
    print(f"  mean return        {mean(t['ret'] for t in closed):+5.2f}%")
    print(f"  median return      {median(t['ret'] for t in closed):+5.2f}%")
    if winners and losers:
        avg_w = mean(t["ret"] for t in winners)
        avg_l = mean(t["ret"] for t in losers)
        print(f"  avg win / loss     {avg_w:+5.2f}% / {avg_l:+5.2f}%")
        print(f"  expectancy         {(wr*avg_w + (1-wr)*avg_l):+5.2f}% / trade")

    if len(losers) < 5:
        print(f"\n(Only {len(losers)} losers — need ≥5 for pattern analysis. "
              f"Keep logging.)")
        return

    print(f"\n=== LOSER PATTERN ANALYSIS (n_loss={len(losers)}, n_win={len(winners)}) ===")
    print("Each candidate filter shows: % of losers removed, % of winners removed, "
          "net effect on expectancy.\n")

    rules = [
        ("gain_at_appear ≥ 8%",  lambda t: (t["gain_at_appear"] or 0) >= 8),
        ("gain_at_appear ≥ 12%", lambda t: (t["gain_at_appear"] or 0) >= 12),
        ("catalyst ≤ 5",         lambda t: (t["catalyst"] or 10) <= 5),
        ("dts < 22",             lambda t: (t["dts"] or 99) < 22),
        ("aas == 0",             lambda t: (t["aas"] or 99) == 0),
        ("rank ≥ 8",             lambda t: (t["rank"] or 0) >= 8),
        ("cap == small",         lambda t: t["cap"] == "small"),
        ("Friday",               lambda t: t["dow"] == "Fri"),
        ("Monday",               lambda t: t["dow"] == "Mon"),
    ]

    cur_exp = (wr * mean(t["ret"] for t in winners)
               + (1 - wr) * mean(t["ret"] for t in losers)) if (winners and losers) else 0.0

    print(f"{'rule':<24}{'cuts losers':>14}{'cuts winners':>14}{'Δ expectancy':>15}")
    print("-" * 67)
    scored = []
    for name, pred in rules:
        lost_cut = sum(1 for t in losers if pred(t))
        won_cut  = sum(1 for t in winners if pred(t))
        kept = [t for t in closed if not pred(t)]
        if not kept:
            continue
        kept_winners = [t for t in kept if t["ret"] > 0]
        kept_losers  = [t for t in kept if t["ret"] <= 0]
        new_wr = len(kept_winners) / len(kept)
        new_exp = (new_wr * mean(t["ret"] for t in kept_winners)
                   + (1 - new_wr) * mean(t["ret"] for t in kept_losers)) \
                  if (kept_winners and kept_losers) else 0.0
        delta = new_exp - cur_exp
        scored.append((delta, name, lost_cut, won_cut))
        pct_l = lost_cut / len(losers)  * 100
        pct_w = won_cut  / len(winners) * 100 if winners else 0
        print(f"{name:<24}{lost_cut:>4} ({pct_l:5.1f}%){won_cut:>4} ({pct_w:5.1f}%)"
              f"{delta:>+12.2f}%")

    scored.sort(reverse=True)
    print()
    if scored and scored[0][0] > 0.05:
        d, n, lc, wc = scored[0]
        print(f"→ TOP FILTER: '{n}' lifts expectancy by {d:+.2f}% / trade "
              f"(removes {lc} losers, {wc} winners).")
    else:
        print("→ No filter shows a meaningful lift yet. Either keep logging "
              "(more data) or your losers don't have a simple pattern.")


# ---------- CLI ----------

def _today() -> str:
    return Date.today().isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(prog="trade_logger")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("log-pick", help="record an S888-surfaced ticker")
    p.add_argument("--date", default=_today())
    p.add_argument("--scan", required=True, help="HH:MM (e.g. 18:30)")
    p.add_argument("--rank", type=int, required=True)
    p.add_argument("--ticker", required=True)
    p.add_argument("--dts", type=float, required=True)
    p.add_argument("--cat", type=float, required=True, help="catalyst score 1-10")
    p.add_argument("--aas", type=float, default=0.0)
    p.add_argument("--cap", choices=["small","mid","large","mega"], required=True)
    p.add_argument("--entry", type=float, required=True, help="price when surfaced")
    p.add_argument("--gain", type=float, required=True, help="% intraday at surface")

    t = sub.add_parser("log-trade", help="record an actual trade")
    t.add_argument("--date", default=_today())
    t.add_argument("--ticker", required=True)
    t.add_argument("--entry-time", required=True, help="HH:MM")
    t.add_argument("--entry", type=float, required=True)
    t.add_argument("--exit-time", default=None)
    t.add_argument("--exit", type=float, default=None, dest="exit_price")
    t.add_argument("--size", type=float, default=None, dest="size",
                   help="position size in USD")
    t.add_argument("--notes", default="")

    sub.add_parser("export", help="dump trades.csv")
    sub.add_parser("analyze", help="loser-pattern report")

    args = ap.parse_args()

    if args.cmd == "log-pick":
        log_pick(args.date, args.scan, args.rank, args.ticker, args.dts,
                 args.cat, args.aas, args.cap, args.entry, args.gain)
        print(f"logged pick: {args.date} {args.scan} #{args.rank} {args.ticker}")
    elif args.cmd == "log-trade":
        log_trade(args.date, args.ticker, args.entry_time, args.entry,
                  args.exit_time, args.exit_price, args.size, args.notes)
        print(f"logged trade: {args.date} {args.ticker} @ {args.entry}")
    elif args.cmd == "export":
        n = export_csv()
        print(f"wrote trades.csv ({n} rows)")
    elif args.cmd == "analyze":
        analyze()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
