"""LabelSchema domain model."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass
class LabelDefinition:
    name: str
    description: str
    examples: list[str]


@dataclass
class LabelSchema:
    """Definition of a labelling scheme used for LLM classification."""

    schema_id: str
    name: str
    schema_type: str
    labels: list[LabelDefinition]
    created_at: str
    description: str = ""

    @classmethod
    def create(
        cls,
        schema_id: str,
        name: str,
        schema_type: str,
        labels: list[LabelDefinition],
        description: str = "",
    ) -> "LabelSchema":
        if schema_type not in ("single_label", "multi_label"):
            raise ValueError(
                f"schema_type must be 'single_label' or 'multi_label', got {schema_type!r}"
            )
        return cls(
            schema_id=schema_id,
            name=name,
            schema_type=schema_type,
            labels=labels,
            created_at=datetime.now(timezone.utc).isoformat(),
            description=description,
        )

    def labels_to_json(self) -> str:
        return json.dumps(
            [
                {"name": label.name, "description": label.description, "examples": label.examples}
                for label in self.labels
            ],
            ensure_ascii=False,
        )

    def to_db_row(self) -> dict:
        return {
            "schema_id": self.schema_id,
            "name": self.name,
            "schema_type": self.schema_type,
            "labels_json": self.labels_to_json(),
            "created_at": self.created_at,
            "description": self.description,
        }

    @classmethod
    def from_db_row(cls, row: Mapping[str, Any]) -> "LabelSchema":
        raw_labels = json.loads(row["labels_json"] or "[]")
        labels = [
            LabelDefinition(
                name=label["name"],
                description=label["description"],
                examples=label.get("examples", []),
            )
            for label in raw_labels
        ]
        return cls(
            schema_id=row["schema_id"],
            name=row["name"],
            schema_type=row["schema_type"],
            labels=labels,
            created_at=row["created_at"],
            description=row["description"] or "",
        )
