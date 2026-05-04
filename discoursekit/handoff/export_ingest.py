"""Ingest-only handoff package export."""

from __future__ import annotations

import hashlib
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from discoursekit import __version__
from discoursekit.config import APP_SCHEMA_VERSION, sha256_of_file
from discoursekit.core.db import get_connection


EXPORT_SCHEMA_SQL = """
CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    description TEXT
);
CREATE TABLE ingest_runs (
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
CREATE TABLE articles (
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
CREATE INDEX idx_articles_project_date ON articles(project_id, date);
"""


def export_ingest_handoff(
    project_db_path: Path,
    project_id: str,
    output_path: Path,
    include_raw: bool = False,
    project_raw_dir: Path | None = None,
) -> Path:
    """Create an ingest-only handoff zip without secrets or local .env files."""
    if not project_db_path.exists():
        raise FileNotFoundError(f"DB not found: {project_db_path}")
    if include_raw and project_raw_dir is None:
        raise ValueError("project_raw_dir is required when include_raw=True")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_db_path = output_path.parent / f"_handoff_temp_{project_id}.db"
    if temp_db_path.exists():
        temp_db_path.unlink()

    conn = get_connection(project_db_path)
    try:
        project_row = conn.execute(
            "SELECT * FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if project_row is None:
            raise ValueError(f"Project {project_id!r} not found in DB")

        article_count = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM articles WHERE project_id = ?",
                (project_id,),
            ).fetchone()["n"]
        )
        date_row = conn.execute(
            "SELECT MIN(date) AS date_min, MAX(date) AS date_max FROM articles WHERE project_id = ?",
            (project_id,),
        ).fetchone()

        export_conn = sqlite3.connect(temp_db_path)
        export_conn.row_factory = sqlite3.Row
        try:
            export_conn.executescript(EXPORT_SCHEMA_SQL)
            _copy_project(conn, export_conn, project_id)
            _copy_ingest_runs(conn, export_conn, project_id)
            _copy_articles(conn, export_conn, project_id)
            export_conn.commit()
        finally:
            export_conn.close()

        created_at = datetime.now(timezone.utc).isoformat()
        manifest = _build_manifest(
            project_id=project_id,
            project_name=project_row["name"],
            article_count=article_count,
            date_range=(date_row["date_min"] or "", date_row["date_max"] or ""),
            include_raw=include_raw,
            created_at=created_at,
        )

        readme = _build_import_readme(project_id, article_count)
        checksums: list[tuple[str, str]] = [
            ("data/project.db", sha256_of_file(temp_db_path)),
            ("manifest.toml", _sha256_text(manifest)),
            ("README_IMPORT.md", _sha256_text(readme)),
        ]
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(temp_db_path, "data/project.db")
            archive.writestr("manifest.toml", manifest)

            if include_raw and project_raw_dir and project_raw_dir.exists():
                for raw_file in sorted(project_raw_dir.rglob("*")):
                    if raw_file.is_file() and not _is_secret_path(raw_file):
                        arcname = f"data/raw/{raw_file.relative_to(project_raw_dir).as_posix()}"
                        archive.write(raw_file, arcname)
                        checksums.append((arcname, sha256_of_file(raw_file)))

            checksum_text = "\n".join(f"{digest}  {path}" for path, digest in checksums)
            archive.writestr("checksums.sha256", checksum_text)
            archive.writestr("README_IMPORT.md", readme)
    finally:
        conn.close()
        if temp_db_path.exists():
            temp_db_path.unlink()

    return output_path


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _copy_project(src: sqlite3.Connection, dst: sqlite3.Connection, project_id: str) -> None:
    row = src.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
    dst.execute(
        """
        INSERT INTO projects (
            project_id, name, created_at, updated_at, schema_version, description
        )
        VALUES (
            :project_id, :name, :created_at, :updated_at, :schema_version, :description
        )
        """,
        _row_to_dict(row),
    )


def _copy_ingest_runs(src: sqlite3.Connection, dst: sqlite3.Connection, project_id: str) -> None:
    rows = src.execute("SELECT * FROM ingest_runs WHERE project_id = ?", (project_id,)).fetchall()
    for row in rows:
        dst.execute(
            """
            INSERT INTO ingest_runs (
                run_id, project_id, source, params_json, started_at, finished_at,
                status, raw_count, in_range_count, error, sha256_manifest
            )
            VALUES (
                :run_id, :project_id, :source, :params_json, :started_at, :finished_at,
                :status, :raw_count, :in_range_count, :error, :sha256_manifest
            )
            """,
            _row_to_dict(row),
        )


def _copy_articles(src: sqlite3.Connection, dst: sqlite3.Connection, project_id: str) -> None:
    rows = src.execute("SELECT * FROM articles WHERE project_id = ?", (project_id,)).fetchall()
    for row in rows:
        dst.execute(
            """
            INSERT INTO articles (
                article_id, project_id, ingest_run_id, source, date, publisher, title,
                body_internal, body_excerpt, keywords, url, raw_json, cleaned_at, is_active
            )
            VALUES (
                :article_id, :project_id, :ingest_run_id, :source, :date, :publisher, :title,
                :body_internal, :body_excerpt, :keywords, :url, :raw_json, :cleaned_at, :is_active
            )
            """,
            _row_to_dict(row),
        )


def _is_secret_path(path: Path) -> bool:
    secret_names = {".env", "secrets.toml"}
    return path.name in secret_names or ".streamlit" in path.parts


def _build_manifest(
    project_id: str,
    project_name: str,
    article_count: int,
    date_range: tuple[str, str],
    include_raw: bool,
    created_at: str,
) -> str:
    """Generate manifest.toml content."""
    return f"""# DiscourseKit Ingest-only Handoff Manifest
[handoff]
type = "ingest_only"
schema_version = "{APP_SCHEMA_VERSION}"
created_at = "{created_at}"
app_version = "{__version__}"

[project]
project_id = "{project_id}"
name = "{project_name}"
article_count = {article_count}
date_min = "{date_range[0]}"
date_max = "{date_range[1]}"
includes_raw = {str(include_raw).lower()}

[security]
api_keys_included = false
env_included = false
"""


def _build_import_readme(project_id: str, article_count: int) -> str:
    return f"""# Handoff Import Guide

This archive contains an ingest-only export from DiscourseKit.

## Contents
- `data/project.db` - SQLite database (projects, ingest_runs, articles)
- `checksums.sha256` - Integrity checksums

## Import Command
```bash
discoursekit import-handoff ./{project_id}_handoff.zip --as <new_project_name>
```

## Notes
- API keys are NOT included. Register them on the target machine.
- Article count: {article_count}
- After import, run `discoursekit clean` to start the cleaning step.
"""
