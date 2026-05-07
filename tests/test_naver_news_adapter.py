"""NAVER News adapter tests. All API calls are mocked."""

from __future__ import annotations

import json

import pytest

from discoursekit.ingest.base import IngestParams, generate_article_id
from discoursekit.ingest.naver_common import naver_date_to_iso, strip_html_tags
from discoursekit.ingest.naver_news import NaverNewsAdapter, _extract_publisher


MOCK_NAVER_RESPONSE = {
    "lastBuildDate": "Mon, 04 May 2026 10:00:00 +0900",
    "total": 3,
    "start": 1,
    "display": 3,
    "items": [
        {
            "title": "<b>이태원동</b> 상권 회복 조짐",
            "originallink": "https://www.chosun.com/article/1",
            "link": "https://n.news.naver.com/1",
            "description": "<b>이태원동</b> 일대 음식점 매출이 전년 대비 증가했다.",
            "pubDate": "Mon, 04 May 2026 09:00:00 +0900",
        },
        {
            "title": "용산구 안전 대책 발표",
            "originallink": "https://www.hani.co.kr/article/2",
            "link": "https://n.news.naver.com/2",
            "description": "용산구가 이태원동 일대 안전 대책을 발표했다.",
            "pubDate": "Sun, 03 May 2026 15:00:00 +0900",
        },
        {
            "title": "이태원 관광 활성화",
            "originallink": "https://unknown-press.com/3",
            "link": "https://n.news.naver.com/3",
            "description": "이태원 관광특구 재지정 논의가 시작되었다.",
            "pubDate": "Sat, 02 May 2026 12:00:00 +0900",
        },
    ],
}


def test_strip_html_tags():
    assert strip_html_tags("<b>강조</b> 텍스트") == "강조 텍스트"
    assert strip_html_tags("&amp; &lt;tag&gt;") == "& <tag>"
    assert strip_html_tags("") == ""
    assert strip_html_tags(None) == ""


def test_naver_date_to_iso():
    assert naver_date_to_iso("Mon, 04 May 2026 09:00:00 +0900") == "2026-05-04"
    assert naver_date_to_iso("invalid") == "invalid"


def test_extract_publisher_known():
    assert _extract_publisher("https://www.chosun.com/article/123") == "조선일보"
    assert _extract_publisher("https://www.hani.co.kr/article/456") == "한겨레"


def test_extract_publisher_unknown():
    assert _extract_publisher("https://unknown-site.com/page") == "unknown-site.com"


def test_adapter_requires_query():
    params = IngestParams(
        project_id="test",
        source="naver_news",
        client_id="id",
        client_secret="secret",
    )
    with pytest.raises(ValueError, match="query"):
        list(NaverNewsAdapter().ingest(params))


def test_adapter_requires_api_keys():
    params = IngestParams(project_id="test", source="naver_news", query="이태원동")
    with pytest.raises(ValueError, match="client_id"):
        list(NaverNewsAdapter().ingest(params))


def test_adapter_mock_ingest(monkeypatch):
    client_kwargs = {}

    class MockResponse:
        status_code = 200

        def json(self):
            return MOCK_NAVER_RESPONSE

        def raise_for_status(self):
            pass

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, headers=None, params=None):
            return MockResponse()

    monkeypatch.setattr(
        "discoursekit.ingest.naver_news.httpx.Client",
        lambda **kwargs: client_kwargs.update(kwargs) or MockClient(),
    )
    params = IngestParams(
        project_id="test_proj",
        source="naver_news",
        query="이태원동",
        client_id="test_id",
        client_secret="test_secret",
        max_results=10,
    )
    articles = list(NaverNewsAdapter().ingest(params))

    assert len(articles) == 3
    assert all(article.source == "naver_news" for article in articles)
    assert articles[0].title == "이태원동 상권 회복 조짐"
    assert "<b>" not in articles[0].body_internal
    assert articles[0].publisher == "조선일보"
    assert articles[0].date == "2026-05-04"
    assert articles[0].raw["source_depth"] == "excerpt_only"
    assert client_kwargs["trust_env"] is False


def test_adapter_date_filter(monkeypatch):
    class MockResponse:
        status_code = 200

        def json(self):
            return MOCK_NAVER_RESPONSE

        def raise_for_status(self):
            pass

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, headers=None, params=None):
            return MockResponse()

    monkeypatch.setattr(
        "discoursekit.ingest.naver_news.httpx.Client",
        lambda **kwargs: MockClient(),
    )
    params = IngestParams(
        project_id="test_proj",
        source="naver_news",
        query="이태원동",
        date_from="2026-05-03",
        date_to="2026-05-04",
        client_id="test_id",
        client_secret="test_secret",
    )
    articles = list(NaverNewsAdapter().ingest(params))

    assert len(articles) == 2
    assert "2026-05-02" not in [article.date for article in articles]


def test_adapter_rate_limit_stops(monkeypatch):
    class MockResponse:
        status_code = 429

        def json(self):
            return {}

        def raise_for_status(self):
            raise AssertionError("raise_for_status should not be called for 429")

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, headers=None, params=None):
            return MockResponse()

    monkeypatch.setattr(
        "discoursekit.ingest.naver_news.httpx.Client",
        lambda **kwargs: MockClient(),
    )
    params = IngestParams(
        project_id="test_proj",
        source="naver_news",
        query="이태원동",
        client_id="test_id",
        client_secret="test_secret",
    )
    assert list(NaverNewsAdapter().ingest(params)) == []


def test_adapter_no_api_key_in_raw():
    params = IngestParams(
        project_id="test",
        source="naver_news",
        query="test",
        client_id="SECRET_ID",
        client_secret="SECRET_KEY",
    )
    article = NaverNewsAdapter()._item_to_article(MOCK_NAVER_RESPONSE["items"][0], params)

    assert article is not None
    raw_str = json.dumps(article.raw, ensure_ascii=False)
    assert "SECRET_ID" not in raw_str
    assert "SECRET_KEY" not in raw_str


def test_api_key_not_in_params_json():
    params = IngestParams(
        project_id="test",
        source="naver_news",
        query="이태원동",
        client_id="my_id",
        client_secret="my_secret",
    )
    serialized = json.dumps(params.to_json_dict(), ensure_ascii=False)
    assert "my_id" not in serialized
    assert "my_secret" not in serialized


def test_duplicate_article_id_stability():
    id1 = generate_article_id("naver_news", "https://example.com/article/1")
    id2 = generate_article_id("naver_news", "https://example.com/article/1")
    id3 = generate_article_id("naver_news", "https://example.com/article/2")
    assert id1 == id2
    assert id1 != id3
