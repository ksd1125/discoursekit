"""LLM-assisted corpus enrichment runner."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from discoursekit.config import sha256_of_text
from discoursekit.core.db import get_connection
from discoursekit.llm.enrichment_prompts import (
    DEFAULT_SEMANTIC_TAGS,
    build_enrichment_prompt,
    get_prompt_version,
)
from discoursekit.llm.evidence_verify import verify_evidence_list
from discoursekit.llm.providers import BaseLLMProvider, GeminiProvider, LLMRequest, LLMResponse
from discoursekit.llm.slot_manager import GeminiProjectSlot, GeminiSlotManager


ENRICHMENT_SCHEMA_ID = "enrichment_v1"
ENRICHMENT_PROMPT_VERSION_ID = "enrich_v1"


@dataclass(frozen=True)
class EnrichmentConfig:
    """Configuration for one LLM enrichment run."""

    project_id: str
    job_id: str | None = None
    sample_size: int = 30
    sample_strategy: str = "random"
    options: list[str] | None = None
    relevance_threshold: float = 0.5
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"
    temperature: float = 0.0
    research_topic: str = ""
    query: str = ""
    semantic_tag_list: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None


@dataclass(frozen=True)
class EnrichmentResult:
    """Summary returned after an enrichment run."""

    job_id: str
    processed: int
    succeeded: int
    failed: int
    evidence_valid: int
    evidence_invalid: int
    avg_relevance_score: float
    action_counts: dict[str, int]


def run_sample_enrichment(
    config: EnrichmentConfig,
    db_path: Path,
    api_keys: list[dict] | list[str],
    provider_instance: BaseLLMProvider | None = None,
) -> EnrichmentResult:
    """Run sample-first enrichment for selected active articles."""
    if config.sample_size <= 0:
        raise ValueError("sample_size must be greater than 0 for sample enrichment")
    return asyncio.run(
        _run_enrichment(
            config=config,
            db_path=db_path,
            api_keys=api_keys,
            provider_instance=provider_instance,
            full_run=False,
            skip_reviewed=False,
        )
    )


def run_full_enrichment(
    config: EnrichmentConfig,
    db_path: Path,
    api_keys: list[dict] | list[str],
    skip_reviewed: bool = True,
    provider_instance: BaseLLMProvider | None = None,
) -> EnrichmentResult:
    """Run enrichment for all active articles, optionally skipping reviewed rows."""
    return asyncio.run(
        _run_enrichment(
            config=config,
            db_path=db_path,
            api_keys=api_keys,
            provider_instance=provider_instance,
            full_run=True,
            skip_reviewed=skip_reviewed,
        )
    )


def parse_enrichment_json(text: str) -> dict[str, Any]:
    """Parse an LLM response into the fixed enrichment JSON schema."""
    if not text or not text.strip():
        raise ValueError("Empty enrichment response")

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start < 0 or end <= start:
        raise ValueError("Enrichment response does not contain a JSON object")

    try:
        payload = json.loads(cleaned[start:end])
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid enrichment JSON") from exc

    return normalize_enrichment_payload(payload)


def normalize_enrichment_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize a parsed payload so required keys are present and typed."""
    if not isinstance(payload, dict):
        raise ValueError("Enrichment payload must be a JSON object")

    score = payload.get("relevance_score", 0.0)
    try:
        score = max(0.0, min(1.0, float(score)))
    except (TypeError, ValueError):
        score = 0.0

    action = str(payload.get("suggested_action") or "review")
    if action not in {"keep", "review", "drop_candidate"}:
        action = "review"
    noise_type = payload.get("noise_type")
    if noise_type not in {None, "ad", "duplicate_pattern", "off_topic", "generic"}:
        noise_type = None
    topic_relevance = str(payload.get("topic_relevance") or "core")
    if topic_relevance not in {"core", "related", "off_topic"}:
        topic_relevance = "core"

    return {
        "is_relevant": bool(payload.get("is_relevant", score >= 0.5)),
        "relevance_score": score,
        "relevance_reason": str(payload.get("relevance_reason") or ""),
        "quality_flags": _as_str_list(payload.get("quality_flags")),
        "semantic_tags": _as_str_list(payload.get("semantic_tags")),
        "noise_type": noise_type,
        "topic_relevance": topic_relevance,
        "canonical_places": _as_str_list(payload.get("canonical_places")),
        "canonical_events": _as_str_list(payload.get("canonical_events")),
        "canonical_actors": _as_str_list(payload.get("canonical_actors")),
        "evidence_sentences": _as_str_list(payload.get("evidence_sentences")),
        "suggested_action": action,
        "rationale": str(payload.get("rationale") or ""),
    }


async def _run_enrichment(
    config: EnrichmentConfig,
    db_path: Path,
    api_keys: list[dict] | list[str],
    provider_instance: BaseLLMProvider | None,
    full_run: bool,
    skip_reviewed: bool,
) -> EnrichmentResult:
    slot_manager = _slot_manager_from_api_keys(api_keys)
    if slot_manager.slot_count == 0:
        raise ValueError("At least one Gemini API key is required")

    conn = get_connection(db_path)
    try:
        _ensure_enrichment_columns(conn)
        _ensure_enrichment_schema(conn, config)
        job_id = _ensure_job(conn, config, full_run)
        done_ids = _done_article_ids(conn, job_id)
        articles = _selected_articles(conn, config, full_run, skip_reviewed)
        pending = [article for article in articles if article["article_id"] not in done_ids]

        provider = provider_instance or _provider_for_config(config)
        processed = len(done_ids & {article["article_id"] for article in articles})
        succeeded = 0
        failed = _current_job_errors(conn, job_id)
        prompt_tokens = _current_job_int(conn, job_id, "prompt_tokens")
        candidates_tokens = _current_job_int(conn, job_id, "candidates_tokens")
        evidence_valid = 0
        evidence_invalid = 0
        relevance_scores: list[float] = []
        action_counts: dict[str, int] = {}

        for article in pending:
            slot = slot_manager.get_next_available()
            if slot is None:
                break

            prompt = build_enrichment_prompt(
                _effective_config(config),
                title=article["title"],
                body=article["body_internal"] or article["body_excerpt"] or "",
            )
            response = await provider.call(
                LLMRequest(prompt=prompt, article_text="", temperature=config.temperature, max_tokens=1024),
                slot.api_key,
            )
            tokens_used = response.prompt_tokens + response.candidates_tokens
            slot.record_request(tokens_used)
            if response.error == "rate_limit_429":
                slot.report_429("rpm")

            processed += 1
            prompt_tokens += response.prompt_tokens
            candidates_tokens += response.candidates_tokens

            try:
                enrichment = _payload_from_response(response)
                verified_evidence, valid_count, invalid_count = verify_evidence_list(
                    enrichment.get("evidence_sentences", []),
                    article["body_internal"] or article["body_excerpt"] or "",
                )
                enrichment["evidence_sentences"] = verified_evidence
                evidence_valid += valid_count
                evidence_invalid += invalid_count
                score = float(enrichment["relevance_score"])
                action = _action_for_payload(enrichment, config.relevance_threshold)
                enrichment["suggested_action"] = action
                relevance_scores.append(score)
                action_counts[action] = action_counts.get(action, 0) + 1
                labels_json = _labels_json(
                    enrichment=enrichment,
                    config=config,
                    valid_count=valid_count,
                    invalid_count=invalid_count,
                )
                _insert_enrichment_result(
                    conn,
                    job_id=job_id,
                    article_id=article["article_id"],
                    action=action,
                    confidence=score,
                    rationale=enrichment.get("rationale") or enrichment.get("relevance_reason") or "",
                    labels_json=labels_json,
                    raw_response=response.raw_response,
                    evidence_valid_count=valid_count,
                )
                succeeded += 1
            except Exception as exc:
                failed += 1
                _insert_error_result(conn, job_id, article["article_id"], str(exc), response)

            _update_job_progress(conn, job_id, processed, failed, prompt_tokens, candidates_tokens)

        final_status = "success" if processed >= len(articles) else "cancelled"
        _finish_job(conn, job_id, final_status, processed, failed, prompt_tokens, candidates_tokens, config.model)

        avg_score = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0
        return EnrichmentResult(
            job_id=job_id,
            processed=processed,
            succeeded=succeeded,
            failed=failed,
            evidence_valid=evidence_valid,
            evidence_invalid=evidence_invalid,
            avg_relevance_score=avg_score,
            action_counts=action_counts,
        )
    finally:
        conn.close()


def _effective_config(config: EnrichmentConfig) -> EnrichmentConfig:
    if config.options is not None and config.semantic_tag_list is not None:
        return config
    return EnrichmentConfig(
        **{
            **config.__dict__,
            "options": config.options
            or ["relevance", "quality_flags", "semantic_tags", "canonical_entities"],
            "semantic_tag_list": config.semantic_tag_list or DEFAULT_SEMANTIC_TAGS,
        }
    )


def _payload_from_response(response: LLMResponse) -> dict[str, Any]:
    if not response.success:
        raise ValueError(response.error or "LLM provider call failed")
    if response.labels_json:
        return parse_enrichment_json(response.labels_json)
    text = _candidate_text(response.raw_response)
    return parse_enrichment_json(text)


def _candidate_text(raw_response: dict | None) -> str:
    if not raw_response:
        return ""
    if "text" in raw_response:
        return str(raw_response["text"])
    candidates = raw_response.get("candidates") or []
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        if parts:
            return str(parts[0].get("text", ""))
    return json.dumps(raw_response, ensure_ascii=False)


def _labels_json(
    enrichment: dict[str, Any],
    config: EnrichmentConfig,
    valid_count: int,
    invalid_count: int,
) -> str:
    return json.dumps(
        {
            "enrichment": enrichment,
            "audit": {
                "prompt_version_id": ENRICHMENT_PROMPT_VERSION_ID,
                "model": config.model,
                "temperature": config.temperature,
                "schema_version": "llm_enrichment_v1",
                "evidence_valid_count": valid_count,
                "evidence_invalid_count": invalid_count,
                "needs_review": True,
                "human_review_status": "pending",
                "human_override": None,
            },
        },
        ensure_ascii=False,
    )


def _ensure_enrichment_columns(conn) -> None:
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(llm_results)").fetchall()
    }
    columns = {
        "evidence_valid": "INTEGER DEFAULT NULL",
        "human_review_status": "TEXT DEFAULT 'pending'",
        "human_override": "TEXT DEFAULT NULL",
        "reviewed_at": "TEXT DEFAULT NULL",
    }
    with conn:
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE llm_results ADD COLUMN {name} {definition}")


def _ensure_enrichment_schema(conn, config: EnrichmentConfig) -> None:
    now = datetime.now(timezone.utc).isoformat()
    effective = _effective_config(config)
    labels_json = json.dumps(
        {
            "options": effective.options,
            "semantic_tags": effective.semantic_tag_list,
            "schema_version": "llm_enrichment_v1",
        },
        ensure_ascii=False,
    )
    prompt_version = get_prompt_version(ENRICHMENT_PROMPT_VERSION_ID)
    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO label_schemas
                (schema_id, name, schema_type, labels_json, created_at, description)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ENRICHMENT_SCHEMA_ID,
                "Corpus Enrichment v1",
                "enrichment",
                labels_json,
                now,
                "LLM-assisted corpus cleaning and standardization schema",
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO prompt_versions
                (version_id, schema_id, prompt_text, created_at, sha256)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ENRICHMENT_PROMPT_VERSION_ID,
                ENRICHMENT_SCHEMA_ID,
                prompt_version["template"],
                now,
                prompt_version["sha256"],
            ),
        )


def _ensure_job(conn, config: EnrichmentConfig, full_run: bool) -> str:
    if config.job_id:
        row = conn.execute("SELECT job_id FROM llm_jobs WHERE job_id = ?", (config.job_id,)).fetchone()
        if row is None:
            raise ValueError(f"Resume job not found: {config.job_id}")
        return config.job_id

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    sample_size = 0 if full_run else config.sample_size
    with conn:
        conn.execute(
            """
            INSERT INTO llm_jobs (
                job_id, project_id, schema_id, prompt_version_id, provider, model,
                temperature, sample_size, started_at, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'running')
            """,
            (
                job_id,
                config.project_id,
                ENRICHMENT_SCHEMA_ID,
                ENRICHMENT_PROMPT_VERSION_ID,
                config.provider,
                config.model,
                config.temperature,
                sample_size,
                now,
            ),
        )
    return job_id


def _selected_articles(conn, config: EnrichmentConfig, full_run: bool, skip_reviewed: bool):
    params: list[Any] = [config.project_id]
    where = "WHERE a.project_id = ? AND a.is_active = 1"
    if skip_reviewed:
        where += """
            AND NOT EXISTS (
                SELECT 1 FROM llm_results r
                WHERE r.article_id = a.article_id
                  AND COALESCE(r.human_review_status, 'pending') != 'pending'
            )
        """

    order_by = {
        "random": "ORDER BY RANDOM()",
        "recent": "ORDER BY a.date DESC, a.article_id",
        "stratified": "ORDER BY a.publisher, a.date, a.article_id",
    }.get(config.sample_strategy, "ORDER BY RANDOM()")

    limit = ""
    if not full_run:
        limit = "LIMIT ?"
        params.append(config.sample_size)

    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT a.article_id, a.title, a.body_internal, a.body_excerpt, a.date, a.publisher
            FROM articles a
            {where}
            {order_by}
            {limit}
            """,
            tuple(params),
        ).fetchall()
    ]


def _done_article_ids(conn, job_id: str) -> set[str]:
    return {
        row["article_id"]
        for row in conn.execute(
            "SELECT article_id FROM llm_results WHERE job_id = ?",
            (job_id,),
        ).fetchall()
    }


def _insert_enrichment_result(
    conn,
    job_id: str,
    article_id: str,
    action: str,
    confidence: float,
    rationale: str,
    labels_json: str,
    raw_response: dict | None,
    evidence_valid_count: int,
) -> None:
    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO llm_results (
                result_id, job_id, article_id, label, labels_json, confidence,
                rationale, raw_response_json, called_at, evidence_valid,
                human_review_status, human_override, reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL)
            """,
            (
                str(uuid.uuid4()),
                job_id,
                article_id,
                action,
                labels_json,
                confidence,
                rationale,
                json.dumps(raw_response, ensure_ascii=False) if raw_response else None,
                datetime.now(timezone.utc).isoformat(),
                evidence_valid_count,
            ),
        )


def _insert_error_result(conn, job_id: str, article_id: str, error: str, response: LLMResponse) -> None:
    payload = json.dumps(
        {
            "enrichment": {},
            "audit": {
                "prompt_version_id": ENRICHMENT_PROMPT_VERSION_ID,
                "schema_version": "llm_enrichment_v1",
                "needs_review": True,
                "human_review_status": "pending",
                "error": error,
            },
        },
        ensure_ascii=False,
    )
    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO llm_results (
                result_id, job_id, article_id, label, labels_json, confidence,
                rationale, raw_response_json, called_at, evidence_valid,
                human_review_status
            )
            VALUES (?, ?, ?, 'review', ?, NULL, ?, ?, ?, 0, 'pending')
            """,
            (
                str(uuid.uuid4()),
                job_id,
                article_id,
                payload,
                error,
                json.dumps(response.raw_response, ensure_ascii=False) if response.raw_response else None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def _update_job_progress(
    conn,
    job_id: str,
    processed: int,
    errors: int,
    prompt_tokens: int,
    candidates_tokens: int,
) -> None:
    with conn:
        conn.execute(
            """
            UPDATE llm_jobs
            SET n_processed = ?, n_errors = ?, prompt_tokens = ?, candidates_tokens = ?
            WHERE job_id = ?
            """,
            (processed, errors, prompt_tokens, candidates_tokens, job_id),
        )


def _finish_job(
    conn,
    job_id: str,
    status: str,
    processed: int,
    errors: int,
    prompt_tokens: int,
    candidates_tokens: int,
    model: str,
) -> None:
    with conn:
        conn.execute(
            """
            UPDATE llm_jobs
            SET finished_at = ?, status = ?, n_processed = ?, n_errors = ?,
                prompt_tokens = ?, candidates_tokens = ?, estimated_cost_usd = ?
            WHERE job_id = ?
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                status,
                processed,
                errors,
                prompt_tokens,
                candidates_tokens,
                _estimate_cost(prompt_tokens, candidates_tokens, model),
                job_id,
            ),
        )


def _slot_manager_from_api_keys(api_keys: list[dict] | list[str]) -> GeminiSlotManager:
    manager = GeminiSlotManager()
    for idx, entry in enumerate(api_keys or [], start=1):
        api_key = _extract_api_key(entry)
        if api_key:
            manager.add_slot(GeminiProjectSlot(slot_name=f"slot_{idx}", api_key=api_key))
    return manager


def _extract_api_key(entry: dict | str) -> str:
    if isinstance(entry, str):
        return entry.strip()
    for key in ("api_key", "key", "client_secret", "gemini_key"):
        value = entry.get(key)
        if value:
            return str(value).strip()
    return ""


def _provider_for_config(config: EnrichmentConfig) -> BaseLLMProvider:
    if config.provider == "gemini":
        return GeminiProvider(config.model)
    raise ValueError(f"Provider {config.provider!r} is not implemented for enrichment")


def _action_for_payload(payload: dict[str, Any], relevance_threshold: float) -> str:
    action = payload.get("suggested_action")
    if action in {"keep", "review", "drop_candidate"}:
        return str(action)
    return "keep" if float(payload.get("relevance_score", 0.0)) >= relevance_threshold else "review"


def _current_job_errors(conn, job_id: str) -> int:
    return _current_job_int(conn, job_id, "n_errors")


def _current_job_int(conn, job_id: str, column: str) -> int:
    if column not in {"n_errors", "prompt_tokens", "candidates_tokens"}:
        raise ValueError(f"Unsupported job column: {column}")
    row = conn.execute(
        f"SELECT COALESCE({column}, 0) AS n FROM llm_jobs WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    return int(row["n"]) if row else 0


def _estimate_cost(prompt_tokens: int, candidates_tokens: int, model: str) -> float:
    if "flash" in model.lower():
        return (prompt_tokens * 0.15 + candidates_tokens * 0.60) / 1_000_000
    return (prompt_tokens * 1.0 + candidates_tokens * 2.0) / 1_000_000


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []
