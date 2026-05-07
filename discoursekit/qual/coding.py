"""Coding record persistence for qualitative analysis."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote


@dataclass(frozen=True)
class EvidenceSentence:
    """Evidence sentence attached to a qualitative code."""

    text: str
    code: str
    source: str = "body_excerpt"


@dataclass(frozen=True)
class CodingRecord:
    """One article-level coding record."""

    article_id: str
    coder_id: str
    codes: list[str]
    evidence_sentences: list[EvidenceSentence]
    memo: str
    coded_at: str
    llm_codes: list[str] | None = None
    llm_agreement: str | None = None
    status: str = "complete"


def save_coding(project_dir: Path, record: CodingRecord) -> Path:
    """Save one article coding record as JSON."""
    if record.status not in {"pending", "in_progress", "complete"}:
        raise ValueError("status must be pending, in_progress, or complete")
    path = _coding_path(project_dir, record.article_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_record_to_dict(record), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_coding(project_dir: Path, article_id: str) -> CodingRecord | None:
    """Load one article coding record, or None when missing."""
    path = _coding_path(project_dir, article_id)
    if not path.exists():
        return None
    return _record_from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_all_codings(project_dir: Path) -> list[CodingRecord]:
    """Load all coding records sorted by article_id."""
    coding_dir = project_dir / "qual" / "coding"
    if not coding_dir.exists():
        return []
    records = []
    for path in sorted(coding_dir.glob("*.json")):
        records.append(_record_from_dict(json.loads(path.read_text(encoding="utf-8"))))
    return sorted(records, key=lambda record: record.article_id)


def coding_progress(project_dir: Path, sample_article_ids: list[str]) -> dict:
    """Return coding progress for a sample article id list."""
    records = {record.article_id: record for record in load_all_codings(project_dir)}
    complete = 0
    in_progress = 0
    for article_id in sample_article_ids:
        record = records.get(article_id)
        if record is None:
            continue
        if record.status == "complete":
            complete += 1
        elif record.status == "in_progress":
            in_progress += 1
    total = len(sample_article_ids)
    return {
        "total": total,
        "complete": complete,
        "in_progress": in_progress,
        "pending": total - complete - in_progress,
    }


def code_frequency(project_dir: Path) -> dict[str, int]:
    """Return code assignment frequencies sorted by count descending."""
    counter: Counter[str] = Counter()
    for record in load_all_codings(project_dir):
        counter.update(record.codes)
    return dict(counter.most_common())


def _record_to_dict(record: CodingRecord) -> dict:
    return asdict(record)


def _record_from_dict(payload: dict) -> CodingRecord:
    evidence = [
        EvidenceSentence(
            text=str(item.get("text", "")),
            code=str(item.get("code", "")),
            source=str(item.get("source", "body_excerpt")),
        )
        for item in payload.get("evidence_sentences", [])
    ]
    return CodingRecord(
        article_id=str(payload.get("article_id", "")),
        coder_id=str(payload.get("coder_id", "researcher")),
        codes=[str(code) for code in payload.get("codes", [])],
        evidence_sentences=evidence,
        memo=str(payload.get("memo", "")),
        coded_at=str(payload.get("coded_at", "")),
        llm_codes=[str(code) for code in payload["llm_codes"]] if payload.get("llm_codes") is not None else None,
        llm_agreement=payload.get("llm_agreement"),
        status=str(payload.get("status", "complete")),
    )


def _coding_path(project_dir: Path, article_id: str) -> Path:
    safe_id = quote(article_id, safe="")
    return project_dir / "qual" / "coding" / f"{safe_id}.json"
