"""Article deduplication - primary exact and fallback fuzzy passes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

from discoursekit.clean.text_utils import compute_text_similarity


@dataclass
class DedupResult:
    """Result of a deduplication pass."""

    kept_ids: list[str]
    primary_dup_ids: list[str]
    fallback_dup_ids: list[str]


def dedup_key(title: str, date: str, publisher: str) -> str:
    """Generate a deterministic exact-dedup key."""
    raw = f"{title.strip().lower()}|{date}|{publisher.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_dedup(
    articles: Sequence[dict],
    similarity_threshold: float = 0.85,
) -> DedupResult:
    """Run exact then fuzzy deduplication over article dictionaries."""
    seen_keys: dict[str, str] = {}
    primary_dups: list[str] = []
    surviving: list[dict] = []

    for article in articles:
        key = dedup_key(article["title"], article["date"], article.get("publisher", ""))
        if key in seen_keys:
            primary_dups.append(article["article_id"])
        else:
            seen_keys[key] = article["article_id"]
            surviving.append(article)

    fallback_dups: list[str] = []
    by_date: dict[str, list[dict]] = {}
    for article in surviving:
        by_date.setdefault(article["date"], []).append(article)

    final_kept: list[str] = []
    for group in by_date.values():
        kept_in_group: list[dict] = []
        for article in group:
            is_duplicate = False
            for kept in kept_in_group:
                similarity = compute_text_similarity(article["title"], kept["title"])
                if similarity >= similarity_threshold:
                    fallback_dups.append(article["article_id"])
                    is_duplicate = True
                    break
            if not is_duplicate:
                kept_in_group.append(article)
                final_kept.append(article["article_id"])

    return DedupResult(
        kept_ids=final_kept,
        primary_dup_ids=primary_dups,
        fallback_dup_ids=fallback_dups,
    )
