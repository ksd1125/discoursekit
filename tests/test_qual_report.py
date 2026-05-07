"""Qualitative report tests."""

import json

import pytest

from discoursekit.qual.codebook import get_template, save_codebook
from discoursekit.qual.coding import CodingRecord, EvidenceSentence, save_coding
from discoursekit.qual.report import generate_qualitative_report, save_report


def test_generate_report_minimal(tmp_path):
    qual_dir = tmp_path / "qual"
    qual_dir.mkdir()
    (qual_dir / "qual_config.json").write_text(
        json.dumps({"research_question": "How is place represented?", "method": "place_discourse"}),
        encoding="utf-8",
    )

    report = generate_qualitative_report(tmp_path)

    assert "# Qualitative Analysis Report" in report
    assert "How is place represented?" in report
    assert "(missing)" in report


def test_generate_report_full(tmp_path):
    save_codebook(tmp_path, get_template("qualitative_content_analysis"))
    save_coding(
        tmp_path,
        CodingRecord(
            article_id="a1",
            coder_id="researcher",
            codes=["content_category"],
            evidence_sentences=[
                EvidenceSentence(text="Evidence sentence", code="content_category")
            ],
            memo="memo",
            coded_at="2026-05-05T00:00:00+00:00",
        ),
    )

    report = generate_qualitative_report(tmp_path)

    assert "content_category" in report
    assert "Evidence sentence" in report
    assert "Total coded articles: 1" in report


def test_generate_report_unsupported_format(tmp_path):
    with pytest.raises(ValueError):
        generate_qualitative_report(tmp_path, format="html")


def test_save_report(tmp_path):
    path = save_report(tmp_path, "# Report\n")

    assert path.exists()
    assert path.suffix == ".md"
    assert path.parent.name == "reports"
