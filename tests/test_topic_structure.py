"""Topic structure analysis tests."""

from discoursekit.analyze.topic_structure import compute_topic_structure
from tests.analysis_fixtures import make_analysis_db


def test_basic_structure(tmp_path):
    db_path = make_analysis_db(tmp_path)
    result = compute_topic_structure(db_path, "test", top_n=20)

    assert isinstance(result.structural_summary, str)
    assert result.structural_summary


def test_bridge_keywords(tmp_path):
    db_path = make_analysis_db(tmp_path)
    result = compute_topic_structure(db_path, "test", top_n=20)

    assert isinstance(result.bridge_keywords, list)


def test_concentration(tmp_path):
    db_path = make_analysis_db(tmp_path)
    result = compute_topic_structure(db_path, "test", top_n=20)

    assert 0 <= result.concentration_index <= 100


def test_empty_project(tmp_path):
    db_path = make_analysis_db(tmp_path)
    result = compute_topic_structure(db_path, "nonexistent", top_n=20)

    assert result.num_nodes == 0
    assert result.structural_summary
