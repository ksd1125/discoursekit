"""LLM enrichment runner tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from discoursekit.core.db import get_connection, init_db, insert_article, upsert_project
from discoursekit.llm.enrichment import (
    EnrichmentConfig,
    EnrichmentResult,
    normalize_enrichment_payload,
    parse_enrichment_json,
    run_sample_enrichment,
)
from discoursekit.llm.providers import BaseLLMProvider, LLMRequest, LLMResponse


class MockEnrichmentProvider(BaseLLMProvider):
    def __init__(self, payload: dict | None = None) -> None:
        self.call_count = 0
        self.payload = payload or {
            "is_relevant": True,
            "relevance_score": 0.88,
            "relevance_reason": "Directly relevant to the topic.",
            "quality_flags": [],
            "semantic_tags": ["local_place", "recovery"],
            "canonical_places": ["Itaewon-dong"],
            "canonical_events": [],
            "canonical_actors": [],
            "evidence_sentences": ["Itaewon local restaurants recovered."],
            "suggested_action": "keep",
            "rationale": "The text discusses Itaewon recovery.",
        }

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-enrich-v1"

    async def call(self, request: LLMRequest, api_key: str) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            labels_json=json.dumps(self.payload, ensure_ascii=False),
            raw_response={"mock": True},
            prompt_tokens=100,
            candidates_tokens=25,
            success=True,
        )


def _setup_project(tmp_path, n: int = 3) -> Path:
    db_path = tmp_path / "project.db"
    conn = init_db(db_path)
    now = "2026-05-05T00:00:00+00:00"
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
        for i in range(n):
            insert_article(
                conn,
                {
                    "article_id": f"art{i}",
                    "project_id": "p1",
                    "source": "test",
                    "date": f"2022-10-{30 + i:02d}",
                    "publisher": "pub",
                    "title": f"Itaewon recovery article {i}",
                    "body_internal": "Itaewon local restaurants recovered.",
                    "body_excerpt": "Itaewon local restaurants recovered.",
                    "keywords": "",
                    "url": "",
                    "raw_json": "{}",
                    "cleaned_at": now,
                },
                ingest_run_id="r1",
            )
    conn.close()
    return db_path


def _config(sample_size: int = 2) -> EnrichmentConfig:
    return EnrichmentConfig(
        project_id="p1",
        sample_size=sample_size,
        sample_strategy="recent",
        options=["relevance", "quality_flags", "semantic_tags", "canonical_entities", "evidence_sentences"],
        research_topic="Itaewon recovery discourse",
        query="Itaewon",
        semantic_tag_list=["local_place", "recovery", "other"],
        date_from="2022-10-01",
        date_to="2022-12-31",
    )


def test_enrichment_config_creation():
    config = _config()

    assert config.project_id == "p1"
    assert config.sample_size == 2


def test_enrichment_result_creation():
    result = EnrichmentResult(
        job_id="j1",
        processed=2,
        succeeded=2,
        failed=0,
        evidence_valid=1,
        evidence_invalid=0,
        avg_relevance_score=0.8,
        action_counts={"keep": 2},
    )

    assert result.action_counts["keep"] == 2


def test_run_sample_mock(tmp_path):
    db_path = _setup_project(tmp_path, n=3)
    provider = MockEnrichmentProvider()

    result = run_sample_enrichment(
        _config(sample_size=2),
        db_path,
        [{"api_key": "test-key"}],
        provider_instance=provider,
    )

    assert result.processed == 2
    assert result.succeeded == 2
    assert result.failed == 0
    assert result.evidence_valid == 2
    assert provider.call_count == 2

    conn = get_connection(db_path)
    rows = conn.execute("SELECT * FROM llm_results WHERE job_id = ?", (result.job_id,)).fetchall()
    job = conn.execute("SELECT * FROM llm_jobs WHERE job_id = ?", (result.job_id,)).fetchone()
    conn.close()

    assert len(rows) == 2
    assert job["schema_id"] == "enrichment_v1"
    labels = json.loads(rows[0]["labels_json"])
    assert labels["audit"]["prompt_version_id"] == "enrich_v1"
    assert labels["audit"]["schema_version"] == "llm_enrichment_v1"
    assert labels["audit"]["human_review_status"] == "pending"
    assert rows[0]["human_review_status"] == "pending"
    assert rows[0]["label"] == "keep"


def test_run_sample_api_key_missing(tmp_path):
    db_path = _setup_project(tmp_path, n=1)

    with pytest.raises(ValueError, match="API key"):
        run_sample_enrichment(_config(sample_size=1), db_path, [], provider_instance=MockEnrichmentProvider())


def test_enrichment_json_parse():
    payload = parse_enrichment_json(
        """
        {"is_relevant": true, "relevance_score": 0.7, "suggested_action": "keep"}
        """
    )

    assert payload["is_relevant"] is True
    assert payload["relevance_score"] == 0.7
    assert payload["suggested_action"] == "keep"


def test_enrichment_normalizes_noise_fields():
    payload = normalize_enrichment_payload(
        {
            "relevance_score": 0.6,
            "noise_type": "ad",
            "topic_relevance": "related",
        }
    )

    assert payload["noise_type"] == "ad"
    assert payload["topic_relevance"] == "related"


def test_enrichment_json_invalid():
    with pytest.raises(ValueError):
        parse_enrichment_json("not json")


def test_labels_json_no_api_key(tmp_path):
    db_path = _setup_project(tmp_path, n=1)
    result = run_sample_enrichment(
        _config(sample_size=1),
        db_path,
        [{"api_key": "secret-key"}],
        provider_instance=MockEnrichmentProvider(),
    )

    conn = get_connection(db_path)
    row = conn.execute("SELECT labels_json FROM llm_results WHERE job_id = ?", (result.job_id,)).fetchone()
    conn.close()

    assert "secret-key" not in row["labels_json"]
