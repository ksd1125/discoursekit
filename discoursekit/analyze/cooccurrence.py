"""Co-occurrence analysis for keyword expansion."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from discoursekit.analyze.keywords import DEFAULT_STOPWORDS, _clean_token, _split_meta_keywords, _tokenize_with_kiwi
from discoursekit.core.db import get_connection


@dataclass(frozen=True)
class CooccurrenceResult:
    """Keywords that appear in articles containing a target keyword."""

    target_keyword: str
    cooccurrences: list[tuple[str, int]]
    article_count: int


def compute_cooccurrence(
    db_path: Path,
    project_id: str,
    target_keyword: str,
    top_n: int = 20,
) -> CooccurrenceResult:
    """Compute co-occurring keyword frequencies for articles matching target_keyword."""
    target = target_keyword.strip()
    if not target:
        return CooccurrenceResult(target_keyword="", cooccurrences=[], article_count=0)

    rows = _matching_rows(db_path, project_id, target)
    counter: Counter[str] = Counter()
    stopwords = set(DEFAULT_STOPWORDS)
    stopwords.add(target.lower())

    for row in rows:
        tokens = _tokens_for_row(row)
        for token in tokens:
            cleaned = _clean_token(token)
            if not cleaned or cleaned in stopwords or len(cleaned) <= 1 or cleaned.isdigit():
                continue
            counter[cleaned] += 1

    return CooccurrenceResult(
        target_keyword=target,
        cooccurrences=counter.most_common(top_n),
        article_count=len(rows),
    )


def _matching_rows(db_path: Path, project_id: str, target_keyword: str) -> list[dict]:
    pattern = f"%{target_keyword}%"
    conn = get_connection(db_path)
    try:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT title, body_excerpt, keywords
                FROM articles
                WHERE project_id = ? AND is_active = 1
                  AND (title LIKE ? OR body_excerpt LIKE ? OR keywords LIKE ?)
                ORDER BY date, article_id
                """,
                (project_id, pattern, pattern, pattern),
            ).fetchall()
        ]
    finally:
        conn.close()


def _tokens_for_row(row: dict) -> list[str]:
    text = f"{row.get('title') or ''} {row.get('body_excerpt') or ''}"
    try:
        tokens = _tokenize_with_kiwi(text)
        if tokens:
            return tokens
    except Exception:
        pass
    return _split_meta_keywords(row.get("keywords") or "")
