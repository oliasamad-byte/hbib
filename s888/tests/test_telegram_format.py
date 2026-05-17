from s888 import telegram_format
from s888.ranker_daily import ScoredTicker
from s888.tech_score_daily import ScoreResult
from s888.tech_score_weekly import WeeklyScoreResult


def _t(**kw) -> ScoredTicker:
    d = dict(ticker="X", source="Y", cap="small", price=10.0, change_pct=5.0,
             market_cap=1e9, dts_total=22.0, dts_base=18, dts_breakout=4,
             dts_analyst=0.0, wts_total=0.0, catalyst_score=7,
             catalyst_category="analyst_upgrade", catalyst_evidence="abc")
    d.update(kw)
    return ScoredTicker(**d)


def test_format_daily_small_has_header_and_top_block():
    picks = [_t(ticker="A"), _t(ticker="B"), _t(ticker="C")]
    scores = {p.ticker: ScoreResult(base=18, breakout=4, analyst=0.0,
                                     breakdown={}, breakout_breakdown={"orb":3, "pdh_pmh":1, "high_breakout":0})
              for p in picks}
    out = telegram_format.format_daily_small(picks, scores, set(), 30, [], [])
    assert "📅 DAILY SMALL CAP" in out
    assert "Universe: 30" in out
    assert "🥇 #1  A" in out
    assert "🥈 #2  B" in out
    assert "🥉 #3  C" in out


def test_format_daily_mlm_has_cap_subtag():
    picks = [_t(ticker="NVDA", cap="mega"), _t(ticker="AMD", cap="large")]
    scores = {p.ticker: ScoreResult(base=20, breakout=5, analyst=2.0,
                                     breakout_breakdown={"orb":3,"pdh_pmh":2,"high_breakout":0})
              for p in picks}
    out = telegram_format.format_daily_mlm(picks, scores, set(), 50, [], [])
    assert "[Mega]" in out
    assert "[Large]" in out


def test_format_weekly_empty_returns_empty():
    assert telegram_format.format_weekly([], {}, {}, [], []) == ""


def test_format_weekly_has_stage_emoji():
    picks = [_t(ticker="NVDA", cap="mega", wts_total=18.0)]
    w = {p.ticker: WeeklyScoreResult(base=10, breakout=5, analyst=3.0,
                                      stage=2) for p in picks}
    out = telegram_format.format_weekly(picks, w, {"NVDA": "M/L/M #1"}, [], [])
    assert "📆 WEEKLY TRADE RANK" in out
    assert "🟢" in out         # stage 2 emoji
    assert "🏆" in out         # AAS 3.0 emoji
    assert "Daily: M/L/M #1" in out


def test_priority_emoji_high_breakout():
    s = ScoreResult(base=25, breakout=6, analyst=2.0)
    e = telegram_format._priority_emojis(s, weekly_match=False)
    assert "⚡" in e


def test_priority_emoji_with_weekly_match():
    s = ScoreResult(base=25, breakout=4)
    e = telegram_format._priority_emojis(s, weekly_match=True)
    assert "🚀" in e
    assert "📆" in e
