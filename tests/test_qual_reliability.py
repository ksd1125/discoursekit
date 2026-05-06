"""Qualitative reliability tests."""

from discoursekit.qual.coding import CodingRecord
from discoursekit.qual.reliability import (
    compute_cohens_kappa,
    disagreement_table,
    interpret_kappa,
)


def _record(article_id: str, codes: list[str], coder_id: str = "coder") -> CodingRecord:
    return CodingRecord(
        article_id=article_id,
        coder_id=coder_id,
        codes=codes,
        evidence_sentences=[],
        memo="",
        coded_at="2026-05-05T00:00:00+00:00",
    )


def test_cohens_kappa_perfect():
    a = [_record("a1", ["safety"]), _record("a2", [])]
    b = [_record("a1", ["safety"]), _record("a2", [])]

    result = compute_cohens_kappa(a, b, ["safety"])

    assert result["kappa"] == 1.0


def test_cohens_kappa_partial():
    a = [_record("a1", ["safety"]), _record("a2", ["safety"]), _record("a3", [])]
    b = [_record("a1", ["safety"]), _record("a2", []), _record("a3", [])]

    result = compute_cohens_kappa(a, b, ["safety"])

    assert 0 < result["kappa"] < 1


def test_cohens_kappa_no_overlap():
    result = compute_cohens_kappa([_record("a1", ["safety"])], [_record("a2", ["safety"])], ["safety"])

    assert result["kappa"] == 0.0
    assert result["percent_agreement"] == 0.0


def test_interpret_kappa_ranges():
    assert interpret_kappa(-0.1) == "Poor"
    assert interpret_kappa(0.1) == "Slight"
    assert interpret_kappa(0.3) == "Fair"
    assert interpret_kappa(0.5) == "Moderate"
    assert interpret_kappa(0.7) == "Substantial"
    assert interpret_kappa(0.9) == "Almost perfect"


def test_disagreement_table():
    a = [_record("a1", ["safety"]), _record("a2", ["economy"])]
    b = [_record("a1", []), _record("a2", ["economy"])]

    rows = disagreement_table(a, b)

    assert rows == [{"article_id": "a1", "coder_a_codes": ["safety"], "coder_b_codes": []}]


def test_disagreement_table_all_agree():
    a = [_record("a1", ["safety"])]
    b = [_record("a1", ["safety"])]

    assert disagreement_table(a, b) == []


def test_per_code_kappa():
    a = [_record("a1", ["safety"]), _record("a2", ["economy"])]
    b = [_record("a1", ["safety"]), _record("a2", [])]

    result = compute_cohens_kappa(a, b, ["safety", "economy"])

    assert set(result["per_code_kappa"]) == {"safety", "economy"}
