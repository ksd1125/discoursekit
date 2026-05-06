"""Prompt templates for LLM-assisted keyword interpretation."""

from __future__ import annotations

import json


KEYWORD_GROUPING_SCHEMA = {
    "groups": [{"name": "group name", "keywords": ["keyword"], "description": "meaning"}],
    "topic_core": ["keyword"],
    "topic_related": ["keyword"],
    "topic_off": ["keyword"],
    "noise_candidates": [{"keyword": "keyword", "noise_type": "ad", "reason": "why"}],
    "summary": "2-3 sentence summary",
}

KEYWORD_CHANGE_SCHEMA = {
    "interpretation": "summary",
    "disappeared": [{"keyword": "keyword", "reason": "why"}],
    "emerged": [{"keyword": "keyword", "reason": "why"}],
    "shifted": [{"keyword": "keyword", "description": "how meaning shifted"}],
    "discourse_shift": "1-2 sentence shift summary",
}

KEYWORD_EXPANSION_SCHEMA = {
    "expansions": [{"keyword": "keyword", "reason": "why", "cooccurrence_count": 0}],
    "narrowings": [{"context": "context", "description": "how to narrow"}],
}


KEYWORD_ANALYSIS_V1_TEMPLATE = """You are an academic research assistant helping a researcher
interpret keyword analysis results.

Research topic: {topic}

Keywords extracted from {article_count} articles (keyword: frequency):
{keywords_formatted}

Tasks:
1. Group these keywords into 4-8 meaningful semantic groups.
2. Classify each keyword's relevance: core, related, or off_topic.
3. Identify noise candidates.
4. Summarize the overall discourse structure in 2-3 sentences.

Return JSON only:
{json_schema}
"""


KEYWORD_CHANGE_V1_TEMPLATE = """You are an academic research assistant.

Research topic: {topic}
Cutoff date: {cutoff_date}

Before cutoff top keywords:
{before_keywords}

After cutoff top keywords:
{after_keywords}

Tasks:
1. Interpret what changed.
2. List keywords that disappeared, emerged, or shifted meaning.
3. Summarize the discourse shift in 1-2 sentences.

Return JSON only:
{json_schema}
"""


def build_keyword_analysis_prompt(topic: str, keywords_with_counts: list[tuple[str, int]], article_count: int = 0) -> str:
    return KEYWORD_ANALYSIS_V1_TEMPLATE.format(
        topic=topic or "",
        article_count=article_count,
        keywords_formatted="\n".join(f"- {keyword}: {count}" for keyword, count in keywords_with_counts),
        json_schema=json.dumps(KEYWORD_GROUPING_SCHEMA, ensure_ascii=False, indent=2),
    )


def build_keyword_change_prompt(
    topic: str,
    before_kw: list[tuple[str, int]],
    after_kw: list[tuple[str, int]],
    cutoff_date: str,
) -> str:
    return KEYWORD_CHANGE_V1_TEMPLATE.format(
        topic=topic or "",
        cutoff_date=cutoff_date or "",
        before_keywords="\n".join(f"- {keyword}: {count}" for keyword, count in before_kw),
        after_keywords="\n".join(f"- {keyword}: {count}" for keyword, count in after_kw),
        json_schema=json.dumps(KEYWORD_CHANGE_SCHEMA, ensure_ascii=False, indent=2),
    )
