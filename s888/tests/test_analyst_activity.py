from datetime import date

from s888.analyst_activity import compute_aas


def _action(action: str, new_grade: str = "Buy", days_ago: int = 5) -> dict:
    today = date(2026, 5, 17)
    from datetime import timedelta
    d = today - timedelta(days=days_ago)
    return {"action": action, "newGrade": new_grade,
            "publishedDate": d.isoformat()}


def test_empty_actions():
    r = compute_aas([], today=date(2026, 5, 17))
    assert r.score == 0.0
    assert all(v == 0 for v in r.bull_counts.values())


def test_one_upgrade():
    r = compute_aas([_action("upgrade")], today=date(2026, 5, 17))
    assert r.score == 1.0
    assert r.bull_counts["upgrades"] == 1


def test_initiation_bullish():
    r = compute_aas([_action("initiation", "Outperform")],
                    today=date(2026, 5, 17))
    assert r.score == 1.0
    assert r.bull_counts["initiations_buy"] == 1


def test_initiation_neutral_ignored():
    r = compute_aas([_action("initiation", "Hold")],
                    today=date(2026, 5, 17))
    assert r.score == 0.0
    assert r.ignored_counts["neutrals"] == 1


def test_initiation_bearish_ignored_not_penalized():
    r = compute_aas([_action("initiation", "Sell")],
                    today=date(2026, 5, 17))
    assert r.score == 0.0
    assert r.ignored_counts["bearish_initiations"] == 1


def test_reiteration_bullish_half_point():
    r = compute_aas([_action("maintain", "Buy")], today=date(2026, 5, 17))
    assert r.score == 0.5
    assert r.bull_counts["reiterations_buy"] == 1


def test_downgrade_ignored():
    r = compute_aas([_action("downgrade", "Hold")], today=date(2026, 5, 17))
    assert r.score == 0.0
    assert r.ignored_counts["downgrades"] == 1


def test_score_caps_at_3():
    acts = [_action("upgrade") for _ in range(10)]
    r = compute_aas(acts, today=date(2026, 5, 17))
    assert r.score == 3.0


def test_outside_window_ignored():
    old = _action("upgrade", days_ago=30)
    r = compute_aas([old], today=date(2026, 5, 17))
    assert r.score == 0.0


def test_tier_emoji_thresholds():
    from s888.analyst_activity import AnalystResult
    assert AnalystResult(score=3.0).tier_emoji() == "🏆"
    assert AnalystResult(score=2.5).tier_emoji() == "👍"
    assert AnalystResult(score=2.0).tier_emoji() == "👍"
    assert AnalystResult(score=1.0).tier_emoji() == "✓"
    assert AnalystResult(score=0.5).tier_emoji() == ""
