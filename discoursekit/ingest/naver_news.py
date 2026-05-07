"""NAVER News Search API adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator
from urllib.parse import urlparse

import httpx

from discoursekit.config import BODY_EXCERPT_MAX_LEN
from discoursekit.core.article import Article
from discoursekit.ingest.base import BaseAdapter, IngestParams, generate_article_id, make_excerpt
from discoursekit.ingest.naver_common import (
    NAVER_NEWS_API_URL,
    naver_date_to_iso,
    strip_html_tags,
)


class NaverNewsAdapter(BaseAdapter):
    """Adapter for NAVER News Search API.

    NAVER Search API provides titles, snippets, and links rather than full article
    bodies. DiscourseKit stores the cleaned description as body_internal and marks
    this limitation in raw metadata.
    """

    @property
    def source_name(self) -> str:
        return "naver_news"

    def ingest(self, params: IngestParams) -> Iterator[Article]:
        """Yield articles from NAVER News Search API."""
        if not params.query:
            raise ValueError("NaverNewsAdapter requires params.query")
        if not params.client_id or not params.client_secret:
            raise ValueError(
                "NaverNewsAdapter requires params.client_id and params.client_secret."
            )
        if params.sort not in {"sim", "date"}:
            raise ValueError("NAVER sort must be 'sim' or 'date'")

        headers = {
            "X-Naver-Client-Id": params.client_id,
            "X-Naver-Client-Secret": params.client_secret,
        }
        display = max(1, min(int(params.display or 100), 100))
        max_results = max(0, int(params.max_results or 1000))
        start = 1
        collected = 0

        with httpx.Client(timeout=30.0, trust_env=False) as client:
            while collected < max_results and start <= 1000:
                response = client.get(
                    NAVER_NEWS_API_URL,
                    headers=headers,
                    params={
                        "query": params.query,
                        "display": display,
                        "start": start,
                        "sort": params.sort,
                    },
                )
                if response.status_code == 429:
                    break
                response.raise_for_status()

                payload = response.json()
                items = payload.get("items", [])
                if not items:
                    break
                total = int(payload.get("total") or 0)

                for item in items:
                    if collected >= max_results:
                        break
                    article = self._item_to_article(item, params)
                    if article is None:
                        continue
                    if params.date_from and article.date < params.date_from:
                        continue
                    if params.date_to and article.date > params.date_to:
                        continue
                    collected += 1
                    yield article

                start += display
                if total and start > total:
                    break

    def _item_to_article(self, item: dict, params: IngestParams) -> Article | None:
        """Convert one NAVER API item to an Article."""
        try:
            title = strip_html_tags(item.get("title", ""))
            description = strip_html_tags(item.get("description", ""))
            pub_date = naver_date_to_iso(item.get("pubDate", ""))
            link = item.get("originallink") or item.get("link") or ""
            body = description or title
            unique_key = link or f"{title}|{pub_date}"
            raw = dict(item)
            raw["source_depth"] = "excerpt_only"
            raw["body_note"] = "NAVER Search API returns description/snippet, not full body."

            return Article(
                article_id=generate_article_id("naver_news", unique_key),
                source="naver_news",
                date=pub_date,
                publisher=_extract_publisher(link),
                title=title,
                body_internal=body,
                body_excerpt=make_excerpt(body, BODY_EXCERPT_MAX_LEN),
                keywords=[params.query] if params.query else [],
                url=link,
                raw=raw,
                cleaned_at=datetime.now(timezone.utc).isoformat(),
                project_id=params.project_id,
            )
        except Exception:
            return None


def _extract_publisher(url: str) -> str:
    """Extract a readable publisher from a URL domain."""
    if not url:
        return ""
    try:
        domain = urlparse(url).netloc.lower()
    except Exception:
        return ""
    publisher_map = {
        "www.chosun.com": "조선일보",
        "www.donga.com": "동아일보",
        "www.joongang.co.kr": "중앙일보",
        "www.hani.co.kr": "한겨레",
        "www.khan.co.kr": "경향신문",
        "www.hankookilbo.com": "한국일보",
        "www.mk.co.kr": "매일경제",
        "www.hankyung.com": "한국경제",
        "news.sbs.co.kr": "SBS",
        "news.kbs.co.kr": "KBS",
        "imnews.imbc.com": "MBC",
        "www.yna.co.kr": "연합뉴스",
        "newsis.com": "뉴시스",
        "www.newsis.com": "뉴시스",
        "www.ytn.co.kr": "YTN",
    }
    return publisher_map.get(domain, domain)
