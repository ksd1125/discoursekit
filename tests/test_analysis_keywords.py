"""Keyword analysis tests."""

from discoursekit.analyze.keywords import compute_keyword_frequency, compute_keyword_stats, compute_keyword_trends
from tests.analysis_fixtures import make_analysis_db


def test_keyword_frequency_basic(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_keyword_frequency(db_path, "test", top_n=5, min_count=1, use_morpheme=False)

    assert result.keywords[0] == ("recovery", 4)
    assert result.total_tokens > 0
    assert result.source_field == "meta_keywords"
    assert result.frequency_stats["mean"] > 0
    assert result.core_keywords
    assert result.concentration > 0


def test_keyword_frequency_with_stopwords(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_keyword_frequency(
        db_path,
        "test",
        top_n=10,
        min_count=1,
        stopwords=["recovery"],
        use_morpheme=False,
    )

    assert "recovery" not in dict(result.keywords)
    assert result.stopwords_applied >= 4


def test_keyword_frequency_min_count(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_keyword_frequency(db_path, "test", top_n=20, min_count=2, use_morpheme=False)

    assert "tourism" not in dict(result.keywords)
    assert "policy" in dict(result.keywords)


def test_keyword_frequency_fallback(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_keyword_frequency(db_path, "test", top_n=5, min_count=1, use_morpheme=False)

    assert result.tokenizer == "split"
    assert result.keywords


def test_compute_keyword_stats():
    stats = compute_keyword_stats([1, 2, 3, 10])

    assert stats["mean"] == 4
    assert stats["median"] == 3
    assert stats["q1"] == 2


def test_keyword_trends_riser(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_keyword_trends(db_path, "test", cutoff_date="2022-10-29", top_n=10, min_count=1)

    assert ("recovery", 4) in result.after_keywords
    assert ("recovery", 4) in result.new_entries


def test_keyword_trends_no_change(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_keyword_trends(db_path, "test", cutoff_date="2022-10-01", top_n=3, min_count=100)

    assert result.risers == []
    assert result.decliners == []
    assert result.new_entries == []
