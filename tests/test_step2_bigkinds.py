"""Step 2 BIGKinds adapter tests."""

from __future__ import annotations

from discoursekit.core.db import count_articles, init_db, upsert_project
from discoursekit.ingest.base import IngestParams
from discoursekit.ingest.bigkinds import BigKindsAdapter, _normalize_date
from discoursekit.ingest.runner import run_ingest


def test_normalize_date_yyyymmdd():
    assert _normalize_date("20221030") == "2022-10-30"
    assert _normalize_date(20221030) == "2022-10-30"
    assert _normalize_date("2022-10-30") == "2022-10-30"


def test_bigkinds_adapter_reads_5_articles(sample_bigkinds_xlsx):
    adapter = BigKindsAdapter()
    params = IngestParams(project_id="test", source="bigkinds", input_path=sample_bigkinds_xlsx)
    articles = list(adapter.ingest(params))
    assert len(articles) == 5


def test_bigkinds_article_has_body_split(sample_bigkinds_xlsx):
    adapter = BigKindsAdapter()
    params = IngestParams(project_id="test", source="bigkinds", input_path=sample_bigkinds_xlsx)
    article = next(adapter.ingest(params))
    assert article.body_internal != ""
    assert article.body_excerpt != ""
    assert len(article.body_excerpt) <= 200


def test_bigkinds_date_range_filter(sample_bigkinds_xlsx):
    adapter = BigKindsAdapter()
    params = IngestParams(
        project_id="test",
        source="bigkinds",
        input_path=sample_bigkinds_xlsx,
        date_from="2022-10-30",
        date_to="2022-10-31",
    )
    articles = list(adapter.ingest(params))
    assert all("2022-10-30" <= article.date <= "2022-10-31" for article in articles)
    assert len(articles) == 3


def test_bigkinds_runner_records_to_db(sample_bigkinds_xlsx, tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    now = "2026-05-03T00:00:00+00:00"
    with conn:
        upsert_project(
            conn,
            {
                "project_id": "p1",
                "name": "Test",
                "created_at": now,
                "updated_at": now,
                "schema_version": "1.0",
                "description": "",
            },
        )
    conn.close()

    adapter = BigKindsAdapter()
    params = IngestParams(project_id="p1", source="bigkinds", input_path=sample_bigkinds_xlsx)
    run_id = run_ingest(adapter, params, db_path)

    conn = init_db(db_path)
    assert count_articles(conn, "p1") == 5
    run_row = conn.execute("SELECT * FROM ingest_runs WHERE run_id=?", (run_id,)).fetchone()
    assert dict(run_row)["status"] == "success"
    assert dict(run_row)["in_range_count"] == 5
    conn.close()
