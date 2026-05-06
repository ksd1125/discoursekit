"""NAVER Search API shared helpers."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Iterator

import httpx

from discoursekit.config import BODY_EXCERPT_MAX_LEN
from discoursekit.core.article import Article
from discoursekit.ingest.base import IngestParams, generate_article_id, make_excerpt


NAVER_NEWS_API_URL = "https://openapi.naver.com/v1/search/news.json"
NAVER_BLOG_API_URL = "https://openapi.naver.com/v1/search/blog.json"
NAVER_CAFE_API_URL = "https://openapi.naver.com/v1/search/cafearticle.json"
NAVER_WEBKR_API_URL = "https://openapi.naver.com/v1/search/webkr.json"


def strip_html_tags(text: str | None) -> str:
    """Remove simple HTML tags and decode HTML entities."""
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", "", str(text))
    return unescape(cleaned).strip()


def naver_date_to_iso(date_str: str | None) -> str:
    """Convert NAVER's date string to YYYY-MM-DD.

    Handles both RFC 2822 format (news: "Mon, 04 May 2026 09:00:00 +0900")
    and compact YYYYMMDD format (blog/cafe: "20260504").
    """
    if not date_str:
        return ""
    cleaned = str(date_str).strip()
    # Compact YYYYMMDD format used by blog/cafe postdate.
    if re.fullmatch(r"\d{8}", cleaned):
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"
    try:
        return parsedate_to_datetime(cleaned).strftime("%Y-%m-%d")
    except Exception:
        return cleaned


def naver_search_ingest(
    api_url: str,
    source_name: str,
    params: IngestParams,
    *,
    item_to_article: "callable | None" = None,
) -> Iterator[Article]:
    """Generic paginated NAVER Search API ingestion.

    Works for blog, cafearticle, and webkr endpoints which share the same
    request/response format (query, display, start, sort → items[]).
    """
    if not params.query:
        raise ValueError(f"{source_name} requires params.query")
    if not params.client_id or not params.client_secret:
        raise ValueError(f"{source_name} requires params.client_id and params.client_secret.")
    if params.sort not in {"sim", "date"}:
        raise ValueError("NAVER sort must be 'sim' or 'date'")

    converter = item_to_article or _default_item_to_article

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
                api_url,
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
                article = converter(item, params, source_name)
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


def _default_item_to_article(
    item: dict, params: IngestParams, source_name: str,
) -> Article | None:
    """Convert a generic NAVER Search API item to an Article."""
    try:
        title = strip_html_tags(item.get("title", ""))
        description = strip_html_tags(item.get("description", ""))
        pub_date = naver_date_to_iso(item.get("postdate") or item.get("pubDate") or "")
        link = item.get("link") or ""
        body = description or title
        unique_key = link or f"{title}|{pub_date}"
        blogger_name = item.get("bloggername") or item.get("cafename") or ""
        raw = dict(item)
        raw["source_depth"] = "excerpt_only"

        return Article(
            article_id=generate_article_id(source_name, unique_key),
            source=source_name,
            date=pub_date,
            publisher=blogger_name,
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
