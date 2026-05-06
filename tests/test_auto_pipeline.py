"""Auto collect-clean pipeline tests."""

from __future__ import annotations

import json

import pytest

from discoursekit.core.db import get_connection, init_db, insert_article, insert_ingest_run, upsert_project
from discoursekit.ingest.base import BaseAdapter, IngestParams
from discoursekit.ingest.runner import IngestRunError, run_ingest
from discoursekit.workflow.auto_pipeline import (
    CleanConfig,
    SourceConfig,
    WorkflowSummary,
    _compute_summary,
    _title_keyword_top_n,
    run_collect_clean_overview,
)


def _make_project(tmp_path, project_id: str = "proj1"):
    db_path = tmp_path / "project.db"
    conn = init_db(db_path)
    now = "2026-05-04T00:00:00+00:00"
    with conn:
        upsert_project(
            conn,
            {
                "project_id": project_id,
                "name": "Test Project",
                "created_at": now,
                "updated_at": now,
                "schema_version": "1.0",
                "description": "",
            },
        )
    conn.close()
    return db_path


def _make_test_db(tmp_path):
    db_path = _make_project(tmp_path)
    conn = get_connection(db_path)
    now = "2026-05-04T00:00:00+00:00"
    with conn:
        insert_ingest_run(
            conn,
            {
                "run_id": "run1",
                "project_id": "proj1",
                "source": "csv",
                "params_json": "{}",
                "started_at": now,
                "status": "success",
            },
        )
        for i in range(10):
            insert_article(
                conn,
                {
                    "article_id": f"test:{i:04d}",
                    "project_id": "proj1",
                    "ingest_run_id": "run1",
                    "source": "csv",
                    "date": f"2026-05-{(i % 28) + 1:02d}",
                    "publisher": ["조선일보", "한겨레", "경향신문"][i % 3],
                    "title": f"이태원동 상권 회복 기사 {i}",
                    "body_internal": f"이태원동 일대 음식점 매출이 증가했다. 기사 본문 {i}. " * 3,
                    "body_excerpt": "이태원동 일대 음식점 매출이 증가했다.",
                    "keywords": "이태원동,상권",
                    "url": f"https://example.com/{i}",
                    "raw_json": "{}",
                    "cleaned_at": "",
                },
            )
    conn.close()
    return db_path


def test_title_keyword_top_n(tmp_path):
    db_path = _make_test_db(tmp_path)
    conn = get_connection(db_path)
    result = _title_keyword_top_n(conn, "proj1", n=5)
    conn.close()

    assert len(result) <= 5
    assert "이태원동" in [keyword for keyword, _count in result]


def test_workflow_summary_fields():
    summary = WorkflowSummary(
        project_id="p1",
        raw_count=100,
        active_count=80,
        dropped_count=20,
        date_min="2026-01-01",
        date_max="2026-05-04",
        publisher_count=5,
        keyword_top_n=[("이태원동", 50)],
        ingest_run_id="r1",
        clean_run_id="r2",
        source_type="naver_news",
        source_depth="excerpt_only",
    )
    assert summary.dropped_count == 20
    assert summary.source_depth == "excerpt_only"


def test_source_config_defaults():
    config = SourceConfig(
        source_type="naver_news",
        query="이태원동",
        date_from="2022-10-01",
        date_to="2023-06-30",
    )
    assert config.display == 100
    assert config.sort == "date"
    assert config.max_results == 1000


def test_compute_summary(tmp_path):
    db_path = _make_test_db(tmp_path)
    summary = _compute_summary(db_path, "proj1", "run1", "", "csv", "full_body")

    assert summary.raw_count == 10
    assert summary.active_count == 10
    assert summary.publisher_count == 3
    assert summary.source_depth == "full_body"
    assert summary.keyword_top_n


def test_auto_pipeline_naver_mock(monkeypatch, tmp_path):
    db_path = _make_project(tmp_path)
    calls = []
    mock_payload = {
        "total": 1,
        "items": [
            {
                "title": "<b>이태원동</b> 안전 대책",
                "originallink": "https://www.hani.co.kr/article/1",
                "link": "https://n.news.naver.com/1",
                "description": "이태원동 안전 대책이 발표됐다. 시민 안전과 골목 관리 정책을 담았다.",
                "pubDate": "Mon, 04 May 2026 09:00:00 +0900",
            }
        ],
    }

    class MockResponse:
        status_code = 200

        def json(self):
            return mock_payload

        def raise_for_status(self):
            pass

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, headers=None, params=None):
            calls.append({"headers": headers, "params": params})
            return MockResponse()

    monkeypatch.setattr(
        "discoursekit.ingest.naver_news.httpx.Client",
        lambda **kwargs: MockClient(),
    )
    progress = []
    summary = run_collect_clean_overview(
        "proj1",
        SourceConfig(
            source_type="naver_news",
            query="이태원동",
            client_id="client",
            client_secret="secret",
            max_results=10,
        ),
        CleanConfig(min_body_chars=5),
        db_path,
        progress_callback=progress.append,
    )

    assert summary.raw_count == 1
    assert summary.active_count == 1
    assert summary.source_depth == "excerpt_only"
    assert progress == ["수집 중...", "정제 중...", "요약 생성 중..."]

    conn = get_connection(db_path)
    params_json = conn.execute("SELECT params_json FROM ingest_runs").fetchone()["params_json"]
    conn.close()
    assert "client" not in params_json
    assert "secret" not in params_json
    assert json.loads(params_json)["source"] == "naver_news"


def test_run_ingest_raises_after_recording_failure(tmp_path):
    db_path = _make_project(tmp_path)

    class FailingAdapter(BaseAdapter):
        @property
        def source_name(self):
            return "failing"

        def ingest(self, params):
            raise ValueError("boom")

    with pytest.raises(IngestRunError, match="boom"):
        run_ingest(
            FailingAdapter(),
            IngestParams(project_id="proj1", source="failing"),
            db_path,
        )

    conn = get_connection(db_path)
    row = conn.execute("SELECT status, error FROM ingest_runs").fetchone()
    conn.close()

    assert row["status"] == "failed"
    assert "boom" in row["error"]
