"""WTS — Weekly Tech Score 0–19 (10 base + 6 breakout + 3 analyst).

Per spec §7. Stage 4 hard-block happens UPSTREAM (in the ranker) — this
module just scores; it does not enforce the gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators as ind


@dataclass
class WeeklyScoreResult:
    base: int = 0
    breakout: int = 0
    analyst: float = 0.0
    stage: int = 4
    breakdown: dict[str, bool] = field(default_factory=dict)
    breakout_breakdown: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return self.base + self.breakout + self.analyst

    def tier_emoji(self) -> str:
        t = self.total
        if t >= 17:
            return "🔥🚀🏆"
        if t >= 14:
            return "🔥🚀"
        if t >= 11:
            return "🔥"
        if t >= 8:
            return "✅"
        if t >= 5:
            return "⚖️"
        return "❌"

    def stage_emoji(self) -> str:
        return {1: "🔵", 2: "🟢", 3: "🟡", 4: "🔴"}.get(self.stage, "❓")


def _safe(bars: dict[str, pd.DataFrame], tf: str) -> pd.DataFrame:
    df = bars.get(tf)
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return df


def _last(s: pd.Series) -> float:
    if s is None or len(s) == 0:
        return float("nan")
    v = s.iloc[-1]
    return float(v) if v is not None else float("nan")


def compute_base(bars: dict[str, pd.DataFrame], stage: int) -> tuple[int, dict[str, bool]]:
    b = {}
    weekly = _safe(bars, "weekly")
    daily = _safe(bars, "daily")
    h1 = _safe(bars, "1h")

    # 1. Stage ∈ {1,2,3}
    b["stage_tradable"] = stage in {1, 2, 3}

    # 2. Weekly price > 30W SMA
    if not weekly.empty and len(weekly) >= 30:
        s30 = ind.sma(weekly["close"], 30).iloc[-1]
        b["weekly_above_sma30"] = np.isfinite(s30) and float(weekly["close"].iloc[-1]) > s30
    else:
        b["weekly_above_sma30"] = False

    # 3. Weekly RSI(14) ∈ [45,75]
    if not weekly.empty:
        r = _last(ind.rsi(weekly["close"], 14))
        b["weekly_rsi"] = np.isfinite(r) and 45 <= r <= 75
    else:
        b["weekly_rsi"] = False

    # 4. Daily > EMA(20)
    if not daily.empty:
        e = _last(ind.ema(daily["close"], 20))
        b["daily_above_ema20"] = np.isfinite(e) and float(daily["close"].iloc[-1]) > e
    else:
        b["daily_above_ema20"] = False

    # 5. Daily > EMA(50)
    if not daily.empty:
        e = _last(ind.ema(daily["close"], 50))
        b["daily_above_ema50"] = np.isfinite(e) and float(daily["close"].iloc[-1]) > e
    else:
        b["daily_above_ema50"] = False

    # 6. Daily RSI ∈ [50,70]
    if not daily.empty:
        r = _last(ind.rsi(daily["close"], 14))
        b["daily_rsi"] = np.isfinite(r) and 50 <= r <= 70
    else:
        b["daily_rsi"] = False

    # 7. Daily CMF > 0
    if not daily.empty:
        c = _last(ind.cmf(daily, 20))
        b["daily_cmf_pos"] = np.isfinite(c) and c > 0
    else:
        b["daily_cmf_pos"] = False

    # 8. Daily CMF > 0.10 (strong)
    if not daily.empty:
        c = _last(ind.cmf(daily, 20))
        b["daily_cmf_strong"] = np.isfinite(c) and c > 0.10
    else:
        b["daily_cmf_strong"] = False

    # 9. Daily ADX > 20
    if not daily.empty:
        a = _last(ind.adx(daily, 14))
        b["daily_adx"] = np.isfinite(a) and a > 20
    else:
        b["daily_adx"] = False

    # 10. 1H RSI rising, in 50-70
    if not h1.empty and len(h1) >= 17:
        r = ind.rsi(h1["close"], 14).iloc[-3:]
        in_range = 50 <= r.iloc[-1] <= 70 if np.isfinite(r.iloc[-1]) else False
        rising = (r.diff().iloc[-1] > 0) and (r.diff().iloc[-2] > 0)
        b["h1_rsi_rising"] = in_range and rising
    else:
        b["h1_rsi_rising"] = False

    score = sum(1 for v in b.values() if v)
    return score, b


def compute_breakout(bars: dict[str, pd.DataFrame],
                     levels: dict[str, float]) -> tuple[int, dict[str, int]]:
    bd = {"high_20d": 0, "high_52w": 0, "stage12_or_8wh": 0}
    daily = _safe(bars, "daily")
    weekly = _safe(bars, "weekly")
    if daily.empty:
        return 0, bd

    close_today = float(daily["close"].iloc[-1])
    vol_today = float(daily["volume"].iloc[-1])
    avg_vol = float(daily["volume"].rolling(20).mean().iloc[-1] or 0)

    # B1: 20d high break + daily vol > avg
    h20 = levels.get("high_20d", float("nan"))
    if np.isfinite(h20) and close_today > h20 and avg_vol > 0 and vol_today > avg_vol:
        bd["high_20d"] = 2

    # B2: 52w high break (within 1%) + vol confirmation
    h52 = levels.get("high_52w", float("nan"))
    if np.isfinite(h52) and close_today >= h52 * 0.99 and avg_vol > 0 \
       and vol_today > 1.2 * avg_vol:
        bd["high_52w"] = 2

    # B3: Stage 1→2 transition OR 8w high
    h8w = levels.get("high_8w", float("nan"))
    if not weekly.empty:
        s30 = ind.sma(weekly["close"], 30)
        if len(s30.dropna()) >= 4:
            now_above = weekly["close"].iloc[-1] > s30.iloc[-1]
            was_below = (weekly["close"].iloc[-5:-1] <= s30.iloc[-5:-1]).any()
            if now_above and was_below:
                bd["stage12_or_8wh"] = 2
        if bd["stage12_or_8wh"] == 0 and np.isfinite(h8w):
            wk_vol_avg = float(weekly["volume"].rolling(8).mean().iloc[-1] or 0)
            wk_vol = float(weekly["volume"].iloc[-1])
            if (close_today > h8w) and wk_vol_avg > 0 and wk_vol > wk_vol_avg:
                bd["stage12_or_8wh"] = 2

    return sum(bd.values()), bd


def compute_wts(bars: dict[str, pd.DataFrame],
                levels: dict[str, float],
                aas: float = 0.0) -> WeeklyScoreResult:
    weekly = _safe(bars, "weekly")
    stage = ind.weinstein_stage(weekly) if not weekly.empty else 4
    base, bd = compute_base(bars, stage)
    bo, bo_bd = compute_breakout(bars, levels)
    return WeeklyScoreResult(base=base, breakout=bo, analyst=float(aas or 0.0),
                              stage=stage, breakdown=bd,
                              breakout_breakdown=bo_bd)
