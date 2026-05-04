"""Project model and folder management."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from discoursekit.config import (
    APP_SCHEMA_VERSION,
    ARTIFACTS_DIR_NAME,
    DB_FILENAME,
    RAW_DIR_NAME,
    get_projects_dir,
)
from discoursekit.core import db as db_layer


@dataclass
class Project:
    """A DiscourseKit project stored as one folder and one SQLite database."""

    project_id: str
    name: str
    data_dir: Path
    created_at: str
    description: str = ""

    @property
    def db_path(self) -> Path:
        return self.data_dir / DB_FILENAME

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / RAW_DIR_NAME

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / ARTIFACTS_DIR_NAME

    def open_db(self):
        return db_layer.get_connection(self.db_path)

    @classmethod
    def create(
        cls,
        name: str,
        description: str = "",
        base_dir: Path | None = None,
    ) -> "Project":
        """Create a new project folder and initialize its database."""
        project_id = str(uuid.uuid4())
        projects_root = base_dir or get_projects_dir()
        data_dir = projects_root / project_id
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / RAW_DIR_NAME).mkdir(exist_ok=True)
        (data_dir / ARTIFACTS_DIR_NAME).mkdir(exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        project = cls(
            project_id=project_id,
            name=name,
            data_dir=data_dir,
            created_at=now,
            description=description,
        )
        conn = db_layer.init_db(project.db_path)
        with conn:
            db_layer.upsert_project(
                conn,
                {
                    "project_id": project_id,
                    "name": name,
                    "created_at": now,
                    "updated_at": now,
                    "schema_version": APP_SCHEMA_VERSION,
                    "description": description,
                },
            )
        conn.close()
        return project

    @classmethod
    def open(cls, project_id: str, base_dir: Path | None = None) -> "Project":
        """Open an existing project by ID."""
        projects_root = base_dir or get_projects_dir()
        data_dir = projects_root / project_id
        if not data_dir.exists():
            raise FileNotFoundError(f"Project directory not found: {data_dir}")

        conn = db_layer.get_connection(data_dir / DB_FILENAME)
        row = db_layer.get_project(conn, project_id)
        conn.close()
        if row is None:
            raise ValueError(f"Project {project_id!r} not found in DB")
        return cls(
            project_id=project_id,
            name=row["name"],
            data_dir=data_dir,
            created_at=row["created_at"],
            description=row.get("description") or "",
        )

    @classmethod
    def list_all(cls, base_dir: Path | None = None) -> list["Project"]:
        """Return all projects found in base_dir."""
        projects_root = base_dir or get_projects_dir()
        results: list[Project] = []
        if not projects_root.exists():
            return results
        for subdir in sorted(projects_root.iterdir()):
            db_path = subdir / DB_FILENAME
            if db_path.exists():
                try:
                    results.append(cls.open(subdir.name, base_dir=projects_root))
                except Exception:
                    pass
        return results
