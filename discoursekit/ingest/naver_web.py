"""NAVER Web Document Search API adapter."""

from __future__ import annotations

from typing import Iterator

from discoursekit.core.article import Article
from discoursekit.ingest.base import BaseAdapter, IngestParams
from discoursekit.ingest.naver_common import NAVER_WEBKR_API_URL, naver_search_ingest


class NaverWebAdapter(BaseAdapter):
    """Adapter for NAVER Web Document (webkr) Search API.

    Returns web document titles, snippets, and links. Useful for picking up
    community posts and other web content indexed by NAVER.
    """

    @property
    def source_name(self) -> str:
        return "naver_web"

    def ingest(self, params: IngestParams) -> Iterator[Article]:
        """Yield articles from NAVER Web Document Search API."""
        yield from naver_search_ingest(
            NAVER_WEBKR_API_URL, "naver_web", params,
        )
