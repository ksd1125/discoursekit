"""Base adapter interface for all data source adapters."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from discoursekit.core.article import Article


@dataclass
class IngestParams:
    """Common parameters for an ingest run."""

    project_id: str
    source: str
    input_path: Path | None = None
    query: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    display: int = 100
    sort: str = "date"
    max_results: int = 1000
    client_id: str | None = None
    client_secret: str | None = None

    def to_json_dict(self) -> dict:
        """Return log-safe params. API credentials are intentionally excluded."""
        return {
            "project_id": self.project_id,
            "source": self.source,
            "input_path": str(self.input_path) if self.input_path else None,
            "query": self.query,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "display": self.display,
            "sort": self.sort,
            "max_results": self.max_results,
        }


def generate_article_id(source: str, unique_key: str) -> str:
    """Generate a deterministic article_id: source:sha1(unique_key)."""
    sha1 = hashlib.sha1(unique_key.encode("utf-8")).hexdigest()[:16]
    return f"{source}:{sha1}"


def make_excerpt(body: str, max_len: int = 200) -> str:
    """Truncate body to max_len characters for safe export."""
    if not body:
        return ""
    if len(body) <= max_len:
        return body
    return body[: max_len - 1] + "..."


class BaseAdapter(ABC):
    """Abstract base for all ingest adapters."""

    @abstractmethod
    def ingest(self, params: IngestParams) -> Iterator[Article]:
        """Yield Article objects from the data source."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the canonical source identifier."""
        ...
