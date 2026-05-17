import numpy as np
import pandas as pd

from s888.tech_score_weekly import compute_wts, WeeklyScoreResult


def _bars(n: int = 60, start: float = 50.0, step: float = 1.0) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="W-FRI")
    close = np.array([start + i * step for i in range(n)])
    return pd.DataFrame({
        "open": close, "high": close + 0.3, "low": close - 0.3,
        "close": close, "volume": np.ones(n) * 1_000_000,
    }, index=idx)


def _daily(n: int = 250, start: float = 50.0, step: float = 0.4):
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    close = np.array([start + i * step for i in range(n)])
    return pd.DataFrame({
        "open": close, "high": close + 0.3, "low": close - 0.3,
        "close": close, "volume": np.ones(n) * 1_000_000,
    }, index=idx)


def test_wts_uptrend_strong():
    bars = {"weekly": _bars(60), "daily": _daily(250),
            "1h": _daily(80, start=100, step=0.05)}
    levels = {"high_20d": 50, "high_52w": 0, "high_8w": 100}
    r = compute_wts(bars, levels, aas=2.0)
    assert r.stage == 2
    assert r.base >= 5
    assert r.total >= 7


def test_wts_downtrend_stage4_low_score():
    bars = {"weekly": _bars(60, start=200, step=-2.0),
            "daily": _daily(250, start=200, step=-0.4),
            "1h": pd.DataFrame()}
    levels = {"high_20d": float("nan"), "high_52w": float("nan"),
              "high_8w": float("nan")}
    r = compute_wts(bars, levels, aas=0.0)
    assert r.stage == 4


def test_weekly_tier_emoji():
    assert WeeklyScoreResult(base=10, breakout=6, analyst=3.0).tier_emoji() == "🔥🚀🏆"
    assert WeeklyScoreResult(base=10, breakout=4).tier_emoji() == "🔥🚀"
    assert WeeklyScoreResult(base=8, breakout=3).tier_emoji() == "🔥"
    assert WeeklyScoreResult(base=5, breakout=3).tier_emoji() == "✅"
    assert WeeklyScoreResult(base=3, breakout=2).tier_emoji() == "⚖️"
    assert WeeklyScoreResult(base=0).tier_emoji() == "❌"


def test_stage_emoji():
    assert WeeklyScoreResult(stage=2).stage_emoji() == "🟢"
    assert WeeklyScoreResult(stage=1).stage_emoji() == "🔵"
    assert WeeklyScoreResult(stage=3).stage_emoji() == "🟡"
    assert WeeklyScoreResult(stage=4).stage_emoji() == "🔴"
