"""Shared fixtures for analysis module tests."""

from __future__ import annotations

from pathlib import Path

from discoursekit.core.db import init_db, insert_article, upsert_project


SAMPLE_ARTICLES = [
    ("a1", "2022-10-01", "Daily A", "Itaewon safety concern", "safety,local"),
    ("a2", "2022-10-05", "Daily B", "Itaewon safety management", "safety,management"),
    ("a3", "2022-10-20", "Daily C", "Itaewon tourism story", "tourism,local"),
    ("a4", "2022-10-30", "Daily A", "Itaewon memorial recovery", "memorial,recovery"),
    ("a5", "2022-11-01", "Daily B", "Itaewon recovery policy", "recovery,policy"),
    ("a6", "2022-11-12", "Daily C", "Itaewon responsibility debate", "responsibility,policy"),
    ("a7", "2022-11-20", "Daily D", "Itaewon recovery economy", "recovery,economy"),
    ("a8", "2022-12-01", "Daily E", "Itaewon resident recovery", "resident,recovery"),
]


def make_analysis_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "project.db"
    conn = init_db(db_path)
    now = "2026-05-05T00:00:00+00:00"
    with conn:
        upsert_project(
            conn,
            {
                "project_id": "test",
                "name": "Test",
                "created_at": now,
                "updated_at": now,
                "schema_version": "1.0",
                "description": "",
            },
        )
        conn.execute(
            """
            INSERT INTO ingest_runs (run_id, project_id, source, params_json, started_at, status)
            VALUES ('r1', 'test', 'naver_news', '{}', ?, 'success')
            """,
            (now,),
        )
        for article_id, date, publisher, title, keywords in SAMPLE_ARTICLES:
            insert_article(
                conn,
                {
                    "article_id": article_id,
                    "project_id": "test",
                    "source": "naver_news",
                    "date": date,
                    "publisher": publisher,
                    "title": title,
                    "body_internal": f"{title}. Body text for {keywords}.",
                    "body_excerpt": f"{title}. Body text for {keywords}.",
                    "keywords": keywords,
                    "url": "",
                    "raw_json": "{}",
                    "cleaned_at": now,
                },
                ingest_run_id="r1",
            )
    conn.close()
    return db_path
