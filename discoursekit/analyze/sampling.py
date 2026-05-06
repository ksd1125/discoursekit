"""Representative article sampling helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from discoursekit.core.db import get_connection


@dataclass(frozen=True)
class SamplingResult:
    """Sampled article list without internal body text."""

    strategy: str
    articles: list[dict]
    sample_size: int
    population_size: int


def sample_representative_articles(
    db_path: Path,
    project_id: str,
    strategy: str = "random",
    n: int = 10,
    cutoff_date: str | None = None,
    keyword: str | None = None,
) -> SamplingResult:
    """Sample representative active articles using a simple strategy."""
    conn = get_connection(db_path)
    try:
        population_size = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM articles WHERE project_id = ? AND is_active = 1",
                (project_id,),
            ).fetchone()["n"]
        )
        if population_size == 0 or n <= 0:
            return SamplingResult(strategy=strategy, articles=[], sample_size=0, population_size=population_size)

        if strategy == "peak_period":
            articles = _sample_peak_period(conn, project_id, n)
        elif strategy == "keyword_match":
            articles = _sample_keyword_match(conn, project_id, n, keyword)
        elif strategy == "stratified":
            articles = _sample_stratified(conn, project_id, n)
        elif strategy == "recent":
            articles = _sample_recent(conn, project_id, n)
        else:
            articles = _sample_random(conn, project_id, n)
    finally:
        conn.close()

    return SamplingResult(
        strategy=strategy,
        articles=articles,
        sample_size=len(articles),
        population_size=population_size,
    )


def _sample_random(conn, project_id: str, n: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT article_id, title, date, publisher
        FROM articles
        WHERE project_id = ? AND is_active = 1
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (project_id, n),
    ).fetchall()
    return [_row_with_reason(row, "random: random sample") for row in rows]


def _sample_recent(conn, project_id: str, n: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT article_id, title, date, publisher
        FROM articles
        WHERE project_id = ? AND is_active = 1
        ORDER BY date DESC, article_id
        LIMIT ?
        """,
        (project_id, n),
    ).fetchall()
    return [_row_with_reason(row, "recent: most recent active articles") for row in rows]


def _sample_keyword_match(conn, project_id: str, n: int, keyword: str | None) -> list[dict]:
    if not keyword:
        return []
    pattern = f"%{keyword}%"
    rows = conn.execute(
        """
        SELECT article_id, title, date, publisher
        FROM articles
        WHERE project_id = ? AND is_active = 1
          AND (title LIKE ? OR body_excerpt LIKE ?)
        ORDER BY date DESC, article_id
        LIMIT ?
        """,
        (project_id, pattern, pattern, n),
    ).fetchall()
    return [_row_with_reason(row, f"keyword_match: '{keyword}' included") for row in rows]


def _sample_peak_period(conn, project_id: str, n: int) -> list[dict]:
    peak = conn.execute(
        """
        SELECT SUBSTR(date, 1, 7) AS period, COUNT(*) AS n
        FROM articles
        WHERE project_id = ? AND is_active = 1
        GROUP BY period
        ORDER BY n DESC, period
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    if not peak:
        return []
    rows = conn.execute(
        """
        SELECT article_id, title, date, publisher
        FROM articles
        WHERE project_id = ? AND is_active = 1 AND SUBSTR(date, 1, 7) = ?
        ORDER BY date, article_id
        LIMIT ?
        """,
        (project_id, peak["period"], n),
    ).fetchall()
    return [_row_with_reason(row, f"peak_period: highest volume period ({peak['period']})") for row in rows]


def _sample_stratified(conn, project_id: str, n: int) -> list[dict]:
    publishers = conn.execute(
        """
        SELECT COALESCE(NULLIF(publisher, ''), 'unknown') AS publisher, COUNT(*) AS n
        FROM articles
        WHERE project_id = ? AND is_active = 1
        GROUP BY publisher
        ORDER BY n DESC, publisher
        LIMIT ?
        """,
        (project_id, n),
    ).fetchall()
    articles = []
    for publisher in publishers:
        row = conn.execute(
            """
            SELECT article_id, title, date, publisher
            FROM articles
            WHERE project_id = ? AND is_active = 1
              AND COALESCE(NULLIF(publisher, ''), 'unknown') = ?
            ORDER BY date DESC, article_id
            LIMIT 1
            """,
            (project_id, publisher["publisher"]),
        ).fetchone()
        if row:
            articles.append(_row_with_reason(row, f"stratified: publisher stratum {publisher['publisher']}"))
    return articles[:n]


def _row_with_reason(row, reason: str) -> dict:
    return {
        "article_id": row["article_id"],
        "title": row["title"],
        "date": row["date"],
        "publisher": row["publisher"] or "",
        "reason": reason,
    }
