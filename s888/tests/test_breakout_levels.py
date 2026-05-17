import numpy as np
import pandas as pd

from s888 import breakout_levels as bl


def _intraday_5m_today(or_highs: list[float],
                       rest_close: float = 105.0,
                       date: str = "2026-05-17") -> pd.DataFrame:
    """Build a 1-day 5m series with 3 OR bars then 10 more bars."""
    times = pd.date_range(f"{date} 09:30", periods=3 + 10, freq="5min")
    n = len(times)
    high = list(or_highs) + [rest_close + 0.5] * (n - 3)
    low = [h - 1 for h in high]
    close = high
    return pd.DataFrame({
        "open": close, "high": high, "low": low,
        "close": close, "volume": np.ones(n) * 100_000,
    }, index=times)


def test_orb_high_after_third_bar():
    df = _intraday_5m_today([101.0, 102.5, 102.0])
    assert bl.opening_range_high(df) == 102.5


def test_orb_high_nan_with_fewer_than_3_bars():
    times = pd.date_range("2026-05-17 09:30", periods=2, freq="5min")
    df = pd.DataFrame({"open": [100, 100], "high": [101, 101],
                       "low": [99, 99], "close": [100, 100],
                       "volume": [1000, 1000]}, index=times)
    assert np.isnan(bl.opening_range_high(df))


def test_pdh_from_daily():
    idx = pd.date_range("2026-05-10", periods=5, freq="D")
    df = pd.DataFrame({
        "open": [10] * 5, "high": [11, 12, 13, 14, 15],
        "low": [9] * 5, "close": [10] * 5, "volume": [1e6] * 5,
    }, index=idx)
    assert bl.prior_day_high(df) == 14   # second-to-last


def test_premarket_high():
    times = pd.date_range("2026-05-17 04:00", periods=300, freq="1min")
    df = pd.DataFrame({
        "open": [100] * 300, "high": np.linspace(100, 105, 300),
        "low": [99] * 300, "close": [100] * 300, "volume": [1000] * 300,
    }, index=times)
    # PMH should be 105 (or close to it) since premarket runs to 9:30
    # premarket ends at 9:30 — index up to 8:59. Last index is 04:00 + 299min = 8:59
    pmh = bl.premarket_high(df)
    assert pmh > 104


def test_nday_high_excludes_today_by_default():
    idx = pd.date_range("2026-05-01", periods=22, freq="D")
    highs = list(range(100, 120)) + [200, 200]  # last two are huge
    df = pd.DataFrame({
        "open": [10] * 22, "high": highs, "low": [9] * 22,
        "close": [10] * 22, "volume": [1e6] * 22,
    }, index=idx)
    # exclude_today=True (default), so last bar's high (200) excluded.
    # 20d-high uses bars [-21:-1] = highs[1:21] = 101..119,200 → max = 200
    h = bl.nday_high(df, 20)
    assert h == 200


def test_nweek_high_8w():
    idx = pd.date_range("2026-01-01", periods=10, freq="W-FRI")
    highs = [50, 60, 70, 80, 90, 100, 110, 120, 130, 200]
    df = pd.DataFrame({
        "open": [10] * 10, "high": highs, "low": [9] * 10,
        "close": [10] * 10, "volume": [1e6] * 10,
    }, index=idx)
    # exclude_current → last 8 of first 9 = [60..130] → max 130
    h = bl.nweek_high(df, 8)
    assert h == 130
