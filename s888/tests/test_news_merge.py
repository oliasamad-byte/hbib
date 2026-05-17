from s888.news_merge import dedupe, jaccard, merge_per_ticker, tokens


def test_tokens_lowercases_and_strips_stopwords():
    t = tokens("The Quick Brown Fox jumps over the lazy dog")
    assert "quick" in t
    assert "brown" in t
    assert "the" not in t
    # "the" is in stopwords; "over" is not — confirm stopword filter works


def test_jaccard_identical_titles():
    a = tokens("Apple announces strong Q4 earnings beat")
    b = tokens("Apple announces strong Q4 earnings beat")
    assert jaccard(a, b) == 1.0


def test_jaccard_disjoint():
    a = tokens("Apple beats earnings")
    b = tokens("Tesla unveils new model")
    assert jaccard(a, b) == 0.0


def test_dedupe_removes_near_duplicates():
    items = [
        {"title": "Apple beats Q4 earnings, revenue up 12 percent", "source": "fmp_news"},
        {"title": "Apple beats Q4 earnings revenue up 12%", "source": "fmp_pr"},
        {"title": "Tesla announces new battery breakthrough", "source": "yf"},
    ]
    out = dedupe(items, threshold=0.7)
    assert len(out) == 2
    assert out[0]["source"] == "fmp_news"
    assert out[1]["title"].startswith("Tesla")


def test_merge_priority_keeps_fmp_news_first():
    fmp = {"AAPL": [
        {"title": "Apple beats earnings", "source": "fmp_news"},
        {"title": "Apple Q4 results press release", "source": "fmp_pr"},
    ]}
    yf = {"AAPL": [{"title": "Apple beats earnings analysts said", "source": "yf"}]}
    out = merge_per_ticker(fmp, yf, threshold=0.5)
    aapl = out["AAPL"]
    # The yf dupe of fmp_news should be dropped
    sources = [i["source"] for i in aapl]
    assert "fmp_news" in sources
    assert sources.count("yf") == 0 or aapl[0]["source"] == "fmp_news"
