"""Evidence verification tests."""

from discoursekit.llm.evidence_verify import verify_evidence


def test_exact_match():
    body = "Itaewon sales increased by 23 percent after the recovery campaign."
    evidence = "Itaewon sales increased by 23 percent after the recovery campaign."

    result = verify_evidence(evidence, body)

    assert result["match_type"] == "exact"
    assert result["source_offset"] == 0


def test_partial_match():
    body = "Itaewon local sales increased by about 23 percent after the recovery campaign."
    evidence = "Itaewon sales increased by 23 percent after the recovery campaign."

    result = verify_evidence(evidence, body)

    assert result["match_type"] == "partial"


def test_invalid_match():
    body = "Seoul changed a traffic policy."
    evidence = "Itaewon sales increased."

    result = verify_evidence(evidence, body)

    assert result["match_type"] == "invalid"
    assert result["source_offset"] is None


def test_empty_body():
    result = verify_evidence("Any sentence", "")

    assert result["match_type"] == "invalid"


def test_whitespace_normalization():
    body = "Itaewon   local   restaurants recovered."
    evidence = "Itaewon local restaurants recovered."

    result = verify_evidence(evidence, body)

    assert result["match_type"] == "exact"
