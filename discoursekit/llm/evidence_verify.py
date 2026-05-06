"""Evidence sentence verification for LLM enrichment outputs."""

from __future__ import annotations

import re


def verify_evidence(evidence: str, body: str | None) -> dict:
    """Verify whether an evidence sentence appears in the source body.

    Returns ``{"match_type": "exact"|"partial"|"invalid", "source_offset": int|None}``.
    Matching normalizes whitespace, but offsets are reported against the original
    body only when an exact raw match is available.
    """
    if not evidence or not body:
        return {"match_type": "invalid", "source_offset": None}

    evidence_norm = _normalize_ws(evidence)
    body_norm = _normalize_ws(body)
    if not evidence_norm or not body_norm:
        return {"match_type": "invalid", "source_offset": None}

    raw_offset = body.find(evidence)
    if raw_offset >= 0:
        return {"match_type": "exact", "source_offset": raw_offset}

    if evidence_norm in body_norm:
        return {"match_type": "exact", "source_offset": None}

    token_overlap = _token_overlap_ratio(evidence_norm, body_norm)
    if token_overlap >= 0.70:
        return {"match_type": "partial", "source_offset": None}

    grams = _char_ngrams(evidence_norm, n=3)
    if grams:
        hit_count = sum(1 for gram in grams if gram in body_norm)
        if hit_count / len(grams) >= 0.70:
            return {"match_type": "partial", "source_offset": None}

    return {"match_type": "invalid", "source_offset": None}


def verify_evidence_list(evidence_sentences: list[str], body: str | None) -> tuple[list[dict], int, int]:
    """Verify multiple evidence strings and return rows plus valid/invalid counts."""
    verified = []
    valid = 0
    invalid = 0
    for sentence in evidence_sentences:
        result = verify_evidence(sentence, body)
        row = {"text": sentence, **result}
        verified.append(row)
        if result["match_type"] in {"exact", "partial"}:
            valid += 1
        else:
            invalid += 1
    return verified, valid, invalid


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def _char_ngrams(text: str, n: int = 3) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < n:
        return [compact] if compact else []
    return [compact[i : i + n] for i in range(len(compact) - n + 1)]


def _token_overlap_ratio(evidence: str, body: str) -> float:
    evidence_tokens = [token.lower() for token in evidence.split() if token.strip()]
    if not evidence_tokens:
        return 0.0
    body_tokens = {token.lower() for token in body.split() if token.strip()}
    hits = sum(1 for token in evidence_tokens if token in body_tokens)
    return hits / len(evidence_tokens)
