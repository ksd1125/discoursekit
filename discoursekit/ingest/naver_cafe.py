"""NAVER Cafe Search API adapter."""

from __future__ import annotations

from typing import Iterator

from discoursekit.core.article import Article
from discoursekit.ingest.base import BaseAdapter, IngestParams
from discoursekit.ingest.naver_common import NAVER_CAFE_API_URL, naver_search_ingest


class NaverCafeAdapter(BaseAdapter):
    """Adapter for NAVER Cafe (cafearticle) Search API.

    Returns public cafe article titles, snippets, cafe names, and links.
    """

    @property
    def source_name(self) -> str:
        return "naver_cafe"

    def ingest(self, params: IngestParams) -> Iterator[Article]:
        """Yield articles from NAVER Cafe Search API."""
        yield from naver_search_ingest(
            NAVER_CAFE_API_URL, "naver_cafe", params,
        )
