"""Keyword trajectory analysis tests."""

from discoursekit.analyze.trajectory import compute_keyword_trajectory
from tests.analysis_fixtures import make_analysis_db


def test_keyword_trajectory_basic(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_keyword_trajectory(
        db_path,
        "test",
        "recovery",
        cutoff_date="2022-10-29",
        period_type="month",
        top_n=20,
        min_count=1,
        min_cooccurrence=1,
    )

    assert result.focus_keyword == "recovery"
    assert result.period_type == "month"
    assert result.periods
    assert result.snapshots
    assert result.summary
    assert {snapshot.phase for snapshot in result.snapshots} <= {"before", "on_or_after"}


def test_focus_neighbors_are_tracked(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_keyword_trajectory(
        db_path,
        "test",
        "recovery",
        period_type="month",
        top_n=20,
        min_count=1,
        min_cooccurrence=1,
    )

    neighbors = [
        neighbor["keyword"]
        for snapshot in result.snapshots
        for neighbor in snapshot.focus_neighbors
    ]
    assert "policy" in neighbors or "memorial" in neighbors


def test_discourse_flow_sankey_payload(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_keyword_trajectory(
        db_path,
        "test",
        "recovery",
        period_type="month",
        top_n=20,
        min_count=1,
        min_cooccurrence=1,
    )

    assert isinstance(result.discourse_flows, list)
    assert isinstance(result.sankey_nodes, list)
    assert isinstance(result.sankey_links, list)
    if len(result.periods) > 1:
        assert result.sankey_nodes
        assert result.sankey_links
        assert {"source", "target", "value"} <= set(result.sankey_links[0])


def test_weekly_trajectory_periods(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_keyword_trajectory(
        db_path,
        "test",
        "safety",
        period_type="week",
        top_n=20,
        min_count=1,
        min_cooccurrence=1,
    )

    assert all("-W" in period for period in result.periods)


def test_empty_project(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = compute_keyword_trajectory(db_path, "nonexistent", "recovery")

    assert result.periods == []
    assert result.snapshots == []
    assert "없습니다" in result.summary
