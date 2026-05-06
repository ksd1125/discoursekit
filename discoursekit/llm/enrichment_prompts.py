"""Prompt templates and version metadata for corpus enrichment."""

from __future__ import annotations

import json

from discoursekit.config import sha256_of_text


DEFAULT_SEMANTIC_TAGS = [
    "safety",
    "economy",
    "tourism",
    "policy",
    "responsibility",
    "memorial",
    "local_place",
    "recovery",
    "culture",
    "media_criticism",
    "resident",
    "other",
]


JSON_SCHEMA_EXAMPLE = {
    "is_relevant": True,
    "relevance_score": 0.86,
    "relevance_reason": "The text directly discusses the research topic.",
    "quality_flags": [],
    "semantic_tags": ["safety", "local_place"],
    "noise_type": None,
    "topic_relevance": "core",
    "canonical_places": ["Itaewon-dong"],
    "canonical_events": [],
    "canonical_actors": [],
    "evidence_sentences": [],
    "suggested_action": "keep",
    "rationale": "Include this text because it is directly relevant to the corpus.",
}


ENRICH_V1_TEMPLATE = """You are an academic text-data cleaning assistant.

Your role is to suggest corpus enrichment fields only. You are not the analyst.
Do not write conclusions, claims about public opinion, or interpretations that go
beyond the provided text. Use only the article/blog text shown below.

Research topic:
{research_topic}

Search query:
{query}

Date range:
{date_from} ~ {date_to}

Enabled options:
{options}

Allowed semantic tags:
{semantic_tag_list}

Decision rules:
- is_relevant: true only if the text is directly useful for the research topic.
- relevance_score: float from 0.0 to 1.0.
- quality_flags: use known flags such as ad_suspected, too_short,
  duplicate_suspected, irrelevant_noise, low_quality, encoding_issue.
- semantic_tags: choose only from the allowed tag list.
- noise_type: null if clean article. Use "ad" for commercial/promotional
  content, "duplicate_pattern" for repeated wire-service patterns,
  "off_topic" for keyword mentions that are not about the topic, and
  "generic" for broad material that is too vague to help.
- topic_relevance: "core" if directly about the research topic, "related" if
  tangentially related, and "off_topic" if not related.
- canonical_* fields: standardize places, events, and actors mentioned in the text.
- evidence_sentences: copy exact source sentences only. Do not invent evidence.
- suggested_action: one of keep, review, drop_candidate.

Return JSON only. Do not wrap it in markdown.

JSON schema example:
{json_schema_example}

Article:
Title: {title}
Body: {body}
"""


PROMPT_VERSIONS = {
    "enrich_v1": {
        "template": ENRICH_V1_TEMPLATE,
        "schema_version": "llm_enrichment_v1",
    }
}


def build_enrichment_prompt(config, title: str, body: str) -> str:
    """Build the v1 enrichment prompt for one article."""
    semantic_tags = config.semantic_tag_list or DEFAULT_SEMANTIC_TAGS
    return ENRICH_V1_TEMPLATE.format(
        research_topic=config.research_topic or "",
        query=config.query or "",
        date_from=config.date_from or "",
        date_to=config.date_to or "",
        options=", ".join(config.options),
        semantic_tag_list=", ".join(semantic_tags),
        json_schema_example=json.dumps(JSON_SCHEMA_EXAMPLE, ensure_ascii=False, indent=2),
        title=title or "",
        body=body or "",
    )


def get_prompt_version(version_id: str) -> dict:
    """Return prompt version metadata, including computed SHA-256."""
    if version_id not in PROMPT_VERSIONS:
        raise ValueError(f"Unknown enrichment prompt version: {version_id}")
    version = dict(PROMPT_VERSIONS[version_id])
    version["version_id"] = version_id
    version["sha256"] = sha256_of_text(version["template"])
    return version
