from s888.config import CFG, load_config


def test_cfg_singleton_loads():
    assert CFG is not None
    assert CFG.universe_max > 0
    assert CFG.scan_interval_min > 0
    assert CFG.cap_small_min < CFG.cap_small_max < CFG.cap_mid_max < CFG.cap_large_max
    assert CFG.data_dir.exists()
    assert CFG.log_dir.exists()


def test_reload_returns_same_shape():
    fresh = load_config()
    assert fresh.universe_max == CFG.universe_max
    assert fresh.weekly_wts_threshold == CFG.weekly_wts_threshold


def test_telegram_combined_modes():
    assert CFG.telegram_combined in {"false", "true", "daily_only", "all"}
