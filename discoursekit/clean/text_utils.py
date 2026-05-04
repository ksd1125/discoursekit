"""Text normalization utilities for article cleaning."""

from __future__ import annotations

import re

from discoursekit.config import BODY_EXCERPT_MAX_LEN


def strip_html_tags(text: str) -> str:
    """Remove all HTML tags."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text)


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace into single spaces and trim edges."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def strip_b_tags(text: str) -> str:
    """Remove NAVER highlight <b> tags only."""
    if not text:
        return ""
    return re.sub(r"</?b>", "", text, flags=re.IGNORECASE)


def clean_body(text: str) -> str:
    """Clean body text by stripping HTML and normalizing whitespace."""
    return normalize_whitespace(strip_html_tags(text))


def make_excerpt(body: str, max_len: int = BODY_EXCERPT_MAX_LEN) -> str:
    """Generate a safe export excerpt from cleaned body text."""
    if not body:
        return ""
    if len(body) <= max_len:
        return body
    if max_len <= 3:
        return "." * max_len
    return body[: max_len - 3] + "..."


def compute_text_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity over character trigrams."""
    if not a or not b:
        return 0.0

    def trigrams(text: str) -> set[str]:
        normalized = normalize_whitespace(text).lower()
        if len(normalized) < 3:
            return {normalized}
        return {normalized[i : i + 3] for i in range(len(normalized) - 2)}

    set_a = trigrams(a)
    set_b = trigrams(b)
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 0.0
