"""Codebook templates, validation, and persistence."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_METHODS = [
    "qualitative_content_analysis",
    "frame_analysis",
    "thematic_analysis",
    "discourse_analysis",
    "place_discourse",
]

FRAME_ELEMENTS = [
    "problem_definition",
    "causal_interpretation",
    "moral_evaluation",
    "treatment_recommendation",
]


def load_codebook(project_dir: Path) -> dict:
    """Load ``qual/codebook.json``."""
    path = _codebook_path(project_dir)
    if not path.exists():
        raise ValueError(f"Codebook does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_codebook(project_dir: Path, codebook: dict) -> Path:
    """Validate and save a codebook, keeping a timestamped history copy."""
    errors = validate_codebook(codebook)
    if errors:
        raise ValueError("; ".join(errors))

    path = _codebook_path(project_dir)
    history_dir = project_dir / "qual" / "codebook_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(json.dumps(codebook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    history_path = _unique_history_path(history_dir)
    shutil.copyfile(path, history_path)
    return path


def validate_codebook(codebook: dict) -> list[str]:
    """Return validation errors. Empty list means valid."""
    errors: list[str] = []
    codebook_id = str(codebook.get("codebook_id", "")).strip()
    method = str(codebook.get("method", "")).strip()
    if not codebook_id:
        errors.append("codebook_id is required")
    if method not in ALLOWED_METHODS:
        errors.append("method must be one of ALLOWED_METHODS")

    if method == "frame_analysis":
        frame_elements = codebook.get("frame_elements")
        if not isinstance(frame_elements, list) or not frame_elements:
            errors.append("frame_analysis requires frame_elements")
        else:
            present = {str(item.get("element", "")).strip() for item in frame_elements if isinstance(item, dict)}
            missing = [element for element in FRAME_ELEMENTS if element not in present]
            if missing:
                errors.append(f"missing frame elements: {', '.join(missing)}")
            for element in frame_elements:
                if not isinstance(element, dict):
                    errors.append("each frame_element must be an object")
                    continue
                errors.extend(_validate_codes(element.get("codes", []), prefix=f"{element.get('element', '')}: "))
    else:
        codes = codebook.get("codes")
        if not isinstance(codes, list) or not codes:
            errors.append("codes must contain at least one code")
        else:
            errors.extend(_validate_codes(codes))
    return errors


def get_template(method: str) -> dict:
    """Return a starter codebook template for a qualitative method."""
    if method not in ALLOWED_METHODS:
        raise ValueError(f"Unknown qualitative method: {method}")
    if method == "frame_analysis":
        return {
            "codebook_id": "frame_analysis_v1",
            "method": method,
            "frame_elements": [
                {"element": element, "codes": [_example_code(element)]}
                for element in FRAME_ELEMENTS
            ],
            "notes": "",
        }
    examples = {
        "qualitative_content_analysis": _example_code("content_category"),
        "thematic_analysis": {**_example_code("theme"), "parent_code": None},
        "discourse_analysis": {**_example_code("discourse_element"), "discourse_element": "actor_positioning"},
        "place_discourse": {**_example_code("place_image"), "place_dimension": "local_identity"},
    }
    return {
        "codebook_id": f"{method}_v1",
        "method": method,
        "codes": [examples[method]],
        "notes": "",
    }


def codebook_history(project_dir: Path) -> list[dict]:
    """Return codebook history entries sorted newest first."""
    history_dir = project_dir / "qual" / "codebook_history"
    if not history_dir.exists():
        return []
    entries = []
    for path in sorted(history_dir.glob("codebook_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            saved_at = _saved_at_from_filename(path.name)
            entries.append(
                {
                    "filename": path.name,
                    "saved_at": saved_at,
                    "codebook_id": payload.get("codebook_id", ""),
                }
            )
        except Exception:
            continue
    return entries


def _validate_codes(codes: list, prefix: str = "") -> list[str]:
    errors: list[str] = []
    if not isinstance(codes, list) or not codes:
        return [f"{prefix}codes must contain at least one code"]
    seen = set()
    for item in codes:
        if not isinstance(item, dict):
            errors.append(f"{prefix}each code must be an object")
            continue
        code = str(item.get("code", "")).strip()
        label = str(item.get("label", "")).strip()
        definition = str(item.get("definition", "")).strip()
        if not code:
            errors.append(f"{prefix}code is required")
        if not label:
            errors.append(f"{prefix}label is required")
        if not definition:
            errors.append(f"{prefix}definition is required")
        if code in seen:
            errors.append(f"{prefix}duplicate code: {code}")
        seen.add(code)
    return errors


def _example_code(code: str) -> dict:
    return {
        "code": code,
        "label": code.replace("_", " ").title(),
        "definition": f"Texts related to {code.replace('_', ' ')}.",
        "include": [],
        "exclude": [],
    }


def _codebook_path(project_dir: Path) -> Path:
    return project_dir / "qual" / "codebook.json"


def _timestamp_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _unique_history_path(history_dir: Path) -> Path:
    stem = f"codebook_{_timestamp_for_filename()}"
    path = history_dir / f"{stem}.json"
    counter = 1
    while path.exists():
        path = history_dir / f"{stem}_{counter}.json"
        counter += 1
    return path


def _saved_at_from_filename(filename: str) -> str:
    raw = filename.removeprefix("codebook_").removesuffix(".json")
    try:
        return datetime.strptime(raw, "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return raw
