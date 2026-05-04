"""Step 1 unit tests."""

from __future__ import annotations

from discoursekit.config import (
    BODY_EXCERPT_MAX_LEN,
    load_local_env,
    sha256_of_text,
)
from discoursekit.core.article import Article
from discoursekit.core.db import (
    count_articles,
    init_db,
    insert_article,
    upsert_project,
    verify_schema,
)
from discoursekit.core.label_schema import LabelDefinition, LabelSchema
from discoursekit.core.project import Project
from discoursekit.core.prompt_version import PromptVersion

import pytest


def test_init_db_creates_all_nine_tables(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    missing = verify_schema(conn)
    conn.close()
    assert missing == [], f"Missing tables: {missing}"


def test_verify_schema_detects_missing_table(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    conn.execute("DROP TABLE artifacts")
    conn.commit()
    missing = verify_schema(conn)
    conn.close()
    assert "artifacts" in missing


def test_article_roundtrip():
    article = Article(
        article_id="bigkinds:abc123",
        source="bigkinds",
        date="2022-10-30",
        publisher="한국일보",
        title="이태원 참사",
        body_internal="전체 본문 텍스트 (분석용)",
        body_excerpt="전체 본문 텍스트 (분석용)"[:BODY_EXCERPT_MAX_LEN],
        keywords=["이태원", "참사"],
        url="https://example.com/article/1",
        raw={"original": "data"},
        cleaned_at="2026-05-03T00:00:00+00:00",
        project_id="proj-001",
    )
    row = article.to_db_row()
    assert "body_internal" in row
    assert "body_excerpt" in row
    assert row["keywords"] == "이태원, 참사"

    restored = Article.from_db_row({**row, "project_id": "proj-001"})
    assert restored.article_id == article.article_id
    assert restored.body_internal == article.body_internal
    assert restored.keywords == article.keywords


def test_insert_and_count_articles(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    now = "2026-05-03T00:00:00+00:00"
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
        conn.execute(
            "INSERT INTO ingest_runs (run_id, project_id, source, params_json, started_at, status) "
            "VALUES ('r1', 'p1', 'bigkinds', '{}', ?, 'running')",
            (now,),
        )
        for i in range(3):
            insert_article(
                conn,
                {
                    "article_id": f"bigkinds:art{i}",
                    "project_id": "p1",
                    "source": "bigkinds",
                    "date": "2022-10-30",
                    "publisher": "test",
                    "title": f"제목 {i}",
                    "body_internal": f"본문 {i}",
                    "body_excerpt": f"본문 {i}"[:200],
                    "keywords": "",
                    "url": "",
                    "raw_json": "{}",
                    "cleaned_at": now,
                },
                ingest_run_id="r1",
            )
    n = count_articles(conn, "p1")
    conn.close()
    assert n == 3


def test_insert_article_dedup(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    now = "2026-05-03T00:00:00+00:00"
    with conn:
        upsert_project(
            conn,
            {
                "project_id": "p1",
                "name": "T",
                "created_at": now,
                "updated_at": now,
                "schema_version": "1.0",
                "description": "",
            },
        )
        conn.execute(
            "INSERT INTO ingest_runs (run_id, project_id, source, params_json, started_at, status) "
            "VALUES ('r1', 'p1', 'bigkinds', '{}', ?, 'running')",
            (now,),
        )
        row = {
            "article_id": "bigkinds:dup",
            "project_id": "p1",
            "source": "bigkinds",
            "date": "2022-10-30",
            "publisher": "x",
            "title": "T",
            "body_internal": "B",
            "body_excerpt": "B",
            "keywords": "",
            "url": "",
            "raw_json": "{}",
            "cleaned_at": now,
        }
        insert_article(conn, row, "r1")
        insert_article(conn, row, "r1")
    n = count_articles(conn, "p1")
    conn.close()
    assert n == 1


def test_prompt_version_sha256():
    pv = PromptVersion.create("rel_v1", "relevance_v1", "당신은 뉴스 분류자입니다.")
    assert pv.verify() is True
    tampered = PromptVersion(
        version_id=pv.version_id,
        schema_id=pv.schema_id,
        prompt_text="변조된 텍스트",
        created_at=pv.created_at,
        sha256=pv.sha256,
    )
    assert tampered.verify() is False


def test_label_schema_invalid_type():
    with pytest.raises(ValueError, match="schema_type"):
        LabelSchema.create(
            schema_id="test",
            name="Test",
            schema_type="invalid_type",
            labels=[],
        )


def test_label_schema_roundtrip():
    schema = LabelSchema.create(
        schema_id="relevance_v1",
        name="Relevance",
        schema_type="single_label",
        labels=[LabelDefinition("relevant", "Relevant to the event", ["direct report"])],
    )
    row = schema.to_db_row()
    restored = LabelSchema.from_db_row(row)
    assert restored.schema_id == schema.schema_id
    assert restored.labels[0].name == "relevant"


def test_sha256_of_text_deterministic():
    text = "재현성 테스트"
    h1 = sha256_of_text(text)
    h2 = sha256_of_text(text)
    assert h1 == h2
    assert len(h1) == 64


def test_load_local_env_bom(tmp_path):
    env_file = tmp_path / ".env"
    content = "\ufeffGEMINI_KEY=testkey123\nDB_PATH=/data/test.db\n"
    env_file.write_bytes(content.encode("utf-8-sig"))
    result = load_local_env(env_file)
    assert result.get("GEMINI_KEY") == "testkey123"
    assert result.get("DB_PATH") == "/data/test.db"


def test_project_create(tmp_path):
    project = Project.create(name="이태원 2022", description="테스트", base_dir=tmp_path)
    assert project.db_path.exists()
    assert project.raw_dir.exists()
    assert project.artifacts_dir.exists()
    conn = project.open_db()
    missing = verify_schema(conn)
    conn.close()
    assert missing == []
