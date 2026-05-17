#!/usr/bin/env python3
"""Small CLI wrapper around the Financial Modeling Prep (FMP) API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests
from dotenv import load_dotenv

BASE_URL = "https://financialmodelingprep.com/api/v3"


class FMPError(RuntimeError):
    pass


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        raise FMPError(
            "FMP_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    params = {**(params or {}), "apikey": api_key}
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    if resp.status_code != 200:
        raise FMPError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if isinstance(data, dict) and "Error Message" in data:
        raise FMPError(data["Error Message"])
    return data


def quote(symbol: str) -> Any:
    return _get(f"/quote/{symbol.upper()}")


def history(symbol: str, date_from: str | None, date_to: str | None) -> Any:
    params: dict[str, Any] = {}
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to
    return _get(f"/historical-price-full/{symbol.upper()}", params)


def income(symbol: str, period: str, limit: int) -> Any:
    return _get(
        f"/income-statement/{symbol.upper()}",
        {"period": period, "limit": limit},
    )


def balance(symbol: str, period: str, limit: int) -> Any:
    return _get(
        f"/balance-sheet-statement/{symbol.upper()}",
        {"period": period, "limit": limit},
    )


def cashflow(symbol: str, period: str, limit: int) -> Any:
    return _get(
        f"/cash-flow-statement/{symbol.upper()}",
        {"period": period, "limit": limit},
    )


def profile(symbol: str) -> Any:
    return _get(f"/profile/{symbol.upper()}")


def news(symbol: str | None, limit: int) -> Any:
    params: dict[str, Any] = {"limit": limit}
    if symbol:
        params["tickers"] = symbol.upper()
    return _get("/stock_news", params)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fmp", description="FMP API CLI")
    sub = p.add_subparsers(dest="command", required=True)

    q = sub.add_parser("quote", help="Real-time quote for a symbol")
    q.add_argument("symbol")

    h = sub.add_parser("history", help="Historical daily OHLCV")
    h.add_argument("symbol")
    h.add_argument("--from", dest="date_from", help="YYYY-MM-DD")
    h.add_argument("--to", dest="date_to", help="YYYY-MM-DD")

    for name, fn_help in [
        ("income", "Income statement"),
        ("balance", "Balance sheet"),
        ("cashflow", "Cash flow statement"),
    ]:
        s = sub.add_parser(name, help=fn_help)
        s.add_argument("symbol")
        s.add_argument(
            "--period", choices=["annual", "quarter"], default="annual"
        )
        s.add_argument("--limit", type=int, default=5)

    pr = sub.add_parser("profile", help="Company profile")
    pr.add_argument("symbol")

    n = sub.add_parser("news", help="Stock news (optionally for a symbol)")
    n.add_argument("symbol", nargs="?", default=None)
    n.add_argument("--limit", type=int, default=20)

    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)

    dispatch = {
        "quote": lambda a: quote(a.symbol),
        "history": lambda a: history(a.symbol, a.date_from, a.date_to),
        "income": lambda a: income(a.symbol, a.period, a.limit),
        "balance": lambda a: balance(a.symbol, a.period, a.limit),
        "cashflow": lambda a: cashflow(a.symbol, a.period, a.limit),
        "profile": lambda a: profile(a.symbol),
        "news": lambda a: news(a.symbol, a.limit),
    }
    try:
        result = dispatch[args.command](args)
    except FMPError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except requests.RequestException as e:
        print(f"network error: {e}", file=sys.stderr)
        return 2

    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
