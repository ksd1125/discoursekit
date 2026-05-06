"""Qualitative codebook backend tests."""

import pytest

from discoursekit.qual.codebook import (
    codebook_history,
    get_template,
    load_codebook,
    save_codebook,
    validate_codebook,
)


def test_get_template_content_analysis():
    template = get_template("qualitative_content_analysis")

    assert template["codebook_id"]
    assert template["method"] == "qualitative_content_analysis"
    assert template["codes"]


def test_get_template_frame_analysis():
    template = get_template("frame_analysis")

    assert len(template["frame_elements"]) == 4


def test_get_template_unknown_method_raises():
    with pytest.raises(ValueError):
        get_template("unknown")


def test_validate_codebook_valid():
    codebook = get_template("qualitative_content_analysis")

    assert validate_codebook(codebook) == []


def test_validate_codebook_missing_id():
    codebook = get_template("qualitative_content_analysis")
    codebook["codebook_id"] = ""

    assert any("codebook_id" in error for error in validate_codebook(codebook))


def test_validate_codebook_duplicate_codes():
    codebook = get_template("qualitative_content_analysis")
    codebook["codes"].append(dict(codebook["codes"][0]))

    assert any("duplicate" in error for error in validate_codebook(codebook))


def test_validate_frame_missing_elements():
    codebook = get_template("frame_analysis")
    codebook["frame_elements"] = codebook["frame_elements"][:2]

    assert any("missing frame elements" in error for error in validate_codebook(codebook))


def test_save_and_load_codebook(tmp_path):
    codebook = get_template("place_discourse")

    path = save_codebook(tmp_path, codebook)
    loaded = load_codebook(tmp_path)
    history = codebook_history(tmp_path)

    assert path.exists()
    assert loaded == codebook
    assert len(history) == 1


def test_codebook_history_ordering(tmp_path):
    save_codebook(tmp_path, get_template("place_discourse"))
    save_codebook(tmp_path, get_template("thematic_analysis"))

    history = codebook_history(tmp_path)

    assert len(history) == 2
    assert history[0]["filename"] > history[1]["filename"]


def test_load_codebook_not_exists(tmp_path):
    with pytest.raises(ValueError):
        load_codebook(tmp_path)
