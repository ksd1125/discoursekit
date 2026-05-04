"""Cross-tabulation helpers for LLM labels and article metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from discoursekit.core.db import get_connection


@dataclass(frozen=True)
class CrossTabResult:
    """A simple integer matrix with row and column labels."""

    row_header: str
    col_header: str
    row_labels: list[str]
    col_labels: list[str]
    matrix: list[list[int]]


def cross_tab_label_publisher(db_path: Path, project_id: str, job_id: str) -> CrossTabResult:
    """Cross-tabulate LLM label by publisher for active articles."""
    return _cross_tab(db_path, project_id, job_id, "publisher")


def cross_tab_label_month(db_path: Path, project_id: str, job_id: str) -> CrossTabResult:
    """Cross-tabulate LLM label by month for active articles."""
    return _cross_tab(db_path, project_id, job_id, "month")


def _cross_tab(db_path: Path, project_id: str, job_id: str, column: str) -> CrossTabResult:
    if column == "publisher":
        select_expr = "COALESCE(NULLIF(a.publisher, ''), 'unknown')"
        col_header = "publisher"
    elif column == "month":
        select_expr = "SUBSTR(a.date, 1, 7)"
        col_header = "month"
    else:
        raise ValueError(f"Unsupported cross-tab column: {column}")

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT COALESCE(NULLIF(r.label, ''), 'unknown') AS label,
                   {select_expr} AS col_value,
                   COUNT(*) AS n
            FROM llm_results r
            JOIN articles a ON r.article_id = a.article_id
            WHERE r.job_id = ? AND a.project_id = ? AND a.is_active = 1
            GROUP BY label, col_value
            """,
            (job_id, project_id),
        ).fetchall()
    finally:
        conn.close()

    row_labels = sorted({row["label"] for row in rows})
    col_labels = sorted({row["col_value"] or "unknown" for row in rows})
    counts = {
        (row["label"], row["col_value"] or "unknown"): int(row["n"])
        for row in rows
    }
    matrix = [[counts.get((label, col), 0) for col in col_labels] for label in row_labels]
    return CrossTabResult("label", col_header, row_labels, col_labels, matrix)

