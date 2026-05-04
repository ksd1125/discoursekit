"""Descriptive statistics for article collections."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from discoursekit.core.db import get_connection


@dataclass(frozen=True)
class DescriptiveStats:
    """Summary statistics for one project's active and total article set."""

    total_articles: int
    active_articles: int
    date_min: str
    date_max: str
    publisher_counts: dict[str, int]
    source_counts: dict[str, int]
    keyword_top_n: list[tuple[str, int]]
    body_length_stats: dict[str, float]


def compute_descriptive(db_path: Path, project_id: str) -> DescriptiveStats:
    """Compute counts, ranges, keywords, and body-length stats for active articles."""
    conn = get_connection(db_path)
    try:
        total = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM articles WHERE project_id = ?",
                (project_id,),
            ).fetchone()["n"]
        )
        active = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM articles WHERE project_id = ? AND is_active = 1",
                (project_id,),
            ).fetchone()["n"]
        )
        date_range = conn.execute(
            """
            SELECT MIN(date) AS d_min, MAX(date) AS d_max
            FROM articles
            WHERE project_id = ? AND is_active = 1
            """,
            (project_id,),
        ).fetchone()
        publisher_counts = _group_counts(conn, project_id, "publisher")
        source_counts = _group_counts(conn, project_id, "source")
        keyword_top_n = _keyword_counts(conn, project_id).most_common(50)
        body_length_stats = _body_length_stats(conn, project_id)
    finally:
        conn.close()

    return DescriptiveStats(
        total_articles=total,
        active_articles=active,
        date_min=date_range["d_min"] or "",
        date_max=date_range["d_max"] or "",
        publisher_counts=publisher_counts,
        source_counts=source_counts,
        keyword_top_n=keyword_top_n,
        body_length_stats=body_length_stats,
    )


def _group_counts(conn, project_id: str, column: str) -> dict[str, int]:
    if column not in {"publisher", "source"}:
        raise ValueError(f"Unsupported grouping column: {column}")
    rows = conn.execute(
        f"""
        SELECT COALESCE(NULLIF({column}, ''), 'unknown') AS value, COUNT(*) AS n
        FROM articles
        WHERE project_id = ? AND is_active = 1
        GROUP BY value
        ORDER BY n DESC, value
        """,
        (project_id,),
    ).fetchall()
    return {row["value"]: int(row["n"]) for row in rows}


def _keyword_counts(conn, project_id: str) -> Counter[str]:
    rows = conn.execute(
        """
        SELECT keywords
        FROM articles
        WHERE project_id = ? AND is_active = 1 AND keywords IS NOT NULL
        """,
        (project_id,),
    ).fetchall()
    counter: Counter[str] = Counter()
    for row in rows:
        for keyword in str(row["keywords"]).split(","):
            cleaned = keyword.strip()
            if cleaned:
                counter[cleaned] += 1
    return counter


def _body_length_stats(conn, project_id: str) -> dict[str, float]:
    rows = conn.execute(
        """
        SELECT LENGTH(body_internal) AS n
        FROM articles
        WHERE project_id = ? AND is_active = 1 AND body_internal IS NOT NULL
        """,
        (project_id,),
    ).fetchall()
    lengths = sorted(int(row["n"]) for row in rows if row["n"])
    if not lengths:
        return {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": sum(lengths) / len(lengths),
        "median": float(median(lengths)),
        "min": float(lengths[0]),
        "max": float(lengths[-1]),
    }

