"""Article domain model."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping


def _get(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


@dataclass(frozen=True)
class Article:
    """Immutable representation of one collected and cleaned article."""

    article_id: str
    source: str
    date: str
    publisher: str
    title: str
    body_internal: str
    body_excerpt: str
    keywords: list[str]
    url: str
    raw: dict
    cleaned_at: str
    project_id: str

    def to_db_row(self) -> dict:
        """Return a dict suitable for INSERT into the articles table."""
        return {
            "article_id": self.article_id,
            "project_id": self.project_id,
            "source": self.source,
            "date": self.date,
            "publisher": self.publisher,
            "title": self.title,
            "body_internal": self.body_internal,
            "body_excerpt": self.body_excerpt,
            "keywords": ", ".join(self.keywords),
            "url": self.url,
            "raw_json": json.dumps(self.raw, ensure_ascii=False),
            "cleaned_at": self.cleaned_at,
        }

    @classmethod
    def from_db_row(cls, row: Mapping[str, Any]) -> "Article":
        """Reconstruct an Article from a row fetched from the articles table."""
        raw_json = _get(row, "raw_json", "{}") or "{}"
        keywords = _get(row, "keywords", "") or ""
        return cls(
            article_id=_get(row, "article_id"),
            project_id=_get(row, "project_id"),
            source=_get(row, "source"),
            date=_get(row, "date"),
            publisher=_get(row, "publisher", "") or "",
            title=_get(row, "title"),
            body_internal=_get(row, "body_internal", "") or "",
            body_excerpt=_get(row, "body_excerpt", "") or "",
            keywords=[k.strip() for k in keywords.split(",") if k.strip()],
            url=_get(row, "url", "") or "",
            raw=json.loads(raw_json),
            cleaned_at=_get(row, "cleaned_at", "") or "",
        )
