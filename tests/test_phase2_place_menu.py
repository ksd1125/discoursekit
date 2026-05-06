"""Tests for Phase 2: Place review schema, menu cleaning, observation aggregation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from discoursekit.core.db import (
    count_place_reviews,
    init_db,
    insert_place_review,
    migrate_schema,
    upsert_observation,
    verify_schema,
)
from discoursekit.analyze.place_menu import (
    build_observations,
    get_first_seen_by_channel,
    get_menu_summary,
    get_place_summary,
    normalize_menu_name,
)
from discoursekit.ui.pages.data_build import _split_date_range_monthly


# ─── Schema tests ───────────────────────────────────────────────────────


class TestPlaceReviewSchema:
    def test_init_db_creates_place_reviews_table(self, tmp_path: Path) -> None:
        conn = init_db(tmp_path / "test.db")
        missing = verify_schema(conn)
        assert "place_reviews" not in missing
        assert "monthly_place_menu_observations" not in missing
        conn.close()

    def test_migrate_adds_place_tables_to_old_db(self, tmp_path: Path) -> None:
        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE projects (project_id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT, updated_at TEXT, schema_version TEXT, description TEXT)")
        conn.execute("CREATE TABLE articles (article_id TEXT PRIMARY KEY, project_id TEXT, ingest_run_id TEXT, source TEXT, date TEXT, publisher TEXT, title TEXT, body_internal TEXT, body_excerpt TEXT, keywords TEXT, url TEXT, raw_json TEXT, cleaned_at TEXT, is_active INTEGER DEFAULT 1)")
        conn.commit()

        tables_before = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "place_reviews" not in tables_before

        applied = migrate_schema(conn)
        assert "table.place_reviews" in applied
        assert "table.monthly_place_menu_observations" in applied

        tables_after = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "place_reviews" in tables_after
        assert "monthly_place_menu_observations" in tables_after
        conn.close()

    def test_migrate_idempotent(self, tmp_path: Path) -> None:
        conn = init_db(tmp_path / "test.db")
        applied = migrate_schema(conn)
        assert applied == []
        conn.close()


# ─── DB operation tests ─────────────────────────────────────────────────


class TestPlaceReviewOps:
    def _setup_project(self, conn):
        conn.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?)",
            ("p1", "test", "2026-01-01", "2026-01-01", "1.0", ""),
        )
        conn.commit()

    def test_insert_and_count_place_reviews(self, tmp_path: Path) -> None:
        conn = init_db(tmp_path / "test.db")
        self._setup_project(conn)
        insert_place_review(conn, {
            "review_id": "r1",
            "project_id": "p1",
            "place_id": "place_001",
            "place_name": "카페A",
            "review_month": "2026-01",
            "body": "맛있어요",
            "voted_keywords": "맛있어요|가성비",
            "menu_item": "아메리카노",
            "origin_type": "receipt",
            "raw_json": "{}",
            "collected_at": "2026-05-07T00:00:00Z",
        })
        conn.commit()
        assert count_place_reviews(conn, "p1") == 1
        conn.close()

    def test_duplicate_review_ignored(self, tmp_path: Path) -> None:
        conn = init_db(tmp_path / "test.db")
        self._setup_project(conn)
        review = {
            "review_id": "r1",
            "project_id": "p1",
            "place_id": "place_001",
            "place_name": "카페A",
            "review_month": "2026-01",
            "body": "맛있어요",
            "voted_keywords": "",
            "menu_item": "라떼",
            "origin_type": "",
            "raw_json": "{}",
            "collected_at": "2026-05-07T00:00:00Z",
        }
        insert_place_review(conn, review)
        insert_place_review(conn, review)
        conn.commit()
        assert count_place_reviews(conn, "p1") == 1
        conn.close()

    def test_upsert_observation(self, tmp_path: Path) -> None:
        conn = init_db(tmp_path / "test.db")
        self._setup_project(conn)
        obs = {
            "project_id": "p1",
            "region_id": "",
            "place_id": "place_001",
            "place_name": "카페A",
            "review_month": "2026-01",
            "normalized_menu_name": "아메리카노",
            "raw_menu_examples": "아메리카노(HOT)|아메리카노",
            "review_count": 3,
            "first_seen_flag": 1,
            "continued_flag": 0,
        }
        upsert_observation(conn, obs)
        conn.commit()

        row = conn.execute(
            "SELECT * FROM monthly_place_menu_observations WHERE project_id = ?",
            ("p1",),
        ).fetchone()
        assert row["review_count"] == 3
        assert row["first_seen_flag"] == 1

        obs["review_count"] = 5
        upsert_observation(conn, obs)
        conn.commit()
        row = conn.execute(
            "SELECT review_count FROM monthly_place_menu_observations WHERE project_id = ?",
            ("p1",),
        ).fetchone()
        assert row["review_count"] == 5
        conn.close()


# ─── Menu name normalization tests ──────────────────────────────────────


class TestNormalizeMenu:
    def test_removes_price(self) -> None:
        assert normalize_menu_name("아메리카노 5,500원") == "아메리카노"

    def test_removes_parenthetical(self) -> None:
        assert normalize_menu_name("아메리카노(HOT)") == "아메리카노"

    def test_removes_size_modifier(self) -> None:
        assert normalize_menu_name("아메리카노 라지") == "아메리카노"
        assert normalize_menu_name("카페라떼 L") == "카페라떼"

    def test_removes_bracket_options(self) -> None:
        assert normalize_menu_name("돈카츠[치즈추가]") == "돈카츠"

    def test_preserves_short_menu_name(self) -> None:
        assert normalize_menu_name("우동") == "우동"

    def test_empty_after_cleaning(self) -> None:
        assert normalize_menu_name("L") == ""
        assert normalize_menu_name("") == ""
        assert normalize_menu_name("(옵션)") == ""

    def test_strips_trailing_junk(self) -> None:
        assert normalize_menu_name("돈카츠---") == "돈카츠"

    def test_complex_example(self) -> None:
        assert normalize_menu_name("수채화 플라워 디자인 쇼핑") == "수채화 플라워 디자인 쇼핑"


# ─── Observation aggregation tests ──────────────────────────────────────


class TestBuildObservations:
    def _seed_reviews(self, conn, project_id: str = "p1") -> None:
        conn.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, "test", "2026-01-01", "2026-01-01", "1.0", ""),
        )
        reviews = [
            ("r1", project_id, "pl1", "카페A", "2025-06", "좋아요", "", "아메리카노(HOT)", "", "{}", "2026-05-07"),
            ("r2", project_id, "pl1", "카페A", "2025-06", "맛있어요", "", "아메리카노 라지", "", "{}", "2026-05-07"),
            ("r3", project_id, "pl1", "카페A", "2025-07", "재방문", "", "아메리카노", "", "{}", "2026-05-07"),
            ("r4", project_id, "pl1", "카페A", "2025-07", "좋음", "", "카페라떼", "", "{}", "2026-05-07"),
            ("r5", project_id, "pl2", "식당B", "2025-08", "맛있음", "", "돈카츠 12,000원", "", "{}", "2026-05-07"),
            ("r6", project_id, "pl2", "식당B", "2025-08", "굿", "", "돈카츠(치즈)", "", "{}", "2026-05-07"),
            ("r7", project_id, "pl1", "카페A", "2025-08", "또옴", "", "아메리카노", "", "{}", "2026-05-07"),
        ]
        for r in reviews:
            conn.execute(
                "INSERT INTO place_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", r,
            )
        conn.commit()

    def test_build_observations_basic(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path)
        self._seed_reviews(conn)
        conn.close()

        summary = build_observations(db_path, "p1")
        assert summary.total_reviews == 7
        assert summary.reviews_with_menu == 7
        assert summary.unique_places == 2
        assert summary.unique_menus >= 3
        assert summary.observations_written > 0

    def test_first_seen_flag(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path)
        self._seed_reviews(conn)
        conn.close()

        build_observations(db_path, "p1")

        from discoursekit.core.db import get_connection
        conn = get_connection(db_path)
        first_seens = conn.execute(
            """
            SELECT place_id, normalized_menu_name, review_month
            FROM monthly_place_menu_observations
            WHERE project_id = 'p1' AND first_seen_flag = 1
            ORDER BY place_id, normalized_menu_name
            """,
        ).fetchall()
        first_seen_set = {
            (r["place_id"], r["normalized_menu_name"])
            for r in first_seens
        }
        assert ("pl1", "아메리카노") in first_seen_set
        assert ("pl1", "카페라떼") in first_seen_set
        assert ("pl2", "돈카츠") in first_seen_set
        conn.close()

    def test_continued_flag(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path)
        self._seed_reviews(conn)
        conn.close()

        build_observations(db_path, "p1")

        from discoursekit.core.db import get_connection
        conn = get_connection(db_path)
        continued = conn.execute(
            """
            SELECT DISTINCT place_id, normalized_menu_name
            FROM monthly_place_menu_observations
            WHERE project_id = 'p1' AND continued_flag = 1
            """,
        ).fetchall()
        continued_set = {(r["place_id"], r["normalized_menu_name"]) for r in continued}
        assert ("pl1", "아메리카노") in continued_set
        conn.close()

    def test_get_place_summary(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path)
        self._seed_reviews(conn)
        conn.close()

        build_observations(db_path, "p1")

        from discoursekit.core.db import get_connection
        conn = get_connection(db_path)
        summary = get_place_summary(conn, "p1")
        assert len(summary) == 2
        place_ids = {s["place_id"] for s in summary}
        assert "pl1" in place_ids
        assert "pl2" in place_ids
        conn.close()

    def test_get_menu_summary(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path)
        self._seed_reviews(conn)
        conn.close()

        build_observations(db_path, "p1")

        from discoursekit.core.db import get_connection
        conn = get_connection(db_path)
        summary = get_menu_summary(conn, "p1")
        menu_names = {s["normalized_menu_name"] for s in summary}
        assert "아메리카노" in menu_names
        assert "돈카츠" in menu_names
        conn.close()


# ─── Naver Place adapter tests ──────────────────────────────────────────


class TestNaverPlaceAdapter:
    def test_review_to_row(self) -> None:
        from discoursekit.ingest.naver_place import PlaceTarget, _review_to_row

        place = PlaceTarget(place_id="123", place_name="테스트식당")
        review = {
            "reviewId": "rev001",
            "body": "맛있어요 강추",
            "votedKeywords": [{"code": "1", "name": "맛있어요"}],
            "item": {"name": "비빔밥", "code": "100"},
            "representativeVisitDateTime": "2026-03-15T09:00:00.000Z",
            "originType": "receipt",
        }
        row = _review_to_row("proj1", place, review, "2026-05-07T00:00:00Z")
        assert row is not None
        assert row.review_id == "rev001"
        assert row.place_id == "123"
        assert row.place_name == "테스트식당"
        assert row.review_month == "2026-03"
        assert row.menu_item == "비빔밥"
        assert "맛있어요" in row.voted_keywords

    def test_review_to_row_missing_id_returns_none(self) -> None:
        from discoursekit.ingest.naver_place import PlaceTarget, _review_to_row

        place = PlaceTarget(place_id="123", place_name="테스트")
        review = {"body": "test"}
        row = _review_to_row("proj1", place, review, "2026-05-07T00:00:00Z")
        assert row is None

    def test_month_of(self) -> None:
        from discoursekit.ingest.naver_place import _month_of

        assert _month_of("2026-03-15T09:00:00.000Z") == "2026-03"
        assert _month_of("2025-12-31T23:59:59+09:00") == "2025-12"
        assert _month_of("") == ""
        assert _month_of("invalid") == ""


# ─── Date range splitting tests ─────────────────────────────────────────


class TestSplitDateRangeMonthly:
    def test_single_month(self) -> None:
        chunks = _split_date_range_monthly("2026-03-01", "2026-03-31")
        assert len(chunks) == 1
        assert chunks[0] == ("2026-03-01", "2026-03-31")

    def test_two_months(self) -> None:
        chunks = _split_date_range_monthly("2026-02-01", "2026-03-15")
        assert len(chunks) == 2
        assert chunks[0] == ("2026-02-01", "2026-02-28")
        assert chunks[1] == ("2026-03-01", "2026-03-15")

    def test_six_months(self) -> None:
        chunks = _split_date_range_monthly("2025-10-01", "2026-03-31")
        assert len(chunks) == 6
        assert chunks[0][0] == "2025-10-01"
        assert chunks[-1][1] == "2026-03-31"

    def test_partial_month_start(self) -> None:
        chunks = _split_date_range_monthly("2026-01-15", "2026-02-20")
        assert len(chunks) == 2
        assert chunks[0] == ("2026-01-15", "2026-01-31")
        assert chunks[1] == ("2026-02-01", "2026-02-20")

    def test_same_day(self) -> None:
        chunks = _split_date_range_monthly("2026-05-07", "2026-05-07")
        assert len(chunks) == 1
        assert chunks[0] == ("2026-05-07", "2026-05-07")

    def test_missing_dates(self) -> None:
        chunks = _split_date_range_monthly(None, None)
        assert len(chunks) == 1
        assert chunks[0] == ("", "")

    def test_empty_dates(self) -> None:
        chunks = _split_date_range_monthly("", "")
        assert len(chunks) == 1

    def test_year_boundary(self) -> None:
        chunks = _split_date_range_monthly("2025-12-01", "2026-01-31")
        assert len(chunks) == 2
        assert chunks[0] == ("2025-12-01", "2025-12-31")
        assert chunks[1] == ("2026-01-01", "2026-01-31")

    def test_leap_year_february(self) -> None:
        chunks = _split_date_range_monthly("2024-02-01", "2024-02-29")
        assert len(chunks) == 1
        assert chunks[0] == ("2024-02-01", "2024-02-29")
