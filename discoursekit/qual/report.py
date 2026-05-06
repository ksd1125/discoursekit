"""Markdown report generation for qualitative analysis."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from discoursekit.qual.codebook import load_codebook
from discoursekit.qual.coding import code_frequency, load_all_codings
from discoursekit.qual.evidence import build_evidence_index


def generate_qualitative_report(project_dir: Path, format: str = "markdown") -> str:
    """Generate a qualitative analysis report as markdown text."""
    if format != "markdown":
        raise ValueError("Only markdown format is supported")

    config = _load_json(project_dir / "qual" / "qual_config.json")
    codebook = _try_load_codebook(project_dir)
    codings = load_all_codings(project_dir)
    frequencies = code_frequency(project_dir)
    evidence = build_evidence_index(project_dir)
    reliability = _latest_reliability(project_dir)

    lines = [
        "# Qualitative Analysis Report",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## 1. Research Question",
        "",
        str(config.get("research_question") or "(missing)"),
        "",
        "## 2. Method",
        "",
        str(config.get("method") or (codebook or {}).get("method") or "(missing)"),
        "",
        "## 3. Codebook",
        "",
    ]
    lines.extend(_codebook_section(codebook))
    lines.extend(["", "## 4. Coding Summary", ""])
    lines.extend(_coding_summary_section(frequencies, len(codings)))
    lines.extend(["", "## 5. Evidence Sentences", ""])
    lines.extend(_evidence_section(evidence, codebook))
    lines.extend(["", "## 6. Reliability", ""])
    lines.extend(_reliability_section(reliability))
    lines.extend(["", "## 7. Method Memo", ""])
    lines.extend(
        [
            f"- Method: {config.get('method') or (codebook or {}).get('method') or '(missing)'}",
            f"- Codes: {_code_count(codebook)}",
            f"- Coded articles: {len(codings)}",
            f"- Coder: {codings[0].coder_id if codings else '(missing)'}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def save_report(project_dir: Path, content: str) -> Path:
    """Save report content under ``qual/reports``."""
    reports_dir = project_dir / "qual" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"report_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.md"
    path.write_text(content, encoding="utf-8")
    return path


def _try_load_codebook(project_dir: Path) -> dict | None:
    try:
        return load_codebook(project_dir)
    except ValueError:
        return None


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _codebook_section(codebook: dict | None) -> list[str]:
    if not codebook:
        return ["(missing)"]
    rows = ["| Code | Label | Definition |", "|------|-------|------------|"]
    for code in _iter_codes(codebook):
        rows.append(
            f"| {code.get('code', '')} | {code.get('label', '')} | {code.get('definition', '')} |"
        )
    return rows


def _coding_summary_section(frequencies: dict[str, int], n_codings: int) -> list[str]:
    if not frequencies:
        return ["(not calculated)", "", f"Total coded articles: {n_codings}"]
    rows = ["| Code | Frequency |", "|------|-----------|"]
    for code, count in frequencies.items():
        rows.append(f"| {code} | {count} |")
    rows.extend(["", f"Total coded articles: {n_codings}"])
    return rows


def _evidence_section(evidence: dict[str, list[dict]], codebook: dict | None) -> list[str]:
    if not evidence:
        return ["(missing)"]
    labels = {code.get("code", ""): code.get("label", "") for code in _iter_codes(codebook or {})}
    lines = []
    for code, rows in sorted(evidence.items()):
        title = f"{code} ({labels.get(code, '')})".strip()
        lines.extend([f"### {title}", "", "| Evidence sentence | Article |", "|-------------------|---------|"])
        for row in rows:
            lines.append(f"| {row['text']} | {row['article_id']} |")
        lines.append("")
    return lines


def _reliability_section(reliability: dict | None) -> list[str]:
    if not reliability:
        return ["(not calculated)"]
    return [
        f"Cohen's kappa: {reliability.get('kappa', 0):.3f} ({reliability.get('interpretation', '')})",
        f"Percent agreement: {reliability.get('percent_agreement', 0):.1f}%",
        f"Articles: {reliability.get('n_articles', 0)}",
    ]


def _latest_reliability(project_dir: Path) -> dict | None:
    reliability_dir = project_dir / "qual" / "reliability"
    if not reliability_dir.exists():
        return None
    files = sorted(reliability_dir.glob("*.json"), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


def _iter_codes(codebook: dict):
    if "codes" in codebook:
        yield from codebook.get("codes", [])
        return
    for element in codebook.get("frame_elements", []):
        yield from element.get("codes", [])


def _code_count(codebook: dict | None) -> int:
    if not codebook:
        return 0
    return sum(1 for _ in _iter_codes(codebook))
