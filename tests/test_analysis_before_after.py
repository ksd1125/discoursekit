"""Before/after analysis tests."""

from math import isinf

from discoursekit.analyze.before_after import compare_before_after
from tests.analysis_fixtures import make_analysis_db


def test_before_after_basic(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compare_before_after(db_path, "test", "2022-10-29")

    assert result.before_count == 3
    assert result.after_count == 5


def test_before_after_no_before(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compare_before_after(db_path, "test", "2022-09-01")

    assert result.before_count == 0
    assert isinf(result.ratio)


def test_before_after_ratio(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compare_before_after(db_path, "test", "2022-10-29")

    assert round(result.ratio, 2) == 1.67


def test_before_after_keywords(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compare_before_after(db_path, "test", "2022-10-29")

    assert result.before_top_keywords
    assert result.after_top_keywords
    assert result.after_top_keywords[0][0] == "recovery"
