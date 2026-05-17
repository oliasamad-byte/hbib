"""SQLite cache + state store. Thin layer; no ORM."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .config import CFG

DB_PATH = CFG.data_dir / "s888_cache.db"

SCHEMA = """
-- One row per (ticker, scan_ts) — full snapshot for audit.
CREATE TABLE IF NOT EXISTS universe (
  scan_ts        TEXT NOT NULL,
  ticker         TEXT NOT NULL,
  source         TEXT NOT NULL,             -- "Y" or "F"
  cap            TEXT NOT NULL,             -- small/mid/large/mega
  market_cap     REAL,
  price          REAL,
  change_pct     REAL,
  avg_volume     REAL,
  PRIMARY KEY (scan_ts, ticker)
);
CREATE INDEX IF NOT EXISTS idx_universe_ticker ON universe(ticker);

-- Earnings calendar, refreshed once per session.
CREATE TABLE IF NOT EXISTS earnings_upcoming (
  ticker      TEXT NOT NULL,
  er_date     TEXT NOT NULL,
  er_timing   TEXT,                          -- BMO / AMC / DMH
  pulled_at   TEXT NOT NULL,
  PRIMARY KEY (ticker, er_date)
);

-- Analyst Activity Score cache (per day per ticker).
CREATE TABLE IF NOT EXISTS analyst_activity (
  ticker             TEXT NOT NULL,
  pulled_date        TEXT NOT NULL,         -- YYYY-MM-DD
  raw_actions        TEXT,                  -- JSON
  aas_score          REAL NOT NULL,
  bullish_counts     TEXT,                  -- JSON
  ignored_counts     TEXT,                  -- JSON
  PRIMARY KEY (ticker, pulled_date)
);

-- Last sent ranking per track (for 🆕/👋 diffing).
CREATE TABLE IF NOT EXISTS prior_rankings (
  track       TEXT NOT NULL,                -- daily_small / daily_mlm / weekly
  tickers     TEXT NOT NULL,                -- JSON list
  sent_at     TEXT NOT NULL,
  PRIMARY KEY (track)
);

-- Full ranking output per scan (audit trail).
CREATE TABLE IF NOT EXISTS rankings (
  scan_ts     TEXT NOT NULL,
  track       TEXT NOT NULL,
  rank        INTEGER NOT NULL,
  ticker      TEXT NOT NULL,
  score       REAL NOT NULL,
  breakdown   TEXT,                         -- JSON
  PRIMARY KEY (scan_ts, track, rank)
);

-- News cache (per ticker, refreshed per spec §11).
CREATE TABLE IF NOT EXISTS news_cache (
  ticker      TEXT NOT NULL,
  pulled_at   TEXT NOT NULL,
  source      TEXT NOT NULL,                -- "fmp_news" / "fmp_pr" / "yf"
  payload     TEXT NOT NULL,                -- JSON list
  PRIMARY KEY (ticker, source)
);
"""


def init_db() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, isolation_level=None)  # autocommit
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


# ---------- universe ----------

def save_universe(scan_ts: str, rows: Iterable[dict[str, Any]]) -> int:
    n = 0
    with conn() as c:
        for r in rows:
            c.execute(
                "INSERT OR REPLACE INTO universe VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?)",
                (scan_ts, r["ticker"], r["source"], r["cap"],
                 r.get("market_cap"), r.get("price"),
                 r.get("change_pct"), r.get("avg_volume")),
            )
            n += 1
    return n


def load_universe(scan_ts: str) -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute(
            "SELECT * FROM universe WHERE scan_ts=? ORDER BY change_pct DESC",
            (scan_ts,),
        ).fetchall()


# ---------- earnings ----------

def save_earnings(rows: Iterable[dict[str, Any]]) -> int:
    n = 0
    now = datetime.utcnow().isoformat(timespec="seconds")
    with conn() as c:
        for r in rows:
            c.execute(
                "INSERT OR REPLACE INTO earnings_upcoming VALUES (?, ?, ?, ?)",
                (r["ticker"], r["er_date"], r.get("er_timing"), now),
            )
            n += 1
    return n


def get_earnings(ticker: str) -> sqlite3.Row | None:
    with conn() as c:
        return c.execute(
            "SELECT * FROM earnings_upcoming WHERE ticker=? "
            "ORDER BY er_date ASC LIMIT 1",
            (ticker,),
        ).fetchone()


# ---------- analyst ----------

def save_analyst(ticker: str, pulled_date: str, raw: list,
                 aas: float, bull: dict, ignored: dict) -> None:
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO analyst_activity VALUES (?, ?, ?, ?, ?, ?)",
            (ticker, pulled_date, json.dumps(raw), aas,
             json.dumps(bull), json.dumps(ignored)),
        )


def get_analyst(ticker: str, pulled_date: str) -> sqlite3.Row | None:
    with conn() as c:
        return c.execute(
            "SELECT * FROM analyst_activity WHERE ticker=? AND pulled_date=?",
            (ticker, pulled_date),
        ).fetchone()


# ---------- prior rankings (state diff) ----------

def save_prior_ranking(track: str, tickers: list[str]) -> None:
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO prior_rankings VALUES (?, ?, ?)",
            (track, json.dumps(tickers),
             datetime.utcnow().isoformat(timespec="seconds")),
        )


def get_prior_ranking(track: str) -> list[str]:
    with conn() as c:
        row = c.execute(
            "SELECT tickers FROM prior_rankings WHERE track=?", (track,)
        ).fetchone()
    return json.loads(row["tickers"]) if row else []


def diff_prior(track: str, current: list[str]) -> tuple[list[str], list[str]]:
    """Return (added_now, dropped_since_last). 🆕 / 👋."""
    prior = set(get_prior_ranking(track))
    cur_set = set(current)
    return sorted(cur_set - prior), sorted(prior - cur_set)


# ---------- rankings audit ----------

def save_rankings(scan_ts: str, track: str,
                  entries: Iterable[tuple[int, str, float, dict]]) -> None:
    with conn() as c:
        for rank, ticker, score, breakdown in entries:
            c.execute(
                "INSERT OR REPLACE INTO rankings VALUES (?, ?, ?, ?, ?, ?)",
                (scan_ts, track, rank, ticker, score, json.dumps(breakdown)),
            )


# Initialize on import — safe (CREATE TABLE IF NOT EXISTS).
init_db()
