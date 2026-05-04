"""Step 2 CSV adapter tests."""

from __future__ import annotations

from discoursekit.core.db import count_articles, init_db, upsert_project
from discoursekit.ingest.base import IngestParams
from discoursekit.ingest.csv_generic import CsvGenericAdapter, _detect_encoding
from discoursekit.ingest.runner import run_ingest


def test_csv_adapter_reads_5_articles(sample_csv):
    adapter = CsvGenericAdapter()
    params = IngestParams(project_id="test", source="csv", input_path=sample_csv)
    articles = list(adapter.ingest(params))
    assert len(articles) == 5


def test_csv_encoding_detection_utf8bom(tmp_path):
    path = tmp_path / "test.csv"
    path.write_bytes(b"\xef\xbb\xbf" + b"col1,col2\na,b\n")
    assert _detect_encoding(path) == "utf-8-sig"


def test_csv_custom_column_map(tmp_path):
    csv_path = tmp_path / "custom.csv"
    csv_path.write_text(
        "날짜,제목,내용,출처,태그,링크\n2022-10-30,테스트,본문,언론사,키워드,http://x\n",
        encoding="utf-8",
    )
    adapter = CsvGenericAdapter(
        column_map={
            "date": "날짜",
            "title": "제목",
            "body": "내용",
            "publisher": "출처",
            "keywords": "태그",
            "url": "링크",
        }
    )
    params = IngestParams(project_id="test", source="csv", input_path=csv_path)
    articles = list(adapter.ingest(params))
    assert len(articles) == 1
    assert articles[0].title == "테스트"
    assert articles[0].publisher == "언론사"


def test_csv_runner_records_to_db(sample_csv, tmp_path):
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

    adapter = CsvGenericAdapter()
    params = IngestParams(project_id="p1", source="csv", input_path=sample_csv)
    run_ingest(adapter, params, db_path)

    conn = init_db(db_path)
    assert count_articles(conn, "p1") == 5
    conn.close()
