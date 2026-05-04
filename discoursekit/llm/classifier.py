"""LLM classifier with resume support."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from discoursekit.core.db import get_connection
from discoursekit.llm.providers import BaseLLMProvider, GeminiProvider, LLMRequest
from discoursekit.llm.slot_manager import GeminiSlotManager


@dataclass
class ClassifyConfig:
    """Configuration for a classification run."""

    project_id: str
    schema_id: str
    prompt_version_id: str
    prompt_text: str
    provider: str
    model: str
    temperature: float = 0.0
    sample_size: int = 0
    resume_job_id: str | None = None


@dataclass
class ClassifyProgress:
    """Real-time progress of a classification run."""

    job_id: str
    total: int
    processed: int
    errors: int
    prompt_tokens: int
    candidates_tokens: int
    estimated_cost_usd: float
    status: str

    @property
    def pct(self) -> float:
        return (self.processed / self.total * 100.0) if self.total > 0 else 0.0


async def run_classification(
    config: ClassifyConfig,
    db_path: Path,
    slot_manager: GeminiSlotManager | None = None,
    provider_instance: BaseLLMProvider | None = None,
    progress_callback=None,
) -> str:
    """Execute LLM classification on active articles with resume support."""
    conn = get_connection(db_path)
    try:
        if config.resume_job_id:
            job_id = config.resume_job_id
            existing = conn.execute("SELECT * FROM llm_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if existing is None:
                raise ValueError(f"Resume job {job_id!r} not found")
        else:
            job_id = str(uuid.uuid4())
            total_for_job = _count_selected_articles(conn, config)
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
                        config.schema_id,
                        config.prompt_version_id,
                        config.provider,
                        config.model,
                        config.temperature,
                        total_for_job,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

        done_ids = {
            row["article_id"]
            for row in conn.execute(
                "SELECT article_id FROM llm_results WHERE job_id = ?",
                (job_id,),
            ).fetchall()
        }
        selected_rows = _selected_article_rows(conn, config)
        selected_articles = [dict(row) for row in selected_rows]
        pending_articles = [article for article in selected_articles if article["article_id"] not in done_ids]
        total = len(selected_articles)

        provider = provider_instance or _provider_for_config(config)
        processed = len(done_ids & {article["article_id"] for article in selected_articles})
        errors = _current_job_errors(conn, job_id)
        prompt_tokens = _current_job_prompt_tokens(conn, job_id)
        candidates_tokens = _current_job_candidates_tokens(conn, job_id)

        for article in pending_articles:
            slot = None
            api_key = ""
            if slot_manager is not None:
                slot = slot_manager.get_next_available()
                if slot is None:
                    wait = slot_manager.min_wait_seconds()
                    if 0 < wait < 3600:
                        await asyncio.sleep(min(wait + 1, 60))
                        slot = slot_manager.get_next_available()
                if slot is None:
                    break
                api_key = slot.api_key

            request = LLMRequest(
                prompt=config.prompt_text,
                article_text=f"제목: {article['title']}\n본문: {article.get('body_internal', '')}",
                temperature=config.temperature,
            )
            response = await provider.call(request, api_key)

            if slot is not None:
                tokens_used = response.prompt_tokens + response.candidates_tokens
                slot.record_request(tokens_used)
                if response.error == "rate_limit_429":
                    slot.report_429("rpm")

            with conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO llm_results (
                        result_id, job_id, article_id, label, labels_json, confidence,
                        rationale, raw_response_json, called_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        job_id,
                        article["article_id"],
                        response.label,
                        response.labels_json,
                        response.confidence,
                        response.rationale,
                        json.dumps(response.raw_response, ensure_ascii=False)
                        if response.raw_response
                        else None,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

            processed += 1
            if not response.success:
                errors += 1
            prompt_tokens += response.prompt_tokens
            candidates_tokens += response.candidates_tokens
            _update_job_progress(conn, job_id, processed, errors, prompt_tokens, candidates_tokens)

            if progress_callback is not None:
                progress_callback(
                    ClassifyProgress(
                        job_id=job_id,
                        total=total,
                        processed=processed,
                        errors=errors,
                        prompt_tokens=prompt_tokens,
                        candidates_tokens=candidates_tokens,
                        estimated_cost_usd=_estimate_cost(
                            prompt_tokens,
                            candidates_tokens,
                            config.model,
                        ),
                        status="running",
                    )
                )

        final_status = "success" if processed >= total else "cancelled"
        with conn:
            conn.execute(
                """
                UPDATE llm_jobs SET
                    finished_at = ?, status = ?, n_processed = ?, n_errors = ?,
                    prompt_tokens = ?, candidates_tokens = ?, estimated_cost_usd = ?
                WHERE job_id = ?
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    final_status,
                    processed,
                    errors,
                    prompt_tokens,
                    candidates_tokens,
                    _estimate_cost(prompt_tokens, candidates_tokens, config.model),
                    job_id,
                ),
            )
        return job_id
    finally:
        conn.close()


def _provider_for_config(config: ClassifyConfig) -> BaseLLMProvider:
    if config.provider == "gemini":
        return GeminiProvider(config.model)
    raise ValueError(f"Provider {config.provider!r} not fully implemented in MVP")


def _count_selected_articles(conn, config: ClassifyConfig) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM articles WHERE project_id = ? AND is_active = 1",
        (config.project_id,),
    ).fetchone()
    total = row["n"]
    return min(config.sample_size, total) if config.sample_size > 0 else total


def _selected_article_rows(conn, config: ClassifyConfig):
    if config.sample_size > 0:
        return conn.execute(
            """
            SELECT article_id, title, body_internal
            FROM articles
            WHERE project_id = ? AND is_active = 1
            ORDER BY date, article_id
            LIMIT ?
            """,
            (config.project_id, config.sample_size),
        ).fetchall()
    return conn.execute(
        """
        SELECT article_id, title, body_internal
        FROM articles
        WHERE project_id = ? AND is_active = 1
        ORDER BY date, article_id
        """,
        (config.project_id,),
    ).fetchall()


def _current_job_errors(conn, job_id: str) -> int:
    row = conn.execute("SELECT COALESCE(n_errors, 0) AS n FROM llm_jobs WHERE job_id = ?", (job_id,)).fetchone()
    return int(row["n"]) if row else 0


def _current_job_prompt_tokens(conn, job_id: str) -> int:
    row = conn.execute("SELECT COALESCE(prompt_tokens, 0) AS n FROM llm_jobs WHERE job_id = ?", (job_id,)).fetchone()
    return int(row["n"]) if row else 0


def _current_job_candidates_tokens(conn, job_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(candidates_tokens, 0) AS n FROM llm_jobs WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    return int(row["n"]) if row else 0


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


def _estimate_cost(prompt_tokens: int, candidates_tokens: int, model: str) -> float:
    """Rough cost estimation for progress display."""
    if "flash" in model.lower():
        return (prompt_tokens * 0.15 + candidates_tokens * 0.60) / 1_000_000
    return (prompt_tokens * 1.0 + candidates_tokens * 2.0) / 1_000_000
