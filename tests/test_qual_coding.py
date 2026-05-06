"""Qualitative coding backend tests."""

from dataclasses import FrozenInstanceError

import pytest

from discoursekit.qual.coding import (
    CodingRecord,
    EvidenceSentence,
    code_frequency,
    coding_progress,
    load_all_codings,
    load_coding,
    save_coding,
)


def _record(article_id: str, codes: list[str], status: str = "complete") -> CodingRecord:
    return CodingRecord(
        article_id=article_id,
        coder_id="researcher",
        codes=codes,
        evidence_sentences=[
            EvidenceSentence(text=f"Evidence for {article_id}", code=codes[0] if codes else "none")
        ],
        memo="memo",
        coded_at="2026-05-05T00:00:00+00:00",
        status=status,
    )


def test_save_and_load_coding(tmp_path):
    record = _record("naver:1", ["safety"])

    path = save_coding(tmp_path, record)
    loaded = load_coding(tmp_path, "naver:1")

    assert path.exists()
    assert loaded == record


def test_load_coding_not_exists(tmp_path):
    assert load_coding(tmp_path, "missing") is None


def test_load_all_codings(tmp_path):
    save_coding(tmp_path, _record("a3", ["safety"]))
    save_coding(tmp_path, _record("a1", ["economy"]))
    save_coding(tmp_path, _record("a2", ["safety"]))

    records = load_all_codings(tmp_path)

    assert [record.article_id for record in records] == ["a1", "a2", "a3"]


def test_coding_progress(tmp_path):
    save_coding(tmp_path, _record("a1", ["safety"], status="complete"))
    save_coding(tmp_path, _record("a2", ["economy"], status="complete"))
    save_coding(tmp_path, _record("a3", ["safety"], status="in_progress"))

    progress = coding_progress(tmp_path, ["a1", "a2", "a3", "a4", "a5"])

    assert progress == {"total": 5, "complete": 2, "in_progress": 1, "pending": 2}


def test_code_frequency(tmp_path):
    save_coding(tmp_path, _record("a1", ["safety", "economy"]))
    save_coding(tmp_path, _record("a2", ["safety"]))

    assert code_frequency(tmp_path) == {"safety": 2, "economy": 1}


def test_coding_record_frozen():
    record = _record("a1", ["safety"])

    with pytest.raises(FrozenInstanceError):
        record.article_id = "changed"
