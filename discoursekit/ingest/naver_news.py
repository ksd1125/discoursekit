"""NAVER News Search API adapter (v0.2 skeleton only)."""

from __future__ import annotations

from typing import Iterator

from discoursekit.core.article import Article
from discoursekit.ingest.base import BaseAdapter, IngestParams


class NaverNewsAdapter(BaseAdapter):
    """NAVER News API adapter planned for v0.2."""

    @property
    def source_name(self) -> str:
        return "naver_news"

    def ingest(self, params: IngestParams) -> Iterator[Article]:
        raise NotImplementedError(
            "NaverNewsAdapter is planned for v0.2. "
            "Use BigKindsAdapter or CsvGenericAdapter for MVP."
        )
