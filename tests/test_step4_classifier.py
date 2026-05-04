"""Step 4 classifier tests using a mock provider."""

from __future__ import annotations

import asyncio
from pathlib import Path

from discoursekit.core.db import get_connection, init_db, insert_article, upsert_project
from discoursekit.llm.classifier import ClassifyConfig, run_classification
from discoursekit.llm.providers import BaseLLMProvider, LLMRequest, LLMResponse


class MockProvider(BaseLLMProvider):
    """Mock provider that returns deterministic labels."""

    def __init__(self) -> None:
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-v1"

    async def call(self, request: LLMRequest, api_key: str) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            label="relevant",
            confidence=0.95,
            rationale="Test rationale",
            raw_response={"mock": True},
            prompt_tokens=100,
            candidates_tokens=20,
            success=True,
        )


def _setup_project_with_articles(tmp_path, n: int = 5) -> Path:
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
        conn.execute(
            """
            INSERT INTO ingest_runs (run_id, project_id, source, params_json, started_at, status)
            VALUES ('r1', 'p1', 'test', '{}', ?, 'success')
            """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO label_schemas (schema_id, name, schema_type, labels_json, created_at)
            VALUES ('rel_v1', 'Relevance', 'single_label', '[]', ?)
            """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO prompt_versions (version_id, schema_id, prompt_text, created_at, sha256)
            VALUES ('rel_v1.0', 'rel_v1', 'classify this', ?, 'abc123')
            """,
            (now,),
        )
        for i in range(n):
            insert_article(
                conn,
                {
                    "article_id": f"test:art{i}",
                    "project_id": "p1",
                    "source": "test",
                    "date": "2022-10-30",
                    "publisher": "pub",
                    "title": f"Article {i}",
                    "body_internal": f"Body text for article {i} with enough content",
                    "body_excerpt": f"Body text for article {i}",
                    "keywords": "",
                    "url": "",
                    "raw_json": "{}",
                    "cleaned_at": now,
                },
                ingest_run_id="r1",
            )
    conn.close()
    return db_path


def _config(sample_size: int = 0, resume_job_id: str | None = None) -> ClassifyConfig:
    return ClassifyConfig(
        project_id="p1",
        schema_id="rel_v1",
        prompt_version_id="rel_v1.0",
        prompt_text="classify this",
        provider="mock",
        model="mock-v1",
        sample_size=sample_size,
        resume_job_id=resume_job_id,
    )


def test_classify_basic(tmp_path):
    db_path = _setup_project_with_articles(tmp_path, n=3)
    mock = MockProvider()
    job_id = asyncio.run(run_classification(_config(), db_path, provider_instance=mock))
    assert mock.call_count == 3

    conn = get_connection(db_path)
    job = conn.execute("SELECT * FROM llm_jobs WHERE job_id=?", (job_id,)).fetchone()
    assert dict(job)["status"] == "success"
    assert dict(job)["n_processed"] == 3
    results = conn.execute(
        "SELECT COUNT(*) AS n FROM llm_results WHERE job_id=?",
        (job_id,),
    ).fetchone()
    assert results["n"] == 3
    conn.close()


def test_classify_resume(tmp_path):
    db_path = _setup_project_with_articles(tmp_path, n=5)
    mock = MockProvider()
    job_id = asyncio.run(run_classification(_config(sample_size=3), db_path, provider_instance=mock))
    assert mock.call_count == 3

    mock2 = MockProvider()
    asyncio.run(
        run_classification(
            _config(sample_size=3, resume_job_id=job_id),
            db_path,
            provider_instance=mock2,
        )
    )
    assert mock2.call_count == 0


def test_classify_result_has_label(tmp_path):
    db_path = _setup_project_with_articles(tmp_path, n=1)
    mock = MockProvider()
    job_id = asyncio.run(run_classification(_config(), db_path, provider_instance=mock))
    conn = get_connection(db_path)
    result = conn.execute("SELECT * FROM llm_results WHERE job_id=?", (job_id,)).fetchone()
    assert dict(result)["label"] == "relevant"
    assert dict(result)["confidence"] == 0.95
    conn.close()


def test_classify_unique_constraint(tmp_path):
    db_path = _setup_project_with_articles(tmp_path, n=2)
    mock = MockProvider()
    job_id = asyncio.run(run_classification(_config(), db_path, provider_instance=mock))
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO llm_results
                (result_id, job_id, article_id, label, called_at)
            VALUES ('dup', ?, 'test:art0', 'x', '2026-01-01')
            """,
            (job_id,),
        )
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM llm_results WHERE job_id=?",
        (job_id,),
    ).fetchone()["n"]
    assert count == 2
    conn.close()


def test_classify_progress_callback(tmp_path):
    db_path = _setup_project_with_articles(tmp_path, n=2)
    mock = MockProvider()
    progress_log = []
    asyncio.run(
        run_classification(
            _config(),
            db_path,
            provider_instance=mock,
            progress_callback=lambda progress: progress_log.append(progress),
        )
    )
    assert len(progress_log) == 2
    assert progress_log[-1].processed == 2
