"""Clean pipeline - text normalization, deduplication, filtering, and DB updates."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from discoursekit.config import BODY_EXCERPT_MAX_LEN
from discoursekit.clean.dedup import run_dedup
from discoursekit.clean.filters import run_filters
from discoursekit.clean.text_utils import clean_body, make_excerpt
from discoursekit.core.db import get_connection, insert_clean_run


def run_clean_pipeline(
    db_path: Path,
    project_id: str,
    min_body_chars: int = 20,
    similarity_threshold: float = 0.85,
) -> str:
    """Execute the full cleaning pipeline on a project."""
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection(db_path)

    params_dict = {
        "min_body_chars": min_body_chars,
        "similarity_threshold": similarity_threshold,
    }
    with conn:
        insert_clean_run(
            conn,
            {
                "run_id": run_id,
                "project_id": project_id,
                "params_json": json.dumps(params_dict, ensure_ascii=False),
                "started_at": started_at,
                "status": "running",
            },
        )

    try:
        rows = conn.execute(
            """
            SELECT article_id, title, date, publisher, body_internal, body_excerpt
            FROM articles
            WHERE project_id = ? AND is_active = 1
            """,
            (project_id,),
        ).fetchall()
        articles = [dict(row) for row in rows]
        input_count = len(articles)

        cleaned_at = datetime.now(timezone.utc).isoformat()
        for article in articles:
            cleaned = clean_body(article.get("body_internal") or "")
            article["body_internal"] = cleaned
            article["body_excerpt"] = make_excerpt(cleaned, BODY_EXCERPT_MAX_LEN)

        with conn:
            for article in articles:
                conn.execute(
                    """
                    UPDATE articles
                    SET body_internal = ?, body_excerpt = ?, cleaned_at = ?
                    WHERE article_id = ?
                    """,
                    (
                        article["body_internal"],
                        article["body_excerpt"],
                        cleaned_at,
                        article["article_id"],
                    ),
                )

        dedup_result = run_dedup(articles, similarity_threshold)
        surviving_ids = set(dedup_result.kept_ids)
        surviving_articles = [
            article for article in articles if article["article_id"] in surviving_ids
        ]
        filter_result = run_filters(surviving_articles, min_body_chars)

        removed_ids = (
            set(dedup_result.primary_dup_ids)
            | set(dedup_result.fallback_dup_ids)
            | set(filter_result.dropped_short)
            | set(filter_result.dropped_advert)
            | set(filter_result.dropped_other)
        )
        if removed_ids:
            placeholders = ",".join("?" for _ in removed_ids)
            with conn:
                conn.execute(
                    f"UPDATE articles SET is_active = 0 WHERE article_id IN ({placeholders})",
                    list(removed_ids),
                )

        output_count = len(filter_result.kept_ids)
        with conn:
            conn.execute(
                """
                UPDATE clean_runs SET
                    finished_at = ?, status = 'success',
                    input_count = ?, output_count = ?,
                    dedup_primary = ?, dedup_fallback = ?,
                    dropped_short = ?, dropped_advert = ?
                WHERE run_id = ?
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    input_count,
                    output_count,
                    len(dedup_result.primary_dup_ids),
                    len(dedup_result.fallback_dup_ids),
                    len(filter_result.dropped_short),
                    len(filter_result.dropped_advert),
                    run_id,
                ),
            )
    except Exception:
        with conn:
            conn.execute(
                """
                UPDATE clean_runs
                SET finished_at = ?, status = 'failed', input_count = 0, output_count = 0
                WHERE run_id = ?
                """,
                (datetime.now(timezone.utc).isoformat(), run_id),
            )
        raise
    finally:
        conn.close()

    return run_id
