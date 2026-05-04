"""Step 3 handoff import tests."""

from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from discoursekit.clean.pipeline import run_clean_pipeline
from discoursekit.core.db import get_connection, init_db, upsert_project
from discoursekit.handoff.export_ingest import export_ingest_handoff
from discoursekit.handoff.import_handoff import import_ingest_handoff
from discoursekit.ingest.base import IngestParams
from discoursekit.ingest.bigkinds import BigKindsAdapter
from discoursekit.ingest.runner import run_ingest


def _create_handoff_zip(tmp_path, sample_bigkinds_xlsx) -> Path:
    db_path = tmp_path / "src" / "p1" / "project.db"
    db_path.parent.mkdir(parents=True)
    conn = init_db(db_path)
    now = "2026-05-04T00:00:00+00:00"
    with conn:
        upsert_project(
            conn,
            {
                "project_id": "p1",
                "name": "Itaewon",
                "created_at": now,
                "updated_at": now,
                "schema_version": "1.0",
                "description": "",
            },
        )
    conn.close()
    params = IngestParams(project_id="p1", source="bigkinds", input_path=sample_bigkinds_xlsx)
    run_ingest(BigKindsAdapter(), params, db_path)
    zip_path = tmp_path / "handoff.zip"
    export_ingest_handoff(db_path, "p1", zip_path)
    return zip_path


def test_import_handoff_basic(sample_bigkinds_xlsx, tmp_path):
    zip_path = _create_handoff_zip(tmp_path, sample_bigkinds_xlsx)
    result = import_ingest_handoff(
        zip_path,
        target_project_id="p1_copy",
        target_base_dir=tmp_path / "imported",
    )
    assert result["status"] == "success"
    assert result["article_count"] == 5
    assert result["project_id"] == "p1_copy"


def test_import_then_clean(sample_bigkinds_xlsx, tmp_path):
    zip_path = _create_handoff_zip(tmp_path, sample_bigkinds_xlsx)
    result = import_ingest_handoff(
        zip_path,
        target_project_id="p2",
        target_base_dir=tmp_path / "imported",
    )
    db_path = Path(result["project_dir"]) / "project.db"
    run_id = run_clean_pipeline(db_path, "p2", min_body_chars=10)

    conn = get_connection(db_path)
    run_row = conn.execute("SELECT * FROM clean_runs WHERE run_id=?", (run_id,)).fetchone()
    assert dict(run_row)["status"] == "success"
    conn.close()


def test_import_invalid_zip(tmp_path):
    bad_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad_zip, "w") as archive:
        archive.writestr("random.txt", "not a handoff")
    with pytest.raises(ValueError, match="manifest.toml"):
        import_ingest_handoff(bad_zip)


def test_import_checksum_mismatch(sample_bigkinds_xlsx, tmp_path):
    zip_path = _create_handoff_zip(tmp_path, sample_bigkinds_xlsx)
    corrupt_zip = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(zip_path, "r") as source:
        with zipfile.ZipFile(corrupt_zip, "w") as target:
            for item in source.namelist():
                data = source.read(item)
                if item == "checksums.sha256":
                    data = b"0000000000000000  data/project.db\n"
                target.writestr(item, data)

    result = import_ingest_handoff(
        corrupt_zip,
        target_project_id="p3",
        target_base_dir=tmp_path / "imported2",
    )
    assert result["status"] == "success"
    assert any("mismatch" in message.lower() for message in result["messages"])
