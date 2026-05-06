"""LLM-assisted search query advisor."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from typing import Any

from discoursekit.llm.providers import BaseLLMProvider, GeminiProvider, LLMRequest
from discoursekit.llm.search_advisor_prompts import build_search_advice_prompt, build_search_revision_prompt


@dataclass(frozen=True)
class SearchAdvice:
    """Search advice generated from a research topic."""

    core_queries: list[str]
    expansion_queries: list[str]
    exclude_patterns: list[str]
    time_suggestion: str
    method_suggestion: str
    reasoning: str


@dataclass(frozen=True)
class SearchAdviceRevision:
    """Revised search advice after researcher feedback."""

    advice: SearchAdvice
    revision_note: str
    revision_round: int


def generate_search_advice(
    topic: str,
    initial_query: str,
    *,
    provider_instance: BaseLLMProvider | None = None,
    api_key: str | None = None,
) -> SearchAdvice:
    """Generate search advice. Falls back to deterministic advice without an API key."""
    if provider_instance is None and not api_key:
        return _heuristic_advice(topic, initial_query)

    prompt = build_search_advice_prompt(topic, initial_query)
    payload = _call_json(provider_instance or GeminiProvider(), prompt, api_key or "")
    return _advice_from_payload(payload, topic, initial_query)


def revise_search_advice(
    prev_advice: SearchAdvice,
    user_feedback: str,
    *,
    revision_round: int = 1,
    provider_instance: BaseLLMProvider | None = None,
    api_key: str | None = None,
) -> SearchAdviceRevision:
    """Revise search advice based on researcher feedback."""
    if provider_instance is None and not api_key:
        advice = _heuristic_revision(prev_advice, user_feedback)
        return SearchAdviceRevision(
            advice=advice,
            revision_note=f"Reflected researcher feedback: {user_feedback}",
            revision_round=revision_round,
        )

    prompt = build_search_revision_prompt(asdict(prev_advice), user_feedback)
    payload = _call_json(provider_instance or GeminiProvider(), prompt, api_key or "")
    advice_payload = payload.get("advice", payload)
    return SearchAdviceRevision(
        advice=_advice_from_payload(advice_payload, "", ""),
        revision_note=str(payload.get("revision_note") or "Revised based on researcher feedback."),
        revision_round=revision_round,
    )


def _call_json(provider: BaseLLMProvider, prompt: str, api_key: str) -> dict:
    response = asyncio.run(
        provider.call(
            LLMRequest(prompt=prompt, article_text="", temperature=0.0, max_tokens=1200),
            api_key=api_key,
        )
    )
    if not response.success:
        raise ValueError(response.error or "LLM search advice call failed")
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
    raise ValueError("Search advice response did not contain JSON")


def _advice_from_payload(payload: dict[str, Any], topic: str, query: str) -> SearchAdvice:
    fallback = _heuristic_advice(topic, query)
    return SearchAdvice(
        core_queries=_strings(payload.get("core_queries")) or fallback.core_queries,
        expansion_queries=_strings(payload.get("expansion_queries")) or fallback.expansion_queries,
        exclude_patterns=_strings(payload.get("exclude_patterns")) or fallback.exclude_patterns,
        time_suggestion=str(payload.get("time_suggestion") or fallback.time_suggestion),
        method_suggestion=str(payload.get("method_suggestion") or fallback.method_suggestion),
        reasoning=str(payload.get("reasoning") or fallback.reasoning),
    )


def _heuristic_advice(topic: str, query: str) -> SearchAdvice:
    base = query.strip() or topic.strip() or "research topic"
    topic_text = topic.strip()
    core = list(dict.fromkeys([base, f"{base} 이슈", f"{base} 보도", f"{base} 담론"]))
    expansion = [f"{base} 지역", f"{base} 정책", f"{base} 변화"]
    exclude = [f"{base} 맛집", f"{base} 부동산", f"{base} 광고"]
    method = "place_discourse" if any(word in topic_text for word in ["장소", "지역", "place"]) else "frame_analysis"
    return SearchAdvice(
        core_queries=core,
        expansion_queries=expansion,
        exclude_patterns=exclude,
        time_suggestion="Use the research period entered by the researcher; expand around major events if needed.",
        method_suggestion=method,
        reasoning="The advice keeps the initial keyword as the core and adds issue, policy, and discourse variants for corpus coverage.",
    )


def _heuristic_revision(prev: SearchAdvice, feedback: str) -> SearchAdvice:
    lowered = feedback.lower()
    remove_terms = []
    for query in prev.core_queries + prev.expansion_queries:
        if query.lower() in lowered and any(marker in lowered for marker in ["exclude", "remove", "제외", "빼"]):
            remove_terms.append(query)
    core = [query for query in prev.core_queries if query not in remove_terms]
    expansion = [query for query in prev.expansion_queries if query not in remove_terms]
    exclude = list(prev.exclude_patterns)
    if feedback.strip() and feedback.strip() not in exclude:
        exclude.append(feedback.strip())
    return SearchAdvice(
        core_queries=core or prev.core_queries,
        expansion_queries=expansion or prev.expansion_queries,
        exclude_patterns=exclude,
        time_suggestion=prev.time_suggestion,
        method_suggestion=prev.method_suggestion,
        reasoning=f"{prev.reasoning} Researcher feedback was incorporated.",
    )


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
