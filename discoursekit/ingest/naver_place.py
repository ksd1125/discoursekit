"""NAVER Place GraphQL review crawler for DiscourseKit.

Adapted from the sns-placeness project's naver_client.py + review_history.py.
Collects visitor reviews per place_id via the pcmap GraphQL endpoint.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

import httpx

GRAPHQL_ENDPOINT = "https://pcmap-api.place.naver.com/graphql"

USER_AGENTS: list[str] = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-S911N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
]

VISITOR_REVIEWS_QUERY = """
query getVisitorReviews($input: VisitorReviewsInput) {
  visitorReviews(input: $input) {
    items {
      id cursor reviewId body visitCount visited created originType representativeVisitDateTime
      votedKeywords { code name }
      visitCategories { code name keywords { code name } }
      item { name code }
    }
    total
  }
}
"""


@dataclass
class PlaceTarget:
    """One place to collect reviews for."""
    place_id: str
    place_name: str
    category: str = ""


@dataclass
class PlaceReviewRow:
    """A single review row ready for DB insertion."""
    review_id: str
    project_id: str
    place_id: str
    place_name: str
    review_month: str
    body: str
    voted_keywords: str
    menu_item: str
    origin_type: str
    raw_json: str
    collected_at: str


@dataclass
class _Pacer:
    base_ms: int = 2500
    min_ms: int = 800
    max_ms: int = 16000
    jitter_ms: int = 600
    current_ms: int = field(init=False)
    error_streak: int = 0
    success_count: int = 0

    def __post_init__(self) -> None:
        self.current_ms = self.base_ms

    def delay(self) -> float:
        return (self.current_ms + random.randint(0, self.jitter_ms)) / 1000.0

    def on_success(self) -> None:
        self.success_count += 1
        self.error_streak = 0
        if self.success_count % 5 == 0:
            self.current_ms = max(self.min_ms, int(self.current_ms * 0.92))

    def on_error(self, *, is_rate_limit: bool) -> None:
        self.error_streak += 1
        if is_rate_limit:
            self.current_ms = min(self.max_ms, self.current_ms * 2)


def _month_of(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m")
    except ValueError:
        return ""


def _headers(place_id: str) -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "*/*",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://m.place.naver.com",
        "Referer": f"https://m.place.naver.com/restaurant/{place_id}/review/visitor",
    }


def collect_place_reviews(
    project_id: str,
    places: list[PlaceTarget],
    *,
    max_pages_per_place: int = 10,
    page_size: int = 20,
    stop_month: str = "2020-01",
    progress_callback: Any = None,
) -> Iterator[PlaceReviewRow]:
    """Synchronously collect Place reviews for a list of places.

    Yields PlaceReviewRow objects suitable for bulk DB insertion.
    Uses adaptive pacing to avoid rate limits.
    """
    pacer = _Pacer()
    now_iso = datetime.now(timezone.utc).isoformat()

    with httpx.Client(
        http2=True, timeout=httpx.Timeout(20.0, connect=10.0), follow_redirects=False,
    ) as client:
        for place_idx, place in enumerate(places):
            if progress_callback:
                progress_callback(
                    f"[{place_idx + 1}/{len(places)}] {place.place_name} 리뷰 수집"
                )
            after = ""
            for page in range(max_pages_per_place):
                variables: dict[str, Any] = {
                    "input": {
                        "businessId": place.place_id,
                        "businessType": "restaurant",
                        "item": "0",
                        "size": page_size,
                        "getTrailer": True,
                        "includeReceiptPhotos": False,
                        "isPhotoUsed": True,
                    }
                }
                if after:
                    variables["input"]["after"] = after

                payload = {
                    "operationName": "getVisitorReviews",
                    "query": VISITOR_REVIEWS_QUERY,
                    "variables": variables,
                }

                reviews = _fetch_with_retry(
                    client, place.place_id, payload, pacer,
                )
                if reviews is None:
                    break

                oldest_month = ""
                for review in reviews:
                    row = _review_to_row(project_id, place, review, now_iso)
                    if row is not None:
                        yield row
                        if row.review_month and (
                            not oldest_month or row.review_month < oldest_month
                        ):
                            oldest_month = row.review_month

                next_cursor = reviews[-1].get("cursor") or "" if reviews else ""
                if not next_cursor:
                    break
                if oldest_month and oldest_month <= stop_month:
                    break
                after = next_cursor
                time.sleep(pacer.delay())


def _fetch_with_retry(
    client: httpx.Client,
    place_id: str,
    payload: dict,
    pacer: _Pacer,
    max_retries: int = 3,
) -> list[dict] | None:
    for attempt in range(max_retries):
        try:
            resp = client.post(
                GRAPHQL_ENDPOINT,
                json=payload,
                headers=_headers(place_id),
            )
        except (httpx.TransportError, httpx.ReadTimeout):
            pacer.on_error(is_rate_limit=False)
            time.sleep(2 ** attempt + random.random())
            continue

        if resp.status_code == 200:
            data = resp.json()
            if data.get("errors"):
                pacer.on_error(is_rate_limit=False)
                return None
            pacer.on_success()
            return (
                data.get("data", {})
                .get("visitorReviews", {})
                .get("items", [])
                or []
            )

        is_rl = resp.status_code in (429, 503)
        pacer.on_error(is_rate_limit=is_rl)
        time.sleep(2 ** attempt + random.random())

    return None


def _review_to_row(
    project_id: str,
    place: PlaceTarget,
    review: dict,
    collected_at: str,
) -> PlaceReviewRow | None:
    review_id = review.get("reviewId") or review.get("id") or ""
    if not review_id:
        return None

    voted = "|".join(
        k.get("name", "")
        for k in (review.get("votedKeywords") or [])
        if k.get("name")
    )
    item = review.get("item") or {}
    body = " ".join((review.get("body") or "").split())
    review_month = _month_of(
        review.get("representativeVisitDateTime") or ""
    )

    return PlaceReviewRow(
        review_id=review_id,
        project_id=project_id,
        place_id=place.place_id,
        place_name=place.place_name,
        review_month=review_month,
        body=body,
        voted_keywords=voted,
        menu_item=item.get("name") or "",
        origin_type=review.get("originType") or "",
        raw_json=json.dumps(review, ensure_ascii=False, default=str),
        collected_at=collected_at,
    )
