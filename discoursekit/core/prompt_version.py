"""PromptVersion domain model with sha256 tracking."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class PromptVersion:
    """One versioned prompt text, identified by sha256 for reproducibility."""

    version_id: str
    schema_id: str
    prompt_text: str
    created_at: str
    sha256: str

    @classmethod
    def create(cls, version_id: str, schema_id: str, prompt_text: str) -> "PromptVersion":
        return cls(
            version_id=version_id,
            schema_id=schema_id,
            prompt_text=prompt_text,
            created_at=datetime.now(timezone.utc).isoformat(),
            sha256=_sha256(prompt_text),
        )

    def verify(self) -> bool:
        """Return True if stored sha256 matches prompt_text."""
        return self.sha256 == _sha256(self.prompt_text)

    def to_db_row(self) -> dict:
        return {
            "version_id": self.version_id,
            "schema_id": self.schema_id,
            "prompt_text": self.prompt_text,
            "created_at": self.created_at,
            "sha256": self.sha256,
        }

    @classmethod
    def from_db_row(cls, row: Mapping[str, Any]) -> "PromptVersion":
        return cls(
            version_id=row["version_id"],
            schema_id=row["schema_id"],
            prompt_text=row["prompt_text"],
            created_at=row["created_at"],
            sha256=row["sha256"],
        )
