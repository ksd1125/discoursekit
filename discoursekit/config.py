"""Central configuration and path management for DiscourseKit."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


def _get_default_data_dir() -> Path:
    """Return the default data directory."""
    env_val = os.environ.get("DISCOURSEKIT_DATA_DIR", "")
    if env_val:
        return Path(env_val).expanduser().resolve()
    home_dir = Path.home() / "discoursekit_data"
    if _can_create_project_dir(home_dir):
        return home_dir
    return Path.cwd() / "discoursekit_data"


def _can_create_project_dir(data_dir: Path) -> bool:
    """Return True when the project root accepts new project directories."""
    probe = data_dir / "projects" / ".write_probe"
    try:
        probe.mkdir(parents=True, exist_ok=True)
        probe.rmdir()
        return True
    except OSError:
        return False


DEFAULT_DATA_DIR: Path = _get_default_data_dir()


def get_projects_dir(data_dir: Path | None = None) -> Path:
    base = data_dir or DEFAULT_DATA_DIR
    return base / "projects"


def get_logs_dir(data_dir: Path | None = None) -> Path:
    base = data_dir or DEFAULT_DATA_DIR
    return base / "logs"


def get_archive_dir(data_dir: Path | None = None) -> Path:
    base = data_dir or DEFAULT_DATA_DIR
    return base / "_archive"


APP_SCHEMA_VERSION: str = "1.0"
DB_FILENAME: str = "project.db"
RAW_DIR_NAME: str = "raw"
ARTIFACTS_DIR_NAME: str = "artifacts"
BODY_EXCERPT_MAX_LEN: int = 200
GEMINI_RPD_RESET_TZ: str = "America/Los_Angeles"


def load_api_key(env_var: str) -> str | None:
    """Load an API key from an environment variable."""
    return os.environ.get(env_var) or None


def mask_key(key: str | None) -> str:
    """Return a masked representation safe for logging."""
    if not key:
        return "(not set)"
    visible = min(4, len(key) // 4)
    return key[:visible] + "****" + key[-2:] if len(key) > visible + 2 else "****"


def sha256_of_file(path: Path) -> str:
    """Return hex-digest SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_of_text(text: str) -> str:
    """Return hex-digest SHA-256 of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_local_env(env_path: Path | None = None) -> dict[str, str]:
    """Load key=value pairs from a local .env file without mutating os.environ."""
    path = env_path or (Path.cwd() / ".env")
    if not path.exists():
        return {}

    raw = path.read_bytes()
    if raw[:2] == b"\xff\xfe":
        text = raw.decode("utf-16-le").lstrip("\ufeff")
    elif raw[:3] == b"\xef\xbb\xbf":
        text = raw.decode("utf-8-sig").lstrip("\ufeff")
    else:
        text = raw.decode("utf-8").lstrip("\ufeff")

    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        result[key.strip()] = val.strip().strip('"').strip("'")
    return result
