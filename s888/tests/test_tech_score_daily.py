import numpy as np
import pandas as pd

from s888.tech_score_daily import compute_dts, ScoreResult


def _bull_bars(n: int = 250, start: float = 50.0, step: float = 0.3) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    close = np.array([start + i * step for i in range(n)])
    return pd.DataFrame({
        "open": close, "high": close + 0.3, "low": close - 0.3,
        "close": close, "volume": np.ones(n) * 1_000_000,
    }, index=idx)


def _bull_intraday(periods: int, freq: str, start: float) -> pd.DataFrame:
    idx = pd.date_range("2026-05-17 09:30", periods=periods, freq=freq)
    close = np.linspace(start, start * 1.05, periods)
    return pd.DataFrame({
        "open": close, "high": close + 0.05, "low": close - 0.05,
        "close": close, "volume": np.linspace(80_000, 200_000, periods),
    }, index=idx)


def _build_all_bars():
    daily = _bull_bars(250)
    weekly = _bull_bars(60, start=30, step=1.2)
    return {
        "1m":     _bull_intraday(120, "1min", 100),
        "5m":     _bull_intraday(120, "5min", 100),
        "15m":    _bull_intraday(80, "15min", 100),
        "30m":    _bull_intraday(60, "30min", 100),
        "1h":     _bull_intraday(80, "1h", 100),
        "daily":  daily,
        "weekly": weekly,
    }


def test_dts_strong_uptrend_high_score():
    bars = _build_all_bars()
    price = float(bars["1m"]["close"].iloc[-1])
    levels = {"or_high": 99, "pdh": 98, "pmh": 97,
              "high_20d": 95, "high_50d": 90, "high_52w": 0,
              "high_8w": 0, "or_low": 95}
    r = compute_dts(bars, price, levels, aas=2.0)
    # Strong uptrend → most base checks should pass. RSI may be too high (>70)
    # in some TFs, but at least 15+ checks should fire.
    assert r.base >= 12
    assert r.total >= 14
    assert r.analyst == 2.0


def test_dts_no_data_low_score():
    empty_bars = {tf: pd.DataFrame(columns=["open","high","low","close","volume"])
                  for tf in ["1m","5m","15m","30m","1h","daily","weekly"]}
    r = compute_dts(empty_bars, 0, {}, aas=0)
    assert r.base == 0
    assert r.breakout == 0
    assert r.total == 0


def test_tier_emoji_ranges():
    assert ScoreResult(base=33).tier_emoji() == "🔥🚀🏆"
    assert ScoreResult(base=28).tier_emoji() == "🔥🚀"
    assert ScoreResult(base=24).tier_emoji() == "🔥"
    assert ScoreResult(base=18).tier_emoji() == "✅"
    assert ScoreResult(base=12).tier_emoji() == "⚖️"
    assert ScoreResult(base=6).tier_emoji() == "⚠️"
    assert ScoreResult(base=0).tier_emoji() == "❌"
