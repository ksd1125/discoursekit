"""Qualitative evidence backend tests."""

import csv

from discoursekit.qual.coding import CodingRecord, EvidenceSentence, save_coding
from discoursekit.qual.evidence import build_evidence_index, evidence_by_code, export_evidence_csv


def _save(project_dir, article_id: str, code: str):
    save_coding(
        project_dir,
        CodingRecord(
            article_id=article_id,
            coder_id="researcher",
            codes=[code],
            evidence_sentences=[EvidenceSentence(text=f"{code} evidence {article_id}", code=code)],
            memo="",
            coded_at="2026-05-05T00:00:00+00:00",
        ),
    )


def test_build_evidence_index(tmp_path):
    _save(tmp_path, "a1", "safety")
    _save(tmp_path, "a2", "safety")

    index = build_evidence_index(tmp_path)

    assert len(index["safety"]) == 2


def test_evidence_by_code(tmp_path):
    _save(tmp_path, "a1", "safety")
    _save(tmp_path, "a2", "economy")

    rows = evidence_by_code(tmp_path, "safety")

    assert len(rows) == 1
    assert rows[0]["article_id"] == "a1"


def test_evidence_by_code_empty(tmp_path):
    assert evidence_by_code(tmp_path, "missing") == []


def test_export_evidence_csv(tmp_path):
    _save(tmp_path, "a1", "safety")
    output_path = export_evidence_csv(tmp_path, tmp_path / "evidence.csv")

    with output_path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    assert rows[0]["code"] == "safety"
    assert set(rows[0]) == {"code", "text", "article_id", "coder_id"}


def test_export_evidence_csv_empty(tmp_path):
    output_path = export_evidence_csv(tmp_path, tmp_path / "evidence.csv")

    with output_path.open(encoding="utf-8-sig", newline="") as file:
        header = file.readline().strip()

    assert header == "code,text,article_id,coder_id"
