"""DTS — Daily Tech Score 0–38 (28 base + 7 breakout + 3 analyst).

Inputs:
  bars         : dict[str, DataFrame] keyed by '1m','5m','15m','30m','1h','daily','weekly'
  price        : current last-trade price (typically bars['1m']['close'].iloc[-1])
  levels       : dict of breakout reference levels (from breakout_levels.all_levels)
  aas          : float 0..3 (from analyst_activity.compute_aas)
  bar_time_et  : current ET datetime (for ORB lock check). Optional.

Returns:
  ScoreResult with .total (0..38), .base (0..28), .breakout (0..7),
  .analyst (0..3), .breakdown (dict of which checks passed), .tier_emoji.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

import numpy as np
import pandas as pd

from . import indicators as ind

ORB_LOCK_TIME = time(9, 45)


@dataclass
class ScoreResult:
    base: int = 0
    breakout: int = 0
    analyst: float = 0.0
    breakdown: dict[str, bool] = field(default_factory=dict)
    breakout_breakdown: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return self.base + self.breakout + self.analyst

    def tier_emoji(self) -> str:
        """Tier per spec §6.4."""
        t = self.total
        if t >= 33:
            return "🔥🚀🏆"
        if t >= 28:
            return "🔥🚀"
        if t >= 24:
            return "🔥"
        if t >= 18:
            return "✅"
        if t >= 12:
            return "⚖️"
        if t >= 6:
            return "⚠️"
        return "❌"


def _last(s: pd.Series) -> float:
    if s is None or len(s) == 0:
        return float("nan")
    v = s.iloc[-1]
    return float(v) if v is not None else float("nan")


def _safe(bars: dict[str, pd.DataFrame], tf: str) -> pd.DataFrame:
    """Return bars for tf or empty DataFrame."""
    df = bars.get(tf)
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return df


def _ck(cond: bool) -> int:
    return 1 if cond else 0


def compute_base(bars: dict[str, pd.DataFrame], price: float) -> tuple[int, dict[str, bool]]:
    """28 base checks per spec §6.1."""
    b = {}

    def has_close_above(tf: str, level: float | None) -> bool:
        df = _safe(bars, tf)
        if df.empty or level is None or not np.isfinite(level):
            return False
        return float(df["close"].iloc[-1]) > level

    # VWAPs (1, 2, 3)
    for i, tf in enumerate(["1m", "5m", "15m"], 1):
        df = _safe(bars, tf)
        if not df.empty:
            v = _last(ind.vwap(df))
            ref_close = float(df["close"].iloc[-1]) if tf != "1m" else price
            b[f"vwap_{tf}"] = np.isfinite(v) and ref_close > v
        else:
            b[f"vwap_{tf}"] = False

    # EMA(9) on 5m, 15m
    for tf in ["5m", "15m"]:
        df = _safe(bars, tf)
        if not df.empty:
            e = _last(ind.ema(df["close"], 9))
            b[f"ema9_{tf}"] = np.isfinite(e) and float(df["close"].iloc[-1]) > e
        else:
            b[f"ema9_{tf}"] = False

    # EMA(20) on 5m, 15m, 30m, 1h, daily
    for tf in ["5m", "15m", "30m", "1h", "daily"]:
        df = _safe(bars, tf)
        if not df.empty:
            e = _last(ind.ema(df["close"], 20))
            b[f"ema20_{tf}"] = np.isfinite(e) and float(df["close"].iloc[-1]) > e
        else:
            b[f"ema20_{tf}"] = False

    # EMA(50) on 15m, daily
    for tf in ["15m", "daily"]:
        df = _safe(bars, tf)
        if not df.empty:
            e = _last(ind.ema(df["close"], 50))
            b[f"ema50_{tf}"] = np.isfinite(e) and float(df["close"].iloc[-1]) > e
        else:
            b[f"ema50_{tf}"] = False

    # 30W SMA via Weinstein Stage 2 (1 point)
    weekly = _safe(bars, "weekly")
    b["weinstein_stage2"] = ind.weinstein_stage(weekly) == 2 if not weekly.empty else False

    # RSI(14) ∈ [50,70] on 5m, 15m, 30m, 1h, daily
    for tf in ["5m", "15m", "30m", "1h", "daily"]:
        df = _safe(bars, tf)
        if not df.empty:
            r = _last(ind.rsi(df["close"], 14))
            b[f"rsi_{tf}"] = np.isfinite(r) and 50 <= r <= 70
        else:
            b[f"rsi_{tf}"] = False

    # CMF(20) > 0 on 5m, 15m, 1h
    for tf in ["5m", "15m", "1h"]:
        df = _safe(bars, tf)
        if not df.empty:
            c = _last(ind.cmf(df, 20))
            b[f"cmf_{tf}"] = np.isfinite(c) and c > 0
        else:
            b[f"cmf_{tf}"] = False

    # ADX(14) > 20 on 5m, 1h
    for tf in ["5m", "1h"]:
        df = _safe(bars, tf)
        if not df.empty:
            a = _last(ind.adx(df, 14))
            b[f"adx_{tf}"] = np.isfinite(a) and a > 20
        else:
            b[f"adx_{tf}"] = False

    # Vol/SMA(20) > 1.5 on 1m, 5m, 15m
    for tf in ["1m", "5m", "15m"]:
        df = _safe(bars, tf)
        if not df.empty:
            ratio = ind.vol_ratio(df, 20)
            b[f"vol_{tf}"] = np.isfinite(ratio) and ratio > 1.5
        else:
            b[f"vol_{tf}"] = False

    # OBV slope > 0 on 5m, 15m
    for tf in ["5m", "15m"]:
        df = _safe(bars, tf)
        if not df.empty and len(df) >= 6:
            slope = ind.obv_slope(df, lookback=5)
            b[f"obv_{tf}"] = slope > 0
        else:
            b[f"obv_{tf}"] = False

    base_score = sum(_ck(v) for v in b.values())
    return base_score, b


def compute_breakout(bars: dict[str, pd.DataFrame],
                     price: float,
                     levels: dict[str, float],
                     bar_time_et: datetime | None = None) -> tuple[int, dict[str, int]]:
    """3 breakout checks weighted to 7 max per spec §6.2."""
    bd = {"orb": 0, "pdh_pmh": 0, "high_breakout": 0}

    # B1: ORB (+3) — needs current 5m close > OR_HIGH + vol > 2x + 2 consecutive closes above.
    or_high = levels.get("or_high")
    if or_high and np.isfinite(or_high):
        # ORB only valid after 9:45 ET
        time_ok = (bar_time_et is None) or (bar_time_et.time() >= ORB_LOCK_TIME)
        df_5m = _safe(bars, "5m")
        if time_ok and not df_5m.empty and len(df_5m) >= 3:
            last2_close_above = (df_5m["close"].iloc[-2:] > or_high).all()
            vol_ok = ind.vol_ratio(df_5m, 20) > 2.0
            if last2_close_above and vol_ok:
                bd["orb"] = 3

    # B2: PDH/PMH break (+2) — current > max(PDH, PMH) + 5m vol > 1.5x
    pdh = levels.get("pdh", float("nan"))
    pmh = levels.get("pmh", float("nan"))
    ref = max([x for x in (pdh, pmh) if np.isfinite(x)], default=float("nan"))
    if np.isfinite(ref) and price > ref:
        df_5m = _safe(bars, "5m")
        if not df_5m.empty and ind.vol_ratio(df_5m, 20) > 1.5:
            bd["pdh_pmh"] = 2

    # B3: 52w-high (preferred) or 20d-high after ≥5d consolidation, vol > 1.2x daily avg
    daily = _safe(bars, "daily")
    if not daily.empty:
        close_today = float(daily["close"].iloc[-1])
        vol_today = float(daily["volume"].iloc[-1])
        avg_vol = float(daily["volume"].rolling(20).mean().iloc[-1] or 0)
        vol_ok = avg_vol > 0 and vol_today > 1.2 * avg_vol
        h52 = levels.get("high_52w", float("nan"))
        h20 = levels.get("high_20d", float("nan"))
        if np.isfinite(h52) and close_today > h52 and vol_ok:
            bd["high_breakout"] = 2
        elif np.isfinite(h20) and close_today > h20 and vol_ok:
            bd["high_breakout"] = 2

    total = sum(bd.values())
    return total, bd


def compute_dts(bars: dict[str, pd.DataFrame],
                price: float,
                levels: dict[str, float],
                aas: float = 0.0,
                bar_time_et: datetime | None = None) -> ScoreResult:
    base, bd = compute_base(bars, price)
    bo, bo_bd = compute_breakout(bars, price, levels, bar_time_et)
    return ScoreResult(base=base, breakout=bo, analyst=float(aas or 0.0),
                       breakdown=bd, breakout_breakdown=bo_bd)
