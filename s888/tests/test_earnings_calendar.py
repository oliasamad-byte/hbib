from datetime import date

from s888 import cache, earnings_calendar


def test_days_until_er_returns_none_if_no_cached():
    # New ticker, never cached
    assert earnings_calendar.days_until_er("ZZZUNKNOWN", today=date(2026, 5, 17)) is None


def test_days_until_er_calculates_correctly():
    cache.save_earnings([{"ticker": "FOOX", "er_date": "2026-05-20",
                          "er_timing": "AMC"}])
    delta = earnings_calendar.days_until_er("FOOX", today=date(2026, 5, 17))
    assert delta == 3


def test_days_until_er_returns_none_for_past_er():
    cache.save_earnings([{"ticker": "FOOY", "er_date": "2026-05-10",
                          "er_timing": "BMO"}])
    delta = earnings_calendar.days_until_er("FOOY", today=date(2026, 5, 17))
    assert delta is None


def test_er_dates_map():
    cache.save_earnings([
        {"ticker": "A1", "er_date": "2026-05-20", "er_timing": "AMC"},
        {"ticker": "B2", "er_date": "2026-05-22", "er_timing": "BMO"},
    ])
    m = earnings_calendar.er_dates_map(["A1", "B2", "NEVER_SEEN"])
    assert m["A1"] == "2026-05-20"
    assert m["B2"] == "2026-05-22"
    assert "NEVER_SEEN" not in m
