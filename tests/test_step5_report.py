"""Step 5 methodology report tests."""

from __future__ import annotations

from discoursekit.analyze.runner import run_full_analysis
from discoursekit.core.db import init_db, upsert_project
from discoursekit.ingest.base import IngestParams
from discoursekit.ingest.bigkinds import BigKindsAdapter
from discoursekit.ingest.runner import run_ingest
from discoursekit.report.methodology import generate_methodology_report


def _setup_with_results(tmp_path, sample_bigkinds_xlsx):
    db_path = tmp_path / "project.db"
    conn = init_db(db_path)
    now = "2026-05-04T00:00:00+00:00"
    with conn:
        upsert_project(
            conn,
            {
                "project_id": "p1",
                "name": "Itaewon 2022",
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
    return db_path


def test_report_generates_html(sample_bigkinds_xlsx, tmp_path):
    db_path = _setup_with_results(tmp_path, sample_bigkinds_xlsx)
    bundle = run_full_analysis(db_path, "p1")
    out = generate_methodology_report(bundle, "Itaewon 2022", tmp_path / "report.html")
    content = out.read_text(encoding="utf-8")
    assert "Methodology Report" in content
    assert "Itaewon 2022" in content


def test_report_contains_stats(sample_bigkinds_xlsx, tmp_path):
    db_path = _setup_with_results(tmp_path, sample_bigkinds_xlsx)
    bundle = run_full_analysis(db_path, "p1")
    out = generate_methodology_report(bundle, "Test", tmp_path / "report.html")
    content = out.read_text(encoding="utf-8")
    assert "Active articles" in content
    assert "5" in content


def test_report_no_body_internal(sample_bigkinds_xlsx, tmp_path):
    db_path = _setup_with_results(tmp_path, sample_bigkinds_xlsx)
    bundle = run_full_analysis(db_path, "p1")
    out = generate_methodology_report(bundle, "Test", tmp_path / "report.html")
    content = out.read_text(encoding="utf-8")
    assert "body_internal" not in content

