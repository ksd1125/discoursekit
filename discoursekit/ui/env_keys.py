"""Local API key persistence for the Streamlit UI.

Keys are stored in the toolkit root ``.env`` file by default. They must never be
included in exports, reports, or handoff packages.
"""

from __future__ import annotations

from pathlib import Path


ENV_PATH = Path(".env")


def load_gemini_keys(env_path: Path | None = None) -> dict[int, str]:
    """Load GEMINI_KEY_1 through GEMINI_KEY_3 from a local .env file."""
    path = env_path or ENV_PATH
    keys: dict[int, str] = {}
    if not path.exists():
        return keys

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if not name.startswith("GEMINI_KEY_"):
            continue
        try:
            slot = int(name.removeprefix("GEMINI_KEY_"))
        except ValueError:
            continue
        value = value.strip().strip('"').strip("'")
        if 1 <= slot <= 3 and value:
            keys[slot] = value
    return keys


def save_gemini_keys(keys: dict[int, str], env_path: Path | None = None) -> Path:
    """Save GEMINI_KEY_1 through GEMINI_KEY_3 while preserving other .env entries."""
    path = env_path or ENV_PATH
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    filtered = [
        line
        for line in existing_lines
        if not line.strip().startswith("GEMINI_KEY_")
    ]

    for slot in range(1, 4):
        value = keys.get(slot, "").strip()
        if value:
            filtered.append(f"GEMINI_KEY_{slot}={value}")

    path.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")
    return path

