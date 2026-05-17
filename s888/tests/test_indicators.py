import numpy as np
import pandas as pd

from s888 import indicators as ind


def _trend_bars(n: int = 60, start: float = 100.0, step: float = 1.0) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    close = np.array([start + i * step for i in range(n)], dtype=float)
    return pd.DataFrame({
        "open": close, "high": close + 0.5, "low": close - 0.5,
        "close": close, "volume": np.ones(n) * 1e6,
    }, index=idx)


def test_ema_trends_with_data():
    b = _trend_bars(60)
    e = ind.ema(b["close"], 20).iloc[-1]
    # EMA(20) of a perfectly linear series should be close to (mean of last ~20)
    assert e > 100 and e < b["close"].iloc[-1]


def test_rsi_uptrend_high():
    b = _trend_bars(60, step=1.0)
    r = ind.rsi(b["close"], 14).iloc[-1]
    assert r > 70  # strict uptrend → high RSI


def test_rsi_downtrend_low():
    b = _trend_bars(60, step=-1.0)
    r = ind.rsi(b["close"], 14).iloc[-1]
    assert r < 30


def test_atr_positive():
    b = _trend_bars(60)
    a = ind.atr(b, 14).iloc[-1]
    assert a > 0


def test_cmf_in_range():
    b = _trend_bars(60)
    c = ind.cmf(b, 20).iloc[-1]
    assert -1.0 <= c <= 1.0


def test_obv_rising_in_uptrend():
    b = _trend_bars(60, step=1.0)
    o = ind.obv(b)
    assert o.iloc[-1] > o.iloc[0]


def test_vol_ratio_basic():
    b = _trend_bars(60)
    b.loc[b.index[-1], "volume"] = 3e6  # 3x normal
    r = ind.vol_ratio(b, 20)
    assert 2.5 < r < 3.5


def test_weinstein_stage_uptrend():
    weekly = _trend_bars(60, start=50, step=2.0)
    assert ind.weinstein_stage(weekly) == 2


def test_weinstein_stage_downtrend():
    weekly = _trend_bars(60, start=200, step=-2.0)
    assert ind.weinstein_stage(weekly) == 4


def test_weinstein_stage_basing_below_flat_sma():
    # Build flat-ish below the SMA: price < sma, slope ~ 0
    n = 60
    idx = pd.date_range("2026-01-01", periods=n, freq="W")
    close = np.full(n, 100.0)
    close[-5:] = 95.0   # price dips below long-term flat mean at the end
    df = pd.DataFrame({
        "open": close, "high": close + 0.5, "low": close - 0.5,
        "close": close, "volume": np.ones(n) * 1e6,
    }, index=idx)
    assert ind.weinstein_stage(df) == 1


def test_weinstein_too_short_is_downtrend():
    b = _trend_bars(10)
    assert ind.weinstein_stage(b) == 4
