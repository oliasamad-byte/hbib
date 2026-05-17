from datetime import date

from s888 import cache, earnings_warning


def test_no_er_returns_empty_tag():
    tag = earnings_warning.warning_for("NEVERSEEN", today=date(2026, 5, 17))
    assert tag.tag() == ""
    assert tag.short() == ""


def test_er_in_one_day_urgent():
    cache.save_earnings([{"ticker": "AAA1", "er_date": "2026-05-18",
                          "er_timing": "BMO"}])
    tag = earnings_warning.warning_for("AAA1", today=date(2026, 5, 17))
    assert "⚠️⚠️⚠️" in tag.tag()


def test_er_in_three_days_double_warn():
    cache.save_earnings([{"ticker": "AAA2", "er_date": "2026-05-20",
                          "er_timing": "AMC"}])
    tag = earnings_warning.warning_for("AAA2", today=date(2026, 5, 17))
    assert tag.tag().startswith("⚠️⚠️")
    assert "3" in tag.tag()


def test_er_in_seven_days_single_warn():
    cache.save_earnings([{"ticker": "AAA3", "er_date": "2026-05-24",
                          "er_timing": "DMH"}])
    tag = earnings_warning.warning_for("AAA3", today=date(2026, 5, 17))
    assert tag.tag().startswith("⚠️ ")


def test_er_in_30_days_no_warn():
    cache.save_earnings([{"ticker": "AAA4", "er_date": "2026-06-17",
                          "er_timing": "AMC"}])
    tag = earnings_warning.warning_for("AAA4", today=date(2026, 5, 17))
    assert tag.tag() == ""
