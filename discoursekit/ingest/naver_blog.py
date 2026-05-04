"""NAVER Blog Search API adapter (v0.2 skeleton only)."""

from __future__ import annotations

from typing import Iterator

from discoursekit.core.article import Article
from discoursekit.ingest.base import BaseAdapter, IngestParams


class NaverBlogAdapter(BaseAdapter):
    """NAVER Blog API adapter planned for v0.2."""

    @property
    def source_name(self) -> str:
        return "naver_blog"

    def ingest(self, params: IngestParams) -> Iterator[Article]:
        raise NotImplementedError(
            "NaverBlogAdapter is planned for v0.2. "
            "Use BigKindsAdapter or CsvGenericAdapter for MVP."
        )
