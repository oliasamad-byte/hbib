from s888.cap_categorizer import cap_for, tag_cap_categories


def test_small_cap_boundaries():
    assert cap_for(300_000_000) == "small"
    assert cap_for(1_999_999_999) == "small"


def test_mid_cap_boundaries():
    assert cap_for(2_000_000_000) == "mid"
    assert cap_for(9_999_999_999) == "mid"


def test_large_cap_boundaries():
    assert cap_for(10_000_000_000) == "large"
    assert cap_for(199_999_999_999) == "large"


def test_mega_cap_boundaries():
    assert cap_for(200_000_000_000) == "mega"
    assert cap_for(3_500_000_000_000) == "mega"


def test_below_min_skipped():
    assert cap_for(100_000_000) == "skip"
    assert cap_for(0) == "skip"
    assert cap_for(None) == "skip"


def test_tag_drops_skip_rows():
    rows = [
        {"ticker": "BIG", "market_cap": 5e11},     # mega
        {"ticker": "MID", "market_cap": 5e9},      # mid
        {"ticker": "TINY", "market_cap": 5e7},     # skip
        {"ticker": "ZERO", "market_cap": None},    # skip
    ]
    out = tag_cap_categories(rows)
    assert {r["ticker"] for r in out} == {"BIG", "MID"}
    assert all(r["cap"] in {"small", "mid", "large", "mega"} for r in out)
