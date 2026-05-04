"""Article filters for short, advertisement, and malformed records."""

from __future__ import annotations

import re
from dataclasses import dataclass


def filter_short_body(body: str, min_chars: int = 20) -> bool:
    """Return True when body length is at least min_chars."""
    return len(body.strip()) >= min_chars


def filter_advertisement(title: str, body: str) -> bool:
    """Return False when title or body matches advertisement patterns."""
    ad_patterns = [
        r"\[광고\]",
        r"\[AD\]",
        r"\[스폰서\]",
        r"\[Sponsored\]",
        r"^광고$",
    ]
    combined = f"{title} {body}"
    return not any(re.search(pattern, combined, re.IGNORECASE) for pattern in ad_patterns)


def filter_title_not_empty(title: str) -> bool:
    """Return True if title is non-empty."""
    return bool(title.strip())


@dataclass
class FilterResult:
    """Aggregated result of all filter passes."""

    kept_ids: list[str]
    dropped_short: list[str]
    dropped_advert: list[str]
    dropped_other: list[str]


def run_filters(
    articles: list[dict],
    min_body_chars: int = 20,
) -> FilterResult:
    """Apply title, short-body, and advertisement filters."""
    kept: list[str] = []
    dropped_short: list[str] = []
    dropped_advert: list[str] = []
    dropped_other: list[str] = []

    for article in articles:
        article_id = article["article_id"]
        title = article.get("title", "")
        body = article.get("body_internal", "")

        if not filter_title_not_empty(title):
            dropped_other.append(article_id)
            continue
        if not filter_short_body(body, min_body_chars):
            dropped_short.append(article_id)
            continue
        if not filter_advertisement(title, body):
            dropped_advert.append(article_id)
            continue
        kept.append(article_id)

    return FilterResult(
        kept_ids=kept,
        dropped_short=dropped_short,
        dropped_advert=dropped_advert,
        dropped_other=dropped_other,
    )
