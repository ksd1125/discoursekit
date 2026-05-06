"""Tests for NAVER Blog, Cafe, and Web adapters. All API calls are mocked."""

from __future__ import annotations

import pytest

from discoursekit.ingest.base import IngestParams
from discoursekit.ingest.naver_blog import NaverBlogAdapter
from discoursekit.ingest.naver_cafe import NaverCafeAdapter
from discoursekit.ingest.naver_web import NaverWebAdapter


MOCK_BLOG_RESPONSE = {
    "lastBuildDate": "Tue, 06 May 2026 10:00:00 +0900",
    "total": 2,
    "start": 1,
    "display": 2,
    "items": [
        {
            "title": "<b>명동</b> 맛집 후기",
            "link": "https://blog.naver.com/user1/post1",
            "description": "<b>명동</b>역 근처 돈카츠 맛집을 다녀왔습니다.",
            "bloggername": "맛집탐방러",
            "bloggerlink": "https://blog.naver.com/user1",
            "postdate": "20260505",
        },
        {
            "title": "성수동 카페 투어",
            "link": "https://blog.naver.com/user2/post2",
            "description": "성수동 새로 오픈한 카페 3곳 추천합니다.",
            "bloggername": "카페러버",
            "bloggerlink": "https://blog.naver.com/user2",
            "postdate": "20260504",
        },
    ],
}

MOCK_CAFE_RESPONSE = {
    "lastBuildDate": "Tue, 06 May 2026 10:00:00 +0900",
    "total": 2,
    "start": 1,
    "display": 2,
    "items": [
        {
            "title": "<b>이태원</b> 주민 모임 공지",
            "link": "https://cafe.naver.com/localcafe/12345",
            "description": "<b>이태원</b>동 주민 정기 모임 일정 안내입니다.",
            "cafename": "이태원주민카페",
            "cafeurl": "https://cafe.naver.com/localcafe",
        },
        {
            "title": "명동 웨이팅 정보 공유",
            "link": "https://cafe.naver.com/foodcafe/67890",
            "description": "명동 인기 맛집 웨이팅 시간 정리했습니다.",
            "cafename": "맛집정보카페",
            "cafeurl": "https://cafe.naver.com/foodcafe",
        },
    ],
}

MOCK_WEB_RESPONSE = {
    "lastBuildDate": "Tue, 06 May 2026 10:00:00 +0900",
    "total": 1,
    "start": 1,
    "display": 1,
    "items": [
        {
            "title": "성수동 <b>상권</b> 분석 리포트",
            "link": "https://example.com/report/seongsu",
            "description": "성수동 상권 변화를 데이터로 분석한 리포트입니다.",
        },
    ],
}


def _make_mock_client(mock_response):
    """Create a mock httpx.Client class that returns mock_response."""

    class MockResponse:
        status_code = 200

        def json(self):
            return mock_response

        def raise_for_status(self):
            pass

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, headers=None, params=None):
            return MockResponse()

    return MockClient


def _base_params(**overrides):
    defaults = {
        "project_id": "test_proj",
        "source": "naver_blog",
        "query": "명동",
        "client_id": "test_id",
        "client_secret": "test_secret",
        "max_results": 100,
    }
    defaults.update(overrides)
    return IngestParams(**defaults)


# ── Blog adapter ──


class TestNaverBlogAdapter:
    def test_source_name(self):
        assert NaverBlogAdapter().source_name == "naver_blog"

    def test_ingest_returns_articles(self, monkeypatch):
        monkeypatch.setattr(
            "discoursekit.ingest.naver_common.httpx.Client",
            lambda **kw: _make_mock_client(MOCK_BLOG_RESPONSE)(),
        )
        articles = list(NaverBlogAdapter().ingest(_base_params(source="naver_blog")))

        assert len(articles) == 2
        assert all(a.source == "naver_blog" for a in articles)
        assert articles[0].title == "명동 맛집 후기"
        assert "<b>" not in articles[0].body_internal
        assert articles[0].publisher == "맛집탐방러"
        assert articles[0].raw["source_depth"] == "excerpt_only"

    def test_requires_query(self):
        params = _base_params(query=None, source="naver_blog")
        with pytest.raises(ValueError, match="query"):
            list(NaverBlogAdapter().ingest(params))

    def test_requires_api_keys(self):
        params = _base_params(client_id=None, client_secret=None, source="naver_blog")
        with pytest.raises(ValueError, match="client_id"):
            list(NaverBlogAdapter().ingest(params))

    def test_date_filter(self, monkeypatch):
        monkeypatch.setattr(
            "discoursekit.ingest.naver_common.httpx.Client",
            lambda **kw: _make_mock_client(MOCK_BLOG_RESPONSE)(),
        )
        params = _base_params(
            source="naver_blog", date_from="2026-05-05", date_to="2026-05-05",
        )
        articles = list(NaverBlogAdapter().ingest(params))
        assert len(articles) == 1
        assert articles[0].date == "2026-05-05"

    def test_rate_limit_stops(self, monkeypatch):
        class RateLimitResponse:
            status_code = 429

            def json(self):
                return {}

            def raise_for_status(self):
                raise AssertionError

        class MockClient:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def get(self, url, headers=None, params=None):
                return RateLimitResponse()

        monkeypatch.setattr(
            "discoursekit.ingest.naver_common.httpx.Client",
            lambda **kw: MockClient(),
        )
        assert list(NaverBlogAdapter().ingest(_base_params(source="naver_blog"))) == []


# ── Cafe adapter ──


class TestNaverCafeAdapter:
    def test_source_name(self):
        assert NaverCafeAdapter().source_name == "naver_cafe"

    def test_ingest_returns_articles(self, monkeypatch):
        monkeypatch.setattr(
            "discoursekit.ingest.naver_common.httpx.Client",
            lambda **kw: _make_mock_client(MOCK_CAFE_RESPONSE)(),
        )
        articles = list(NaverCafeAdapter().ingest(
            _base_params(source="naver_cafe", query="이태원"),
        ))

        assert len(articles) == 2
        assert all(a.source == "naver_cafe" for a in articles)
        assert articles[0].title == "이태원 주민 모임 공지"
        assert articles[0].publisher == "이태원주민카페"

    def test_requires_query(self):
        params = _base_params(query=None, source="naver_cafe")
        with pytest.raises(ValueError, match="query"):
            list(NaverCafeAdapter().ingest(params))


# ── Web adapter ──


class TestNaverWebAdapter:
    def test_source_name(self):
        assert NaverWebAdapter().source_name == "naver_web"

    def test_ingest_returns_articles(self, monkeypatch):
        monkeypatch.setattr(
            "discoursekit.ingest.naver_common.httpx.Client",
            lambda **kw: _make_mock_client(MOCK_WEB_RESPONSE)(),
        )
        articles = list(NaverWebAdapter().ingest(
            _base_params(source="naver_web", query="성수동 상권"),
        ))

        assert len(articles) == 1
        assert articles[0].source == "naver_web"
        assert articles[0].title == "성수동 상권 분석 리포트"
        assert "<b>" not in articles[0].title

    def test_requires_query(self):
        params = _base_params(query=None, source="naver_web")
        with pytest.raises(ValueError, match="query"):
            list(NaverWebAdapter().ingest(params))
