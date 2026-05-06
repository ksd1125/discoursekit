"""Search advisor tests."""

import json

from discoursekit.llm.providers import BaseLLMProvider, LLMRequest, LLMResponse
from discoursekit.llm.search_advisor import generate_search_advice, revise_search_advice


class MockSearchProvider(BaseLLMProvider):
    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-search"

    async def call(self, request: LLMRequest, api_key: str) -> LLMResponse:
        return LLMResponse(
            labels_json=json.dumps(
                {
                    "core_queries": ["이태원동", "이태원 안전"],
                    "expansion_queries": ["용산구 이태원"],
                    "exclude_patterns": ["맛집"],
                    "time_suggestion": "2022-2023",
                    "method_suggestion": "frame_analysis",
                    "reasoning": "Search should capture safety discourse.",
                },
                ensure_ascii=False,
            )
        )


def test_generate_basic():
    advice = generate_search_advice("이태원동 장소 이미지 변화", "이태원동")

    assert advice.core_queries
    assert advice.exclude_patterns


def test_generate_with_provider():
    advice = generate_search_advice(
        "이태원동 장소 이미지 변화",
        "이태원동",
        provider_instance=MockSearchProvider(),
        api_key="k",
    )

    assert "이태원 안전" in advice.core_queries
    assert advice.method_suggestion == "frame_analysis"


def test_revise_increments_and_reflects():
    advice = generate_search_advice("관광 제외", "명동")
    revised = revise_search_advice(advice, "관광 제외", revision_round=2)

    assert revised.revision_round == 2
    assert "관광 제외" in revised.revision_note
    assert "관광 제외" in revised.advice.exclude_patterns
