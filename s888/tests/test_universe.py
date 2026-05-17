"""Universe pull is end-to-end network — test the offline logic only:
merge + dedupe + prescreen + cap-tag. The network adapters are mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from s888 import universe


@pytest.mark.asyncio
async def test_yf_wins_on_duplicate():
    yf_rows = [
        {"symbol": "AAPL", "price": 200, "change_pct": 3.0,
         "market_cap": 3.5e12, "avg_volume": 5e7, "name": "Apple"},
    ]
    fmp_dup = [
        {"symbol": "AAPL", "price": 199, "changesPercentage": 2.5,
         "marketCap": 3.5e12, "avgVolume": 5e7, "name": "Apple"},
        {"symbol": "PIII", "price": 5.0, "changesPercentage": 50.0,
         "marketCap": 4e8, "avgVolume": 3e6, "name": "Piii"},
    ]

    class FakeFMP:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def gainers(self): return fmp_dup
        async def screener(self, **kw): return []

    with patch("s888.universe.day_gainers", AsyncMock(return_value=yf_rows)):
        with patch("s888.universe.FMPClient", FakeFMP):
            rows = await universe.build_universe()
    by_sym = {r["ticker"]: r for r in rows}
    assert by_sym["AAPL"]["source"] == "Y"
    assert by_sym["PIII"]["source"] == "F"


@pytest.mark.asyncio
async def test_prescreen_drops_thin_and_low_change():
    yf_rows = [
        {"symbol": "GOOD", "price": 10, "change_pct": 5.0,
         "market_cap": 1e9, "avg_volume": 1e6, "name": "Good"},
        {"symbol": "CHEAP", "price": 0.5, "change_pct": 8.0,        # price < min
         "market_cap": 1e9, "avg_volume": 1e6, "name": "Cheap"},
        {"symbol": "THIN", "price": 10, "change_pct": 5.0,
         "market_cap": 1e9, "avg_volume": 100, "name": "Thin"},     # vol < min
        {"symbol": "FLAT", "price": 10, "change_pct": 0.5,           # chg% < 2.5
         "market_cap": 1e9, "avg_volume": 1e6, "name": "Flat"},
    ]

    class FakeFMP:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def gainers(self): return []
        async def screener(self, **kw): return []

    with patch("s888.universe.day_gainers", AsyncMock(return_value=yf_rows)):
        with patch("s888.universe.FMPClient", FakeFMP):
            rows = await universe.build_universe()
    assert [r["ticker"] for r in rows] == ["GOOD"]


@pytest.mark.asyncio
async def test_universe_max_respected():
    many = [{"symbol": f"T{i:03d}", "price": 10, "change_pct": float(50 - i),
             "market_cap": 1e9, "avg_volume": 1e6, "name": f"t{i}"}
            for i in range(300)]

    class FakeFMP:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def gainers(self): return []
        async def screener(self, **kw): return []

    with patch("s888.universe.day_gainers", AsyncMock(return_value=many)):
        with patch("s888.universe.FMPClient", FakeFMP):
            rows = await universe.build_universe()
    from s888.config import CFG
    assert len(rows) <= CFG.universe_max
    # Sorted by change_pct desc, so T000 (chg 50) is first
    assert rows[0]["ticker"] == "T000"
