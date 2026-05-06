"""Step 7 UI/backend wiring support tests."""

from __future__ import annotations

import csv

from discoursekit.analyze.export import export_articles_csv
from discoursekit.core.db import init_db, upsert_project
from discoursekit.ingest.base import IngestParams
from discoursekit.ingest.bigkinds import BigKindsAdapter
from discoursekit.ingest.runner import run_ingest
from discoursekit.ui.env_keys import (
    load_gemini_keys,
    load_naver_keys,
    save_gemini_keys,
    save_naver_keys,
)


def test_env_keys_roundtrip_preserves_other_entries(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("OTHER=value\nGEMINI_KEY_1=old\n", encoding="utf-8")

    save_gemini_keys({1: "key-one", 3: "key-three"}, env_path)

    text = env_path.read_text(encoding="utf-8")
    assert "OTHER=value" in text
    assert "GEMINI_KEY_1=old" not in text
    assert load_gemini_keys(env_path) == {1: "key-one", 3: "key-three"}


def test_naver_keys_roundtrip_preserves_other_entries(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("OTHER=value\nNAVER_CLIENT_ID=old\n", encoding="utf-8")

    save_naver_keys("client-id", "client-secret", env_path)

    text = env_path.read_text(encoding="utf-8")
    assert "OTHER=value" in text
    assert "NAVER_CLIENT_ID=old" not in text
    assert load_naver_keys(env_path) == {
        "NAVER_CLIENT_ID": "client-id",
        "NAVER_CLIENT_SECRET": "client-secret",
    }


def test_export_articles_csv_excludes_body_internal(sample_bigkinds_xlsx, tmp_path):
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

    output_path = export_articles_csv(db_path, "p1", tmp_path / "artifacts" / "articles.csv")

    with output_path.open(encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f))
    assert "body_excerpt" in header
    assert "body_internal" not in header
