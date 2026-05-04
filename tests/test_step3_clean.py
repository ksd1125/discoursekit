"""Step 3 cleaning pipeline tests."""

from __future__ import annotations

from discoursekit.clean.dedup import run_dedup
from discoursekit.clean.filters import run_filters
from discoursekit.clean.pipeline import run_clean_pipeline
from discoursekit.clean.text_utils import clean_body, make_excerpt, strip_b_tags
from discoursekit.core.db import count_articles, init_db, upsert_project
from discoursekit.ingest.base import IngestParams
from discoursekit.ingest.bigkinds import BigKindsAdapter
from discoursekit.ingest.runner import run_ingest


def test_strip_b_tags():
    assert strip_b_tags("이태원 <b>참사</b> 현장") == "이태원 참사 현장"
    assert strip_b_tags("<B>강조</B>") == "강조"


def test_clean_body():
    raw = "  <p>이태원   <b>참사</b>   관련</p>  뉴스  "
    result = clean_body(raw)
    assert "<" not in result
    assert "  " not in result
    assert result == "이태원 참사 관련 뉴스"


def test_make_excerpt():
    short = "짧은 텍스트"
    assert make_excerpt(short) == short
    long_text = "가" * 300
    excerpt = make_excerpt(long_text, 200)
    assert len(excerpt) == 200
    assert excerpt.endswith("...")


def test_dedup_primary_exact():
    articles = [
        {"article_id": "a1", "title": "이태원 참사", "date": "2022-10-30", "publisher": "조선"},
        {"article_id": "a2", "title": "이태원 참사", "date": "2022-10-30", "publisher": "조선"},
        {"article_id": "a3", "title": "다른 제목", "date": "2022-10-30", "publisher": "중앙"},
    ]
    result = run_dedup(articles)
    assert "a1" in result.kept_ids
    assert "a2" in result.primary_dup_ids
    assert "a3" in result.kept_ids


def test_dedup_fallback_fuzzy():
    articles = [
        {
            "article_id": "a1",
            "title": "이태원 핼러윈 대형 참사 발생",
            "date": "2022-10-30",
            "publisher": "A",
        },
        {
            "article_id": "a2",
            "title": "이태원 핼러윈 대형 참사 발생!",
            "date": "2022-10-30",
            "publisher": "B",
        },
    ]
    result = run_dedup(articles, similarity_threshold=0.85)
    assert "a1" in result.kept_ids
    assert "a2" in result.fallback_dup_ids


def test_filters_drop_short():
    articles = [
        {
            "article_id": "a1",
            "title": "정상",
            "body_internal": "정상적인 길이의 기사 본문입니다. 최소 20자를 넘어야 합니다.",
        },
        {"article_id": "a2", "title": "단문", "body_internal": "짧음"},
    ]
    result = run_filters(articles, min_body_chars=20)
    assert "a1" in result.kept_ids
    assert "a2" in result.dropped_short


def test_filters_drop_advert():
    articles = [
        {
            "article_id": "a1",
            "title": "[광고] 홍보 기사",
            "body_internal": "충분히 긴 광고 본문 텍스트입니다.",
        },
        {
            "article_id": "a2",
            "title": "정상 기사",
            "body_internal": "정상적인 기사 본문입니다. 이것은 광고가 아닙니다.",
        },
    ]
    result = run_filters(articles, min_body_chars=10)
    assert "a1" in result.dropped_advert
    assert "a2" in result.kept_ids


def test_full_clean_pipeline(sample_bigkinds_xlsx, tmp_path):
    db_path = tmp_path / "project.db"
    conn = init_db(db_path)
    now = "2026-05-04T00:00:00+00:00"
    with conn:
        upsert_project(
            conn,
            {
                "project_id": "p1",
                "name": "Test",
                "created_at": now,
                "updated_at": now,
                "schema_version": "1.0",
                "description": "",
            },
        )
    conn.close()

    params = IngestParams(project_id="p1", source="bigkinds", input_path=sample_bigkinds_xlsx)
    run_ingest(BigKindsAdapter(), params, db_path)
    run_id = run_clean_pipeline(db_path, "p1", min_body_chars=10)

    conn = init_db(db_path)
    run_row = conn.execute("SELECT * FROM clean_runs WHERE run_id=?", (run_id,)).fetchone()
    assert dict(run_row)["status"] == "success"
    assert dict(run_row)["input_count"] == 5
    assert count_articles(conn, "p1", active_only=True) == 5
    conn.close()
