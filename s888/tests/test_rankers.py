from s888.ranker_daily import ScoredTicker, rank_small_cap, rank_mid_large_mega, rank_both
from s888.ranker_weekly import filter_weekly, rank_weekly


def _t(**kw) -> ScoredTicker:
    defaults = dict(
        ticker="X", source="Y", cap="small", price=10.0, change_pct=5.0,
        market_cap=1e9, dts_total=20.0, dts_base=18, dts_breakout=2,
        dts_analyst=0.0, wts_total=0.0, catalyst_score=5,
        catalyst_category="technical_only",
    )
    defaults.update(kw)
    return ScoredTicker(**defaults)


def test_small_cap_sorted_by_dts_desc():
    a = _t(ticker="A", cap="small", dts_total=25)
    b = _t(ticker="B", cap="small", dts_total=20)
    c = _t(ticker="C", cap="mid",   dts_total=30)   # not in small
    out = rank_small_cap([a, b, c])
    assert [x.ticker for x in out] == ["A", "B"]


def test_breakout_tiebreaker():
    a = _t(ticker="A", dts_total=20, dts_breakout=2, catalyst_score=7)
    b = _t(ticker="B", dts_total=20, dts_breakout=5, catalyst_score=5)
    out = rank_small_cap([a, b])
    assert out[0].ticker == "B"   # higher breakout wins tiebreak


def test_catalyst_tiebreaker_after_breakout():
    a = _t(ticker="A", dts_total=20, dts_breakout=3, catalyst_score=8)
    b = _t(ticker="B", dts_total=20, dts_breakout=3, catalyst_score=5)
    out = rank_small_cap([a, b])
    assert out[0].ticker == "A"


def test_mlm_excludes_small():
    s = _t(ticker="S", cap="small", dts_total=30)
    m = _t(ticker="M", cap="mid", dts_total=20)
    L = _t(ticker="L", cap="large", dts_total=25)
    out = rank_mid_large_mega([s, m, L])
    assert [x.ticker for x in out] == ["L", "M"]


def test_rank_both_returns_two_disjoint_lists():
    a = _t(ticker="A", cap="small", dts_total=25)
    b = _t(ticker="B", cap="mega", dts_total=30)
    s, m = rank_both([a, b])
    assert [x.ticker for x in s] == ["A"]
    assert [x.ticker for x in m] == ["B"]


def test_weekly_filter_stage4_blocked():
    a = _t(ticker="A", wts_total=15, catalyst_score=8)
    b = _t(ticker="B", wts_total=15, catalyst_score=8)
    stages = {"A": 2, "B": 4}
    out = filter_weekly([a, b], stages)
    assert [x.ticker for x in out] == ["A"]


def test_weekly_filter_catalyst_threshold():
    a = _t(ticker="A", wts_total=15, catalyst_score=8)
    b = _t(ticker="B", wts_total=15, catalyst_score=6)
    stages = {"A": 2, "B": 2}
    out = filter_weekly([a, b], stages, catalyst_threshold=7)
    assert [x.ticker for x in out] == ["A"]


def test_weekly_filter_wts_threshold():
    a = _t(ticker="A", wts_total=15, catalyst_score=8)
    b = _t(ticker="B", wts_total=10, catalyst_score=8)
    stages = {"A": 2, "B": 2}
    out = filter_weekly([a, b], stages, wts_threshold=12)
    assert [x.ticker for x in out] == ["A"]


def test_weekly_rank_stage2_beats_stage1_in_tiebreak():
    a = _t(ticker="A", wts_total=15, dts_breakout=3, catalyst_score=8)
    b = _t(ticker="B", wts_total=15, dts_breakout=3, catalyst_score=8)
    stages = {"A": 1, "B": 2}
    out = rank_weekly([a, b], stages)
    assert out[0].ticker == "B"
