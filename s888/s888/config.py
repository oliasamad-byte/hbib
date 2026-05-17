"""Centralized env-driven config. Read once on import; everything else uses it."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _env_str(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    v = os.environ.get(key)
    return int(v) if v not in (None, "") else default


def _env_float(key: str, default: float) -> float:
    v = os.environ.get(key)
    return float(v) if v not in (None, "") else default


def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key)
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    # Secrets
    fmp_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    # Schedule
    master_clock: str
    scan_start_gst: str
    scan_end_gst: str
    scan_interval_min: int
    # Universe
    universe_max: int
    min_price: float
    min_avg_volume: int
    min_intraday_change_pct: float
    # Cap thresholds
    cap_small_min: int
    cap_small_max: int
    cap_mid_max: int
    cap_large_max: int
    # Daily ranking
    daily_top_n_detailed: int
    daily_top_n_list: int
    daily_stage_b_cut_per_bucket: int
    daily_small_send_if_empty: bool
    daily_midlargemega_send_if_empty: bool
    # Weekly ranking
    weekly_catalyst_threshold: int
    weekly_wts_threshold: int
    weekly_top_n: int
    weekly_top_n_detailed: int
    weekly_send_if_empty: bool
    # Analyst
    analyst_lookback_days: int
    analyst_cache_hours: int
    # Earnings warning
    earnings_warn_days: int
    earnings_urgent_days: int
    # Telegram
    telegram_combined: str
    # Rate limit
    fmp_concurrent_requests: int
    # Paths
    data_dir: Path
    log_dir: Path


def load_config() -> Config:
    data_dir = ROOT / _env_str("DATA_DIR", "data")
    log_dir = ROOT / _env_str("LOG_DIR", "logs")
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        fmp_api_key=_env_str("FMP_API_KEY"),
        telegram_bot_token=_env_str("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_env_str("TELEGRAM_CHAT_ID"),
        master_clock=_env_str("MASTER_CLOCK", "gst"),
        scan_start_gst=_env_str("SCAN_START_GST", "17:30"),
        scan_end_gst=_env_str("SCAN_END_GST", "22:30"),
        scan_interval_min=_env_int("SCAN_INTERVAL_MIN", 10),
        universe_max=_env_int("UNIVERSE_MAX", 200),
        min_price=_env_float("MIN_PRICE", 2.0),
        min_avg_volume=_env_int("MIN_AVG_VOLUME", 200_000),
        min_intraday_change_pct=_env_float("MIN_INTRADAY_CHANGE_PCT", 2.5),
        cap_small_min=_env_int("CAP_SMALL_MIN", 300_000_000),
        cap_small_max=_env_int("CAP_SMALL_MAX", 2_000_000_000),
        cap_mid_max=_env_int("CAP_MID_MAX", 10_000_000_000),
        cap_large_max=_env_int("CAP_LARGE_MAX", 200_000_000_000),
        daily_top_n_detailed=_env_int("DAILY_TOP_N_DETAILED", 3),
        daily_top_n_list=_env_int("DAILY_TOP_N_LIST", 20),
        daily_stage_b_cut_per_bucket=_env_int("DAILY_STAGE_B_CUT_PER_BUCKET", 30),
        daily_small_send_if_empty=_env_bool("DAILY_SMALL_SEND_IF_EMPTY", False),
        daily_midlargemega_send_if_empty=_env_bool("DAILY_MIDLARGEMEGA_SEND_IF_EMPTY", True),
        weekly_catalyst_threshold=_env_int("WEEKLY_CATALYST_THRESHOLD", 7),
        weekly_wts_threshold=_env_int("WEEKLY_WTS_THRESHOLD", 12),
        weekly_top_n=_env_int("WEEKLY_TOP_N", 20),
        weekly_top_n_detailed=_env_int("WEEKLY_TOP_N_DETAILED", 3),
        weekly_send_if_empty=_env_bool("WEEKLY_SEND_IF_EMPTY", False),
        analyst_lookback_days=_env_int("ANALYST_LOOKBACK_DAYS", 15),
        analyst_cache_hours=_env_int("ANALYST_CACHE_HOURS", 24),
        earnings_warn_days=_env_int("EARNINGS_WARN_DAYS", 7),
        earnings_urgent_days=_env_int("EARNINGS_URGENT_DAYS", 3),
        telegram_combined=_env_str("TELEGRAM_COMBINED", "false"),
        fmp_concurrent_requests=_env_int("FMP_CONCURRENT_REQUESTS", 20),
        data_dir=data_dir,
        log_dir=log_dir,
    )


# Module-level singleton — most code just imports CFG.
CFG = load_config()
