"""Reliability helpers for qualitative coding."""

from __future__ import annotations

from discoursekit.qual.coding import CodingRecord


KAPPA_INTERPRETATION = [
    (0.00, "Poor"),
    (0.20, "Slight"),
    (0.40, "Fair"),
    (0.60, "Moderate"),
    (0.80, "Substantial"),
    (1.01, "Almost perfect"),
]


def compute_cohens_kappa(
    codings_a: list[CodingRecord],
    codings_b: list[CodingRecord],
    codes: list[str],
) -> dict:
    """Compute average binary Cohen's kappa across codes."""
    by_a = {record.article_id: record for record in codings_a}
    by_b = {record.article_id: record for record in codings_b}
    article_ids = sorted(set(by_a) & set(by_b))
    if not article_ids or not codes:
        return {
            "kappa": 0.0,
            "percent_agreement": 0.0,
            "interpretation": interpret_kappa(0.0),
            "n_articles": 0,
            "n_codes": len(codes),
            "per_code_kappa": {},
        }

    per_code = {}
    total_pairs = 0
    total_agree = 0
    for code in codes:
        a_yes = b_yes = agree = 0
        for article_id in article_ids:
            has_a = code in by_a[article_id].codes
            has_b = code in by_b[article_id].codes
            a_yes += int(has_a)
            b_yes += int(has_b)
            agree += int(has_a == has_b)
        n = len(article_ids)
        p_o = agree / n
        p_a1 = a_yes / n
        p_b1 = b_yes / n
        p_e = (p_a1 * p_b1) + ((1 - p_a1) * (1 - p_b1))
        kappa = 1.0 if p_e == 1.0 else (p_o - p_e) / (1 - p_e)
        per_code[code] = kappa
        total_pairs += n
        total_agree += agree

    avg_kappa = sum(per_code.values()) / len(per_code)
    percent_agreement = total_agree / total_pairs * 100.0 if total_pairs else 0.0
    return {
        "kappa": avg_kappa,
        "percent_agreement": percent_agreement,
        "interpretation": interpret_kappa(avg_kappa),
        "n_articles": len(article_ids),
        "n_codes": len(codes),
        "per_code_kappa": per_code,
    }


def interpret_kappa(kappa: float) -> str:
    """Interpret kappa using Landis and Koch-style labels."""
    if kappa < 0:
        return "Poor"
    if kappa <= 0.20:
        return "Slight"
    if kappa <= 0.40:
        return "Fair"
    if kappa <= 0.60:
        return "Moderate"
    if kappa <= 0.80:
        return "Substantial"
    return "Almost perfect"


def disagreement_table(
    codings_a: list[CodingRecord],
    codings_b: list[CodingRecord],
) -> list[dict]:
    """Return articles where coder code sets differ."""
    by_a = {record.article_id: record for record in codings_a}
    by_b = {record.article_id: record for record in codings_b}
    rows = []
    for article_id in sorted(set(by_a) & set(by_b)):
        codes_a = sorted(by_a[article_id].codes)
        codes_b = sorted(by_b[article_id].codes)
        if codes_a != codes_b:
            rows.append(
                {
                    "article_id": article_id,
                    "coder_a_codes": codes_a,
                    "coder_b_codes": codes_b,
                }
            )
    return rows
