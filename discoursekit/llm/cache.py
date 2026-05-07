"""LLM response cache to avoid duplicate calls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def cache_key(category: str, **params: Any) -> str:
    """Build a stable cache key for an LLM task."""
    raw = json.dumps({"category": category, **params}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def get_cached(project_dir: Path, key: str) -> dict | None:
    path = project_dir / "llm_cache" / f"{key}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def set_cache(project_dir: Path, key: str, data: dict) -> None:
    cache_dir = project_dir / "llm_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def invalidate(project_dir: Path, category: str | None = None) -> None:
    """Invalidate all cached responses or only one category."""
    cache_dir = project_dir / "llm_cache"
    if not cache_dir.exists():
        return
    for path in cache_dir.glob("*.json"):
        if category is None:
            path.unlink()
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("_category") == category:
            path.unlink()
