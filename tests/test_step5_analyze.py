"""Step 5 analysis tests."""

from __future__ import annotations

import csv

import pytest

from discoursekit.analyze.agreement import compute_agreement
from discoursekit.analyze.cross_tab import cross_tab_label_publisher
from discoursekit.analyze.descriptive import compute_descriptive
from discoursekit.analyze.export import export_articles_parquet, export_results_csv
from discoursekit.analyze.runner import run_full_analysis
from discoursekit.analyze.statistics import run_did
from discoursekit.analyze.time_series import compute_monthly, compute_weekly
from discoursekit.core.db import get_connection, init_db, upsert_project
from discoursekit.ingest.base import IngestParams
from discoursekit.ingest.bigkinds import BigKindsAdapter
from discoursekit.ingest.runner import run_ingest


def _setup(tmp_path, sample_bigkinds_xlsx):
    db_path = tmp_path / "project.db"
    conn = init_db(db_path)
    now = "2026-05-04T00:00:00+00:00"
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

    run_ingest(
        BigKindsAdapter(),
        IngestParams(project_id="p1", source="bigkinds", input_path=sample_bigkinds_xlsx),
        db_path,
    )

    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO label_schemas (
                schema_id, name, schema_type, labels_json, created_at, description
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("rel", "Relevance", "single_label", "[]", now, ""),
        )
        conn.execute(
            """
            INSERT INTO prompt_versions (
                version_id, schema_id, prompt_text, created_at, sha256
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("rel_v1", "rel", "test", now, "abc"),
        )
        conn.execute(
            """
            INSERT INTO llm_jobs (
                job_id, project_id, schema_id, prompt_version_id, provider, model,
                temperature, sample_size, started_at, finished_at, status,
                n_processed, n_errors, prompt_tokens, candidates_tokens, estimated_cost_usd
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("j1", "p1", "rel", "rel_v1", "mock", "mock", 0.0, 5, now, now, "success", 5, 0, 0, 0, 0.0),
        )
        articles = conn.execute(
            "SELECT article_id FROM articles WHERE project_id = ? ORDER BY date, article_id",
            ("p1",),
        ).fetchall()
        labels = ["relevant", "relevant", "irrelevant", "relevant", "irrelevant"]
        for idx, article in enumerate(articles):
            conn.execute(
                """
                INSERT INTO llm_results (
                    result_id, job_id, article_id, label, labels_json, confidence,
                    rationale, raw_response_json, called_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"r{idx}", "j1", article["article_id"], labels[idx], None, 0.9, None, None, now),
            )
    conn.close()
    return db_path


def test_descriptive_stats(sample_bigkinds_xlsx, tmp_path):
    db_path = _setup(tmp_path, sample_bigkinds_xlsx)
    stats = compute_descriptive(db_path, "p1")
    assert stats.total_articles == 5
    assert stats.active_articles == 5
    assert stats.date_min <= stats.date_max
    assert "bigkinds" in stats.source_counts
    assert len(stats.publisher_counts) > 0


def test_monthly_time_series(sample_bigkinds_xlsx, tmp_path):
    db_path = _setup(tmp_path, sample_bigkinds_xlsx)
    data = compute_monthly(db_path, "p1", "j1")
    assert data.period_type == "monthly"
    assert sum(data.total_counts) == 5
    assert sum(data.label_counts["relevant"]) == 3


def test_weekly_time_series(sample_bigkinds_xlsx, tmp_path):
    db_path = _setup(tmp_path, sample_bigkinds_xlsx)
    data = compute_weekly(db_path, "p1")
    assert data.period_type == "weekly"
    assert sum(data.total_counts) == 5


def test_cross_tab(sample_bigkinds_xlsx, tmp_path):
    db_path = _setup(tmp_path, sample_bigkinds_xlsx)
    result = cross_tab_label_publisher(db_path, "p1", "j1")
    assert "relevant" in result.row_labels
    assert sum(sum(row) for row in result.matrix) == 5


def test_agreement():
    result = compute_agreement(["A", "A", "B", "B", "A"], ["A", "B", "B", "B", "A"])
    assert result.n_samples == 5
    assert 0.0 <= result.accuracy <= 1.0
    assert -1.0 <= result.cohens_kappa <= 1.0
    assert set(result.per_label) == {"A", "B"}


def test_agreement_perfect():
    labels = ["A", "B", "C", "A", "B"]
    result = compute_agreement(labels, labels)
    assert result.accuracy == 1.0
    assert result.cohens_kappa == 1.0


def test_export_parquet_and_csv_exclude_body_internal(sample_bigkinds_xlsx, tmp_path):
    db_path = _setup(tmp_path, sample_bigkinds_xlsx)
    parquet_path = export_articles_parquet(db_path, "p1", tmp_path / "export" / "articles.parquet")
    csv_path = export_results_csv(db_path, "p1", "j1", tmp_path / "export" / "results.csv")
    assert parquet_path.exists()
    assert csv_path.exists()
    assert b"body_internal" not in parquet_path.read_bytes()
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f))
    assert "body_excerpt" in header
    assert "body_internal" not in header


def test_full_analysis(sample_bigkinds_xlsx, tmp_path):
    db_path = _setup(tmp_path, sample_bigkinds_xlsx)
    bundle = run_full_analysis(db_path, "p1", "j1", output_dir=tmp_path / "output")
    assert bundle.descriptive.active_articles == 5
    assert bundle.cross_tab_publisher is not None
    assert (tmp_path / "output" / "articles.parquet").exists()
    assert (tmp_path / "output" / "results.csv").exists()


def test_statistics_import_and_did_smoke():
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        {
            "outcome": [1, 2, 2, 5, 2, 3, 4, 8],
            "treat": [0, 0, 1, 1, 0, 0, 1, 1],
            "post": [0, 1, 0, 1, 0, 1, 0, 1],
        }
    )
    result = run_did(df, "outcome", "treat", "post")
    assert result.test_name == "DiD (OLS)"
    assert "beta_interaction" in result.summary

