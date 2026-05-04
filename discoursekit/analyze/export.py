"""Safe export utilities.

Exports never include ``body_internal``. Only ``body_excerpt`` may leave the
project database.
"""

from __future__ import annotations

import csv
from pathlib import Path

from discoursekit.core.db import get_connection


ARTICLE_EXPORT_COLUMNS: tuple[str, ...] = (
    "article_id",
    "source",
    "date",
    "publisher",
    "title",
    "body_excerpt",
    "keywords",
    "url",
    "cleaned_at",
    "is_active",
)

RESULT_EXPORT_COLUMNS: tuple[str, ...] = (
    "article_id",
    "date",
    "publisher",
    "title",
    "body_excerpt",
    "label",
    "confidence",
    "rationale",
    "called_at",
)


def export_articles_parquet(
    db_path: Path,
    project_id: str,
    output_path: Path,
    active_only: bool = True,
) -> Path:
    """Export articles to Parquet when an engine exists, otherwise CSV fallback.

    The fallback keeps the requested path so batch workflows do not crash on
    minimal machines, but writes comma-separated text with the same safe columns.
    """
    rows = _article_rows(db_path, project_id, active_only)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    engine = _parquet_engine()
    if engine:
        import pandas as pd

        pd.DataFrame(rows, columns=ARTICLE_EXPORT_COLUMNS).to_parquet(
            output_path,
            index=False,
            engine=engine,
        )
    else:
        _write_csv_rows(output_path, ARTICLE_EXPORT_COLUMNS, rows)
    return output_path


def export_articles_csv(
    db_path: Path,
    project_id: str,
    output_path: Path,
    active_only: bool = True,
) -> Path:
    """Export articles to CSV with body excerpts only."""
    rows = _article_rows(db_path, project_id, active_only)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv_rows(output_path, ARTICLE_EXPORT_COLUMNS, rows, encoding="utf-8-sig")
    return output_path


def export_results_csv(db_path: Path, project_id: str, job_id: str, output_path: Path) -> Path:
    """Export LLM results joined to articles as CSV with body excerpts only."""
    conn = get_connection(db_path)
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT a.article_id, a.date, a.publisher, a.title, a.body_excerpt,
                       r.label, r.confidence, r.rationale, r.called_at
                FROM llm_results r
                JOIN articles a ON r.article_id = a.article_id
                WHERE r.job_id = ? AND a.project_id = ? AND a.is_active = 1
                ORDER BY a.date, a.article_id
                """,
                (job_id, project_id),
            ).fetchall()
        ]
    finally:
        conn.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv_rows(output_path, RESULT_EXPORT_COLUMNS, rows, encoding="utf-8-sig")
    return output_path


def _article_rows(db_path: Path, project_id: str, active_only: bool) -> list[dict[str, object]]:
    conn = get_connection(db_path)
    try:
        query = """
            SELECT article_id, source, date, publisher, title, body_excerpt,
                   keywords, url, cleaned_at, is_active
            FROM articles
            WHERE project_id = ?
        """
        params: list[object] = [project_id]
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY date, article_id"
        return [dict(row) for row in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


def _write_csv_rows(
    output_path: Path,
    columns: tuple[str, ...],
    rows: list[dict[str, object]],
    encoding: str = "utf-8",
) -> None:
    with output_path.open("w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _parquet_engine() -> str | None:
    for engine in ("pyarrow", "fastparquet"):
        try:
            __import__(engine)
        except ImportError:
            continue
        return engine
    return None
