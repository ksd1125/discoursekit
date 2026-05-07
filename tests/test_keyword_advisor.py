"""Keyword advisor tests."""

import json

from discoursekit.llm.keyword_advisor import (
    analyze_keywords,
    interpret_keyword_change,
    revise_keyword_analysis,
    suggest_expansion,
)
from discoursekit.llm.providers import BaseLLMProvider, LLMRequest, LLMResponse


class MockKeywordProvider(BaseLLMProvider):
    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-keyword"

    async def call(self, request: LLMRequest, api_key: str) -> LLMResponse:
        return LLMResponse(
            labels_json=json.dumps(
                {
                    "groups": [{"name": "안전", "keywords": ["안전"], "description": "안전 담론"}],
                    "topic_core": ["안전"],
                    "topic_related": ["정책"],
                    "topic_off": ["맛집"],
                    "noise_candidates": [{"keyword": "맛집", "noise_type": "ad", "reason": "상업 노이즈"}],
                    "summary": "안전과 정책 중심입니다.",
                    "interpretation": "기준일 이후 안전 담론이 증가했습니다.",
                    "emerged": [{"keyword": "안전", "reason": "새로 등장"}],
                    "disappeared": [],
                    "shifted": [],
                    "discourse_shift": "안전 중심으로 이동했습니다.",
                },
                ensure_ascii=False,
            )
        )


def test_grouping_basic():
    result = analyze_keywords("이태원", [("안전", 10), ("정책", 5), ("맛집", 2)])

    assert result.groups
    assert result.topic_core


def test_grouping_with_provider():
    result = analyze_keywords(
        "이태원",
        [("안전", 10), ("정책", 5)],
        provider_instance=MockKeywordProvider(),
        api_key="k",
    )

    assert result.groups[0]["name"] == "안전"
    assert result.noise_candidates[0]["noise_type"] == "ad"


def test_change_interpretation():
    result = interpret_keyword_change("이태원", [("관광", 5)], [("안전", 10)], "2022-10-29")

    assert result.interpretation
    assert result.emerged


def test_expansion_suggest():
    result = suggest_expansion("이태원", ["안전"], [("정책", 7), ("관광", 3)])

    assert result.expansions[0]["keyword"] == "정책"


def test_revise_keywords():
    result = analyze_keywords("이태원", [("안전", 10)])
    revised = revise_keyword_analysis(result, "관광 제외")

    assert "관광 제외" in revised.topic_off
