"""NAVER Blog Search API adapter."""

from __future__ import annotations

from typing import Iterator

from discoursekit.core.article import Article
from discoursekit.ingest.base import BaseAdapter, IngestParams
from discoursekit.ingest.naver_common import NAVER_BLOG_API_URL, naver_search_ingest


class NaverBlogAdapter(BaseAdapter):
    """Adapter for NAVER Blog Search API.

    Returns blog post titles, snippets, blogger names, and links.
    Full blog post bodies are not available through the Search API.
    """

    @property
    def source_name(self) -> str:
        return "naver_blog"

    def ingest(self, params: IngestParams) -> Iterator[Article]:
        """Yield articles from NAVER Blog Search API."""
        yield from naver_search_ingest(
            NAVER_BLOG_API_URL, "naver_blog", params,
        )
