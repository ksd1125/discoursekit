"""Before/after comparison analysis around a cutoff date."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from discoursekit.core.db import get_connection


@dataclass(frozen=True)
class BeforeAfterResult:
    """Count, keyword, and publisher comparison around a cutoff date."""

    cutoff_date: str
    before_count: int
    after_count: int
    ratio: float
    before_monthly_avg: float
    after_monthly_avg: float
    before_top_keywords: list[tuple[str, int]]
    after_top_keywords: list[tuple[str, int]]
    before_top_publishers: list[tuple[str, int]]
    after_top_publishers: list[tuple[str, int]]


def compare_before_after(
    db_path: Path,
    project_id: str,
    cutoff_date: str,
    keyword_top_n: int = 10,
    stopwords: list[str] | None = None,
) -> BeforeAfterResult:
    """Compare active articles before and after a cutoff date."""
    conn = get_connection(db_path)
    try:
        before_count, before_months = _count_and_months(conn, project_id, "<", cutoff_date)
        after_count, after_months = _count_and_months(conn, project_id, ">=", cutoff_date)
        before_keywords = _keyword_counts(conn, project_id, "<", cutoff_date, stopwords).most_common(keyword_top_n)
        after_keywords = _keyword_counts(conn, project_id, ">=", cutoff_date, stopwords).most_common(keyword_top_n)
        before_publishers = _publisher_counts(conn, project_id, "<", cutoff_date).most_common(keyword_top_n)
        after_publishers = _publisher_counts(conn, project_id, ">=", cutoff_date).most_common(keyword_top_n)
    finally:
        conn.close()

    return BeforeAfterResult(
        cutoff_date=cutoff_date,
        before_count=before_count,
        after_count=after_count,
        ratio=float("inf") if before_count == 0 and after_count > 0 else (after_count / before_count if before_count else 0.0),
        before_monthly_avg=before_count / before_months if before_months else 0.0,
        after_monthly_avg=after_count / after_months if after_months else 0.0,
        before_top_keywords=before_keywords,
        after_top_keywords=after_keywords,
        before_top_publishers=before_publishers,
        after_top_publishers=after_publishers,
    )


def _count_and_months(conn, project_id: str, op: str, cutoff_date: str) -> tuple[int, int]:
    if op not in {"<", ">="}:
        raise ValueError(f"Unsupported date operator: {op}")
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS n, COUNT(DISTINCT SUBSTR(date, 1, 7)) AS months
        FROM articles
        WHERE project_id = ? AND is_active = 1 AND date {op} ?
        """,
        (project_id, cutoff_date),
    ).fetchone()
    return int(row["n"] or 0), int(row["months"] or 0)


def _keyword_counts(conn, project_id: str, op: str, cutoff_date: str, stopwords: list[str] | None) -> Counter[str]:
    if op not in {"<", ">="}:
        raise ValueError(f"Unsupported date operator: {op}")
    stopword_set = {word.lower() for word in (stopwords or [])}
    rows = conn.execute(
        f"""
        SELECT keywords
        FROM articles
        WHERE project_id = ? AND is_active = 1 AND date {op} ?
          AND keywords IS NOT NULL
        """,
        (project_id, cutoff_date),
    ).fetchall()
    counter: Counter[str] = Counter()
    for row in rows:
        for keyword in str(row["keywords"] or "").split(","):
            cleaned = keyword.strip().lower()
            if cleaned and cleaned not in stopword_set:
                counter[cleaned] += 1
    return counter


def _publisher_counts(conn, project_id: str, op: str, cutoff_date: str) -> Counter[str]:
    if op not in {"<", ">="}:
        raise ValueError(f"Unsupported date operator: {op}")
    rows = conn.execute(
        f"""
        SELECT COALESCE(NULLIF(publisher, ''), 'unknown') AS publisher, COUNT(*) AS n
        FROM articles
        WHERE project_id = ? AND is_active = 1 AND date {op} ?
        GROUP BY publisher
        """,
        (project_id, cutoff_date),
    ).fetchall()
    return Counter({row["publisher"]: int(row["n"]) for row in rows})
