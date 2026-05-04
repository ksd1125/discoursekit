"""Step 2 handoff export tests."""

from __future__ import annotations

import sqlite3
import zipfile

from discoursekit.core.db import init_db, upsert_project
from discoursekit.handoff.export_ingest import export_ingest_handoff
from discoursekit.ingest.base import IngestParams
from discoursekit.ingest.bigkinds import BigKindsAdapter
from discoursekit.ingest.naver_blog import NaverBlogAdapter
from discoursekit.ingest.naver_news import NaverNewsAdapter
from discoursekit.ingest.runner import run_ingest


def _setup_project_with_articles(tmp_path, sample_bigkinds_xlsx):
    db_path = tmp_path / "projects" / "p1" / "project.db"
    db_path.parent.mkdir(parents=True)
    conn = init_db(db_path)
    now = "2026-05-03T00:00:00+00:00"
    with conn:
        upsert_project(
            conn,
            {
                "project_id": "p1",
                "name": "Itaewon",
                "created_at": now,
                "updated_at": now,
                "schema_version": "1.0",
                "description": "test",
            },
        )
    conn.close()

    adapter = BigKindsAdapter()
    params = IngestParams(project_id="p1", source="bigkinds", input_path=sample_bigkinds_xlsx)
    run_ingest(adapter, params, db_path)
    return db_path


def test_handoff_export_creates_zip(sample_bigkinds_xlsx, tmp_path):
    db_path = _setup_project_with_articles(tmp_path, sample_bigkinds_xlsx)
    output = tmp_path / "handoff.zip"
    result = export_ingest_handoff(db_path, "p1", output)
    assert result.exists()
    assert zipfile.is_zipfile(result)


def test_handoff_contains_manifest_and_db(sample_bigkinds_xlsx, tmp_path):
    db_path = _setup_project_with_articles(tmp_path, sample_bigkinds_xlsx)
    output = tmp_path / "handoff.zip"
    export_ingest_handoff(db_path, "p1", output)

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert "manifest.toml" in names
        assert "data/project.db" in names
        assert "checksums.sha256" in names
        assert "README_IMPORT.md" in names
        manifest = archive.read("manifest.toml").decode("utf-8")
        assert "api_keys_included = false" in manifest


def test_handoff_db_has_articles(sample_bigkinds_xlsx, tmp_path):
    db_path = _setup_project_with_articles(tmp_path, sample_bigkinds_xlsx)
    output = tmp_path / "handoff.zip"
    export_ingest_handoff(db_path, "p1", output)

    extract_dir = tmp_path / "extracted"
    with zipfile.ZipFile(output) as archive:
        archive.extractall(extract_dir)

    conn = sqlite3.connect(str(extract_dir / "data" / "project.db"))
    conn.row_factory = sqlite3.Row
    count = conn.execute("SELECT COUNT(*) AS n FROM articles WHERE project_id='p1'").fetchone()[
        "n"
    ]
    conn.close()
    assert count == 5


def test_naver_skeletons_raise_not_implemented():
    params = IngestParams(project_id="p1", source="naver_news", query="이태원")
    for adapter in (NaverNewsAdapter(), NaverBlogAdapter()):
        try:
            list(adapter.ingest(params))
        except NotImplementedError as exc:
            assert "v0.2" in str(exc)
        else:
            raise AssertionError("NAVER skeleton should raise NotImplementedError")
