"""Co-occurrence analysis tests."""

from discoursekit.analyze.cooccurrence import compute_cooccurrence
from tests.analysis_fixtures import make_analysis_db


def test_basic(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_cooccurrence(db_path, "test", "Itaewon", top_n=10)

    assert result.article_count == 8
    assert result.cooccurrences


def test_counts_sorted(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_cooccurrence(db_path, "test", "recovery", top_n=10)
    counts = [count for _, count in result.cooccurrences]

    assert counts == sorted(counts, reverse=True)


def test_top_n(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_cooccurrence(db_path, "test", "Itaewon", top_n=5)

    assert len(result.cooccurrences) <= 5


def test_no_match(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_cooccurrence(db_path, "test", "missing")

    assert result.article_count == 0
    assert result.cooccurrences == []
