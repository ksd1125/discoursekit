"""Import an ingest-only handoff zip into a project folder."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from discoursekit.config import APP_SCHEMA_VERSION
from discoursekit.core.db import get_connection, init_db, verify_schema


def import_ingest_handoff(
    zip_path: Path,
    target_project_id: str | None = None,
    target_base_dir: Path | None = None,
) -> dict:
    """Import an ingest-only handoff zip and prepare it for cleaning."""
    if not zip_path.exists():
        raise FileNotFoundError(f"Handoff zip not found: {zip_path}")

    messages: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = archive.namelist()
        if "manifest.toml" not in names:
            raise ValueError("Invalid handoff: manifest.toml missing")
        if "data/project.db" not in names:
            raise ValueError("Invalid handoff: data/project.db missing")

        manifest_text = archive.read("manifest.toml").decode("utf-8")
        manifest = _parse_simple_toml(manifest_text)
        schema_version = manifest.get("handoff", {}).get("schema_version", "")
        if schema_version and schema_version != APP_SCHEMA_VERSION:
            messages.append(
                f"Warning: handoff schema {schema_version} != app schema {APP_SCHEMA_VERSION}. "
                "Migration may be needed."
            )

        if "checksums.sha256" in names:
            _verify_checksums(
                archive,
                archive.read("checksums.sha256").decode("utf-8"),
                messages,
            )

        base_dir = target_base_dir or Path.cwd()
        original_project_id = manifest.get("project", {}).get("project_id", "imported")
        project_id = target_project_id or original_project_id
        project_dir = base_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "raw").mkdir(exist_ok=True)
        (project_dir / "artifacts").mkdir(exist_ok=True)

        db_dest = project_dir / "project.db"
        with archive.open("data/project.db") as src, open(db_dest, "wb") as dst:
            dst.write(src.read())

        # Extend the ingest-only DB to the full app schema so clean can run immediately.
        conn = init_db(db_dest)
        if project_id != original_project_id:
            _rewrite_project_id(conn, original_project_id, project_id)
        conn.close()

        for name in names:
            if name.startswith("data/raw/") and not name.endswith("/"):
                rel = name[len("data/raw/") :]
                destination = project_dir / "raw" / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as src, open(destination, "wb") as dst:
                    dst.write(src.read())

    conn = get_connection(db_dest)
    try:
        missing = verify_schema(conn)
        if missing:
            messages.append(f"Warning: imported DB missing tables: {missing}")
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        article_count = row["n"] if row else 0
    finally:
        conn.close()

    return {
        "project_id": project_id,
        "project_dir": str(project_dir),
        "article_count": article_count,
        "status": "success",
        "messages": messages,
    }


def _rewrite_project_id(conn, original_project_id: str, target_project_id: str) -> None:
    """Rewrite project_id while respecting SQLite foreign keys."""
    project_row = conn.execute(
        "SELECT * FROM projects WHERE project_id = ?",
        (original_project_id,),
    ).fetchone()
    if project_row is None:
        return
    with conn:
        conn.execute(
            """
            INSERT INTO projects (
                project_id, name, created_at, updated_at, schema_version, description
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                target_project_id,
                project_row["name"],
                project_row["created_at"],
                project_row["updated_at"],
                project_row["schema_version"],
                project_row["description"],
            ),
        )
        conn.execute(
            "UPDATE ingest_runs SET project_id = ? WHERE project_id = ?",
            (target_project_id, original_project_id),
        )
        conn.execute(
            "UPDATE articles SET project_id = ? WHERE project_id = ?",
            (target_project_id, original_project_id),
        )
        conn.execute("DELETE FROM projects WHERE project_id = ?", (original_project_id,))


def _parse_simple_toml(text: str) -> dict:
    """Minimal TOML parser for handoff manifests."""
    result: dict = {}
    current_section = result
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            result[section_name] = {}
            current_section = result[section_name]
        elif "=" in line:
            key, _, val = line.partition("=")
            value = val.strip().strip('"')
            if value.lower() in ("true", "false"):
                parsed: object = value.lower() == "true"
            elif value.isdigit():
                parsed = int(value)
            else:
                parsed = value
            current_section[key.strip()] = parsed
    return result


def _verify_checksums(
    archive: zipfile.ZipFile,
    checksum_text: str,
    messages: list[str],
) -> None:
    """Verify checksums and append warnings for mismatches."""
    for line in checksum_text.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            continue
        expected_hash, filepath = parts
        if filepath not in archive.namelist():
            messages.append(f"Checksum: file {filepath} not found in zip")
            continue
        actual_hash = hashlib.sha256(archive.read(filepath)).hexdigest()
        if actual_hash.lower() != expected_hash.lower():
            messages.append(f"Checksum mismatch: {filepath}")
