from s888 import state, cache


def test_diff_first_run_all_added():
    # Wipe state first
    cache.save_prior_ranking("daily_small", [])
    added, dropped = state.diff("daily_small", ["A", "B", "C"])
    assert sorted(added) == ["A", "B", "C"]
    assert dropped == []


def test_commit_then_diff_no_change():
    state.commit("daily_small", ["A", "B", "C"])
    added, dropped = state.diff("daily_small", ["A", "B", "C"])
    assert added == []
    assert dropped == []


def test_diff_after_change():
    state.commit("daily_mlm", ["A", "B"])
    added, dropped = state.diff("daily_mlm", ["B", "C"])
    assert added == ["C"]
    assert dropped == ["A"]


def test_invalid_track_raises():
    import pytest
    with pytest.raises(ValueError):
        state.diff("nonsense_track", ["X"])
