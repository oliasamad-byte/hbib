from datetime import date

from s888.catalyst import CatalystResult, classify, upgrade_to_high_vol


def test_earnings_beat_detected():
    r = classify("AAPL", [{"title": "Apple Q4 earnings beats Street estimates"}])
    assert r.category == "earnings_beat"
    assert r.score == 9


def test_regulatory_win_higher_than_analyst():
    items = [
        {"title": "Pfizer upgrades from analysts"},
        {"title": "FDA approves new Pfizer drug"},
    ]
    r = classify("PFE", items)
    assert r.category == "regulatory_win"
    assert r.score == 9


def test_contract_award():
    r = classify("RKLB", [{"title": "Rocket Lab awarded $750M NRO contract"}])
    assert r.category == "contract_award"


def test_m_and_a_target():
    r = classify("XYZ", [{"title": "XYZ to acquire ABC in $5B deal"}])
    assert r.category == "m_and_a_target"
    assert r.score == 8


def test_analyst_upgrade():
    r = classify("NVDA", [{"title": "Wedbush upgrades NVDA, raises PT to $200"}])
    assert r.category == "analyst_upgrade"
    assert r.score == 7


def test_pump_unclear_low_score():
    r = classify("AAA", [{"title": "AAA penny stock could rocket 500%"}])
    assert r.category == "pump_unclear"
    assert r.score == 1


def test_fallback_technical_only():
    r = classify("BBB", [{"title": "BBB closes at new daily high"}])
    assert r.category == "technical_only"
    assert r.score == 3


def test_no_news_fallback():
    r = classify("EMPTY", [])
    assert r.category == "technical_only"


def test_pre_er_window_when_no_news():
    # ER in 3 days, no news → pre_er_window
    er_map = {"FOO": (date.today().replace(day=1).isoformat())}  # placeholder
    # Use a known er date
    today = date(2026, 5, 17)
    er_map = {"FOO": "2026-05-21"}  # 4 days out
    r = classify("FOO", [], er_dates=er_map, today=today)
    assert r.category == "pre_er_window"
    assert r.score == 6


def test_post_er_drift_when_recent_er_no_strong_news():
    today = date(2026, 5, 17)
    er_map = {"FOO": "2026-05-14"}  # 3 days ago
    r = classify("FOO", [], er_dates=er_map, today=today)
    assert r.category == "post_er_drift"
    assert r.score == 8


def test_sector_sympathy_when_etf_up():
    r = classify("XYZ", [], sector_etf_change_pct=3.5)
    assert r.category == "sector_sympathy"
    assert r.score == 5


def test_upgrade_to_hv():
    base = CatalystResult(9, "earnings_beat", "Beats Q4")
    up = upgrade_to_high_vol(base, vol_ratio=2.5)
    assert up.score == 10
    assert up.category == "earnings_beat_HV"
    # No upgrade if vol_ratio < 2.0
    no_up = upgrade_to_high_vol(base, vol_ratio=1.0)
    assert no_up.score == 9
