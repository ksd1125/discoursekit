"""Evidence sentence indexing and export."""

from __future__ import annotations

import csv
from pathlib import Path

from discoursekit.qual.coding import load_all_codings


def build_evidence_index(project_dir: Path) -> dict[str, list[dict]]:
    """Index evidence sentences by code."""
    index: dict[str, list[dict]] = {}
    for record in load_all_codings(project_dir):
        for evidence in record.evidence_sentences:
            index.setdefault(evidence.code, []).append(
                {
                    "text": evidence.text,
                    "article_id": record.article_id,
                    "coder_id": record.coder_id,
                }
            )
    return index


def evidence_by_code(project_dir: Path, code: str) -> list[dict]:
    """Return evidence sentences for one code."""
    return build_evidence_index(project_dir).get(code, [])


def export_evidence_csv(project_dir: Path, output_path: Path) -> Path:
    """Export evidence sentences to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    index = build_evidence_index(project_dir)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["code", "text", "article_id", "coder_id"])
        writer.writeheader()
        for code, rows in sorted(index.items()):
            for row in rows:
                writer.writerow({"code": code, **row})
    return output_path
