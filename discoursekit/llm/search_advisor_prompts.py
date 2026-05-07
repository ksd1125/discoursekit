"""Prompt templates for LLM-assisted search advice."""

from __future__ import annotations

import json


SEARCH_ADVICE_SCHEMA = {
    "core_queries": ["keyword"],
    "expansion_queries": ["related keyword"],
    "exclude_patterns": ["off-topic pattern"],
    "time_suggestion": "suggested time range",
    "method_suggestion": "suggested qualitative method",
    "reasoning": "2-3 sentence rationale",
}


SEARCH_ADVISOR_V1_TEMPLATE = """You are an academic research assistant helping a researcher
design search queries for a discourse analysis project.

Research topic: {topic}
Initial search keyword: {query}

Tasks:
1. Understand the meaning of the research topic.
2. Suggest core search queries (4-6 terms).
3. Suggest expansion queries that catch related articles the core might miss (3-5 terms).
4. Suggest exclude patterns for ads, promotional, or off-topic patterns (2-4 patterns).
5. Suggest a time range if the topic implies a specific period.
6. Suggest which qualitative method fits.
7. Explain your reasoning in 2-3 sentences.

Return JSON only:
{json_schema}
"""


SEARCH_REVISION_V1_TEMPLATE = """You are an academic research assistant.
The researcher reviewed your previous search advice and wants changes.

Previous advice:
{previous_advice_json}

Researcher feedback:
{user_feedback}

Revise the search advice to reflect the researcher's intent.
Explain what you changed and why in revision_note.

Return JSON only:
{json_schema}
"""


def build_search_advice_prompt(topic: str, query: str) -> str:
    return SEARCH_ADVISOR_V1_TEMPLATE.format(
        topic=topic or "",
        query=query or "",
        json_schema=json.dumps(SEARCH_ADVICE_SCHEMA, ensure_ascii=False, indent=2),
    )


def build_search_revision_prompt(previous_advice: dict, user_feedback: str) -> str:
    return SEARCH_REVISION_V1_TEMPLATE.format(
        previous_advice_json=json.dumps(previous_advice, ensure_ascii=False, indent=2),
        user_feedback=user_feedback or "",
        json_schema=json.dumps(
            {"advice": SEARCH_ADVICE_SCHEMA, "revision_note": "what changed and why"},
            ensure_ascii=False,
            indent=2,
        ),
    )
