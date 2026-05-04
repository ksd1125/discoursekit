"""SQLite database layer for DiscourseKit's 9-table schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping


EXPECTED_TABLE_NAMES: tuple[str, ...] = (
    "projects",
    "ingest_runs",
    "articles",
    "clean_runs",
    "label_schemas",
    "prompt_versions",
    "llm_jobs",
    "llm_results",
    "artifacts",
)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source TEXT NOT NULL,
    params_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    raw_count INTEGER,
    in_range_count INTEGER,
    error TEXT,
    sha256_manifest TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE TABLE IF NOT EXISTS articles (
    article_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    ingest_run_id TEXT NOT NULL,
    source TEXT NOT NULL,
    date TEXT NOT NULL,
    publisher TEXT,
    title TEXT NOT NULL,
    body_internal TEXT,
    body_excerpt TEXT,
    keywords TEXT,
    url TEXT,
    raw_json TEXT,
    cleaned_at TEXT,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (ingest_run_id) REFERENCES ingest_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_articles_project_date ON articles(project_id, date);

CREATE TABLE IF NOT EXISTS clean_runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    params_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    input_count INTEGER,
    output_count INTEGER,
    dedup_primary INTEGER,
    dedup_fallback INTEGER,
    dropped_short INTEGER,
    dropped_advert INTEGER,
    sha256_log TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE TABLE IF NOT EXISTS label_schemas (
    schema_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    schema_type TEXT NOT NULL,
    labels_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    version_id TEXT PRIMARY KEY,
    schema_id TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    FOREIGN KEY (schema_id) REFERENCES label_schemas(schema_id)
);

CREATE TABLE IF NOT EXISTS llm_jobs (
    job_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    schema_id TEXT NOT NULL,
    prompt_version_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    temperature REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    n_processed INTEGER DEFAULT 0,
    n_errors INTEGER DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    candidates_tokens INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0.0,
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (schema_id) REFERENCES label_schemas(schema_id),
    FOREIGN KEY (prompt_version_id) REFERENCES prompt_versions(version_id)
);

CREATE TABLE IF NOT EXISTS llm_results (
    result_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    article_id TEXT NOT NULL,
    label TEXT,
    labels_json TEXT,
    confidence REAL,
    rationale TEXT,
    raw_response_json TEXT,
    called_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES llm_jobs(job_id),
    FOREIGN KEY (article_id) REFERENCES articles(article_id),
    UNIQUE(job_id, article_id)
);

CREATE INDEX IF NOT EXISTS idx_llm_results_job ON llm_results(job_id);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER,
    created_at TEXT NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with row access and FK enforcement."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create the schema at db_path and return an open connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def verify_schema(conn: sqlite3.Connection) -> list[str]:
    """Return expected table names missing from the database."""
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    existing = {row["name"] for row in rows}
    return [name for name in EXPECTED_TABLE_NAMES if name not in existing]


def _as_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def upsert_project(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    """Insert or update one project row."""
    conn.execute(
        """
        INSERT INTO projects (
            project_id, name, created_at, updated_at, schema_version, description
        )
        VALUES (
            :project_id, :name, :created_at, :updated_at, :schema_version, :description
        )
        ON CONFLICT(project_id) DO UPDATE SET
            name = excluded.name,
            updated_at = excluded.updated_at,
            schema_version = excluded.schema_version,
            description = excluded.description
        """,
        dict(row),
    )


def get_project(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    """Fetch a project row by ID."""
    row = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
    return _as_dict(row)


def insert_article(
    conn: sqlite3.Connection,
    row: Mapping[str, Any],
    ingest_run_id: str | None = None,
) -> None:
    """Insert an article, ignoring duplicate article_id values."""
    data = dict(row)
    if ingest_run_id is not None:
        data["ingest_run_id"] = ingest_run_id
    conn.execute(
        """
        INSERT OR IGNORE INTO articles (
            article_id, project_id, ingest_run_id, source, date, publisher, title,
            body_internal, body_excerpt, keywords, url, raw_json, cleaned_at
        )
        VALUES (
            :article_id, :project_id, :ingest_run_id, :source, :date, :publisher, :title,
            :body_internal, :body_excerpt, :keywords, :url, :raw_json, :cleaned_at
        )
        """,
        data,
    )


def insert_ingest_run(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    """Insert a new ingest run record."""
    conn.execute(
        """
        INSERT INTO ingest_runs
            (run_id, project_id, source, params_json, started_at, status)
        VALUES
            (:run_id, :project_id, :source, :params_json, :started_at, :status)
        """,
        dict(row),
    )


def update_ingest_run(
    conn: sqlite3.Connection,
    run_id: str,
    updates: Mapping[str, Any],
) -> None:
    """Partially update an ingest run record."""
    if not updates:
        return
    data = dict(updates)
    allowed = {
        "finished_at",
        "status",
        "raw_count",
        "in_range_count",
        "error",
        "sha256_manifest",
    }
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Unsupported ingest_runs update column(s): {sorted(unknown)}")
    set_clause = ", ".join(f"{key} = :{key}" for key in data)
    data["_run_id"] = run_id
    conn.execute(f"UPDATE ingest_runs SET {set_clause} WHERE run_id = :_run_id", data)


def insert_clean_run(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    """Insert a new clean run record."""
    conn.execute(
        """
        INSERT INTO clean_runs
            (run_id, project_id, params_json, started_at, status)
        VALUES
            (:run_id, :project_id, :params_json, :started_at, :status)
        """,
        dict(row),
    )


def count_articles(conn: sqlite3.Connection, project_id: str, active_only: bool = False) -> int:
    """Count articles for a project."""
    if active_only:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE project_id = ? AND is_active = 1",
            (project_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    return int(row["n"])
