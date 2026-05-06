"""Insight card payload tests."""

from dataclasses import dataclass

import pytest

from discoursekit.analyze.insight_cards import (
    InsightCardPayload,
    build_insight_card_payload,
    validate_headline,
)


@dataclass(frozen=True)
class DummyKeywordResult:
    keywords: list[tuple[str, int]]
    total_tokens: int = 10
    unique_tokens: int = 2
    source_field: str = "meta_keywords"
    tokenizer: str = "split"
    stopwords_applied: int = 0


def _config(**overrides):
    data = {
        "project_id": "test",
        "query": "Itaewon",
        "source_depth": "full_body",
        "active_count": 100,
        "date_min": "2022-10-01",
        "date_max": "2022-12-01",
        "cutoff_date": None,
    }
    data.update(overrides)
    return data


def test_headline_no_causal_language():
    assert validate_headline("Article volume is higher after the cutoff")
    assert not validate_headline("The event proves public opinion changed")


def test_method_note_has_source_depth():
    payload = build_insight_card_payload(
        "keywords",
        DummyKeywordResult(keywords=[("recovery", 3)]),
        _config(source_depth="full_body"),
    )

    assert isinstance(payload, InsightCardPayload)
    assert "자료 깊이: 전문 포함" in payload.method_note


def test_caveat_excerpt_only():
    payload = build_insight_card_payload(
        "keywords",
        DummyKeywordResult(keywords=[("recovery", 3)]),
        _config(source_depth="excerpt_only"),
    )

    assert "제목과 요약문" in payload.caveat


def test_caveat_small_sample():
    payload = build_insight_card_payload(
        "keywords",
        DummyKeywordResult(keywords=[("recovery", 3)]),
        _config(active_count=20),
    )

    assert "50건 미만" in payload.caveat


def test_forbidden_headline_raises():
    with pytest.raises(ValueError):
        build_insight_card_payload(
            "sampling",
            type(
                "BadSampling",
                (),
                {
                    "sample_size": 1,
                    "population_size": 1,
                    "strategy": "because",
                    "articles": [],
                },
            )(),
            _config(),
        )


def test_network_card_payload():
    result = type(
        "NetworkResult",
        (),
        {
            "num_nodes": 5,
            "num_edges": 4,
            "density": 0.4,
            "communities": [{"id": 0, "keywords": ["safety", "policy"]}],
            "top_central": [{"keyword": "safety"}, {"keyword": "policy"}],
        },
    )()

    payload = build_insight_card_payload("network", result, _config())

    assert payload.card_id == "network"
    assert "의미망" in payload.headline
    assert "동시출현" in payload.method_note
    assert "인과관계" in payload.caveat
