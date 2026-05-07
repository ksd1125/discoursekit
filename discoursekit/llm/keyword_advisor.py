"""LLM-assisted keyword analysis advisor."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from typing import Any

from discoursekit.llm.keyword_advisor_prompts import (
    build_keyword_analysis_prompt,
    build_keyword_change_prompt,
)
from discoursekit.llm.providers import BaseLLMProvider, GeminiProvider, LLMRequest


@dataclass(frozen=True)
class KeywordGrouping:
    """Suggested semantic grouping for extracted keywords."""

    groups: list[dict]
    topic_core: list[str]
    topic_related: list[str]
    topic_off: list[str]
    noise_candidates: list[dict]
    summary: str


@dataclass(frozen=True)
class KeywordChangeInterpretation:
    """Suggested interpretation of before/after keyword movement."""

    interpretation: str
    disappeared: list[dict]
    emerged: list[dict]
    shifted: list[dict]
    discourse_shift: str


@dataclass(frozen=True)
class KeywordExpansion:
    """Suggested expansion or narrowing keywords."""

    expansions: list[dict]
    narrowings: list[dict]


def analyze_keywords(
    topic: str,
    keywords_with_counts: list[tuple[str, int]],
    *,
    article_count: int = 0,
    provider_instance: BaseLLMProvider | None = None,
    api_key: str | None = None,
) -> KeywordGrouping:
    """Analyze keyword groups and relevance. Falls back to deterministic grouping."""
    if provider_instance is None and not api_key:
        return _heuristic_grouping(topic, keywords_with_counts)
    prompt = build_keyword_analysis_prompt(topic, keywords_with_counts[:50], article_count)
    payload = _call_json(provider_instance or GeminiProvider(), prompt, api_key or "")
    return _grouping_from_payload(payload, topic, keywords_with_counts)


def interpret_keyword_change(
    topic: str,
    before_kw: list[tuple[str, int]],
    after_kw: list[tuple[str, int]],
    cutoff: str,
    *,
    provider_instance: BaseLLMProvider | None = None,
    api_key: str | None = None,
) -> KeywordChangeInterpretation:
    """Interpret before/after keyword changes."""
    if provider_instance is None and not api_key:
        return _heuristic_change(topic, before_kw, after_kw, cutoff)
    prompt = build_keyword_change_prompt(topic, before_kw[:20], after_kw[:20], cutoff)
    payload = _call_json(provider_instance or GeminiProvider(), prompt, api_key or "")
    return _change_from_payload(payload, topic, before_kw, after_kw, cutoff)


def suggest_expansion(
    topic: str,
    current_keywords: list[str],
    cooccurrence_data: list[tuple[str, int]],
    *,
    provider_instance: BaseLLMProvider | None = None,
    api_key: str | None = None,
) -> KeywordExpansion:
    """Suggest keyword expansion or narrowing based on co-occurrence data."""
    if provider_instance is None and not api_key:
        expansions = [
            {"keyword": keyword, "reason": "Frequently co-occurs with current topic keywords.", "cooccurrence_count": count}
            for keyword, count in cooccurrence_data[:10]
            if keyword not in current_keywords
        ]
        return KeywordExpansion(expansions=expansions, narrowings=[])
    prompt = (
        f"Research topic: {topic}\nCurrent keywords: {current_keywords}\n"
        f"Cooccurrence data: {cooccurrence_data}\nReturn JSON with expansions and narrowings."
    )
    payload = _call_json(provider_instance or GeminiProvider(), prompt, api_key or "")
    return KeywordExpansion(
        expansions=_dict_list(payload.get("expansions")),
        narrowings=_dict_list(payload.get("narrowings")),
    )


def revise_keyword_analysis(
    prev_result: KeywordGrouping,
    user_feedback: str,
    *,
    provider_instance: BaseLLMProvider | None = None,
    api_key: str | None = None,
) -> KeywordGrouping:
    """Revise keyword grouping based on researcher feedback."""
    if provider_instance is None and not api_key:
        return KeywordGrouping(
            groups=prev_result.groups,
            topic_core=prev_result.topic_core,
            topic_related=prev_result.topic_related,
            topic_off=list(dict.fromkeys(prev_result.topic_off + ([user_feedback] if user_feedback else []))),
            noise_candidates=prev_result.noise_candidates,
            summary=f"{prev_result.summary} Researcher feedback: {user_feedback}",
        )
    prompt = (
        "Revise this keyword analysis based on researcher feedback.\n"
        f"Previous: {json.dumps(asdict(prev_result), ensure_ascii=False)}\n"
        f"Feedback: {user_feedback}\nReturn JSON only."
    )
    payload = _call_json(provider_instance or GeminiProvider(), prompt, api_key or "")
    return _grouping_from_payload(payload, "", [])


def _call_json(provider: BaseLLMProvider, prompt: str, api_key: str) -> dict:
    response = asyncio.run(
        provider.call(
            LLMRequest(prompt=prompt, article_text="", temperature=0.0, max_tokens=1600),
            api_key=api_key,
        )
    )
    if not response.success:
        raise ValueError(response.error or "LLM keyword advice call failed")
    text = response.labels_json or ""
    if not text and response.raw_response:
        text = json.dumps(response.raw_response, ensure_ascii=False)
    return _extract_json(text)


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    raise ValueError("Keyword advice response did not contain JSON")


def _grouping_from_payload(payload: dict[str, Any], topic: str, keywords: list[tuple[str, int]]) -> KeywordGrouping:
    fallback = _heuristic_grouping(topic, keywords)
    return KeywordGrouping(
        groups=_dict_list(payload.get("groups")) or fallback.groups,
        topic_core=_strings(payload.get("topic_core")) or fallback.topic_core,
        topic_related=_strings(payload.get("topic_related")) or fallback.topic_related,
        topic_off=_strings(payload.get("topic_off")) or fallback.topic_off,
        noise_candidates=_dict_list(payload.get("noise_candidates")) or fallback.noise_candidates,
        summary=str(payload.get("summary") or fallback.summary),
    )


def _change_from_payload(
    payload: dict[str, Any],
    topic: str,
    before_kw: list[tuple[str, int]],
    after_kw: list[tuple[str, int]],
    cutoff: str,
) -> KeywordChangeInterpretation:
    fallback = _heuristic_change(topic, before_kw, after_kw, cutoff)
    return KeywordChangeInterpretation(
        interpretation=str(payload.get("interpretation") or fallback.interpretation),
        disappeared=_dict_list(payload.get("disappeared")) or fallback.disappeared,
        emerged=_dict_list(payload.get("emerged")) or fallback.emerged,
        shifted=_dict_list(payload.get("shifted")) or fallback.shifted,
        discourse_shift=str(payload.get("discourse_shift") or fallback.discourse_shift),
    )


def _heuristic_grouping(topic: str, keywords: list[tuple[str, int]]) -> KeywordGrouping:
    top = keywords[:50]
    groups = []
    for idx, chunk in enumerate(_chunks(top, 8), start=1):
        groups.append(
            {
                "name": f"Keyword group {idx}",
                "keywords": [keyword for keyword, _ in chunk],
                "description": "Grouped by rank proximity; researcher should rename after review.",
            }
        )
    core = [keyword for keyword, _ in top[: max(1, min(10, len(top)))]]
    related = [keyword for keyword, _ in top[len(core) : len(core) + 10]]
    off = [keyword for keyword, _ in top[-5:]] if len(top) > 15 else []
    noise = [
        {"keyword": keyword, "noise_type": "generic", "reason": "Low-ranked or broad keyword; review before using."}
        for keyword in off
    ]
    return KeywordGrouping(
        groups=groups,
        topic_core=core,
        topic_related=related,
        topic_off=off,
        noise_candidates=noise,
        summary=f"{topic or 'The topic'} keyword structure is summarized as ranked semantic groups for researcher review.",
    )


def _heuristic_change(topic: str, before_kw: list[tuple[str, int]], after_kw: list[tuple[str, int]], cutoff: str) -> KeywordChangeInterpretation:
    before = dict(before_kw)
    after = dict(after_kw)
    disappeared = [
        {"keyword": keyword, "reason": "Present before cutoff but absent after cutoff."}
        for keyword in before
        if keyword not in after
    ][:10]
    emerged = [
        {"keyword": keyword, "reason": "Absent before cutoff but present after cutoff."}
        for keyword in after
        if keyword not in before
    ][:10]
    shifted = [
        {"keyword": keyword, "description": f"Frequency changed from {before[keyword]} to {after[keyword]}."}
        for keyword in set(before) & set(after)
        if before[keyword] != after[keyword]
    ][:10]
    return KeywordChangeInterpretation(
        interpretation=f"Keyword composition around {cutoff} changed in emergence and disappearance patterns.",
        disappeared=disappeared,
        emerged=emerged,
        shifted=shifted,
        discourse_shift=f"{topic or 'The discourse'} should be interpreted by checking emerged and disappeared terms.",
    )


def _chunks(items: list[tuple[str, int]], size: int):
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dict_list(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]
