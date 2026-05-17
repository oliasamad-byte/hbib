from datetime import datetime

from s888 import cache


def _ts() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def test_save_and_load_universe():
    ts = _ts()
    rows = [
        {"ticker": "AAPL", "source": "Y", "cap": "mega",
         "market_cap": 3.5e12, "price": 200.0, "change_pct": 1.2, "avg_volume": 5e7},
        {"ticker": "PIII", "source": "F", "cap": "small",
         "market_cap": 5e8, "price": 4.2, "change_pct": 18.5, "avg_volume": 3e6},
    ]
    cache.save_universe(ts, rows)
    back = cache.load_universe(ts)
    assert len(back) == 2
    assert back[0]["ticker"] == "PIII"   # ordered by change_pct desc


def test_earnings_roundtrip():
    cache.save_earnings([{"ticker": "NVDA", "er_date": "2026-05-29",
                          "er_timing": "AMC"}])
    row = cache.get_earnings("NVDA")
    assert row is not None
    assert row["er_timing"] == "AMC"


def test_analyst_roundtrip():
    cache.save_analyst("UXIN", "2026-05-17",
                       raw=[{"action": "upgrade"}],
                       aas=1.0,
                       bull={"upgrades": 1, "initiations_buy": 0,
                             "reiterations_buy": 0, "pt_raises": 0},
                       ignored={"downgrades": 0, "bearish_initiations": 0,
                                "neutrals": 0})
    row = cache.get_analyst("UXIN", "2026-05-17")
    assert row is not None
    assert row["aas_score"] == 1.0


def test_prior_ranking_diff():
    cache.save_prior_ranking("test_track", ["AAA", "BBB", "CCC"])
    added, dropped = cache.diff_prior("test_track", ["BBB", "CCC", "DDD"])
    assert added == ["DDD"]
    assert dropped == ["AAA"]


def test_rankings_audit_save():
    cache.save_rankings("2026-05-17T18:30:00", "daily_small",
                        [(1, "PIII", 25.0, {"breakout": 7, "catalyst": 9})])
    # No getter — purely audit. Just verify no crash.
