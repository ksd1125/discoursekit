"""Generic CSV adapter with flexible column mapping."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from discoursekit.config import BODY_EXCERPT_MAX_LEN
from discoursekit.core.article import Article
from discoursekit.ingest.base import BaseAdapter, IngestParams, generate_article_id, make_excerpt


DEFAULT_CSV_COLUMN_MAP: dict[str, str] = {
    "date": "date",
    "title": "title",
    "body": "body",
    "publisher": "publisher",
    "keywords": "keywords",
    "url": "url",
}


def _detect_encoding(path: Path) -> str:
    """Detect common text encodings by BOM."""
    raw = path.read_bytes()[:4]
    if raw[:2] == b"\xff\xfe":
        return "utf-16-le"
    if raw[:2] == b"\xfe\xff":
        return "utf-16-be"
    if raw[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    return "utf-8"


class CsvGenericAdapter(BaseAdapter):
    """Adapter for user-supplied CSV files."""

    def __init__(self, column_map: dict[str, str] | None = None):
        self.column_map = column_map or DEFAULT_CSV_COLUMN_MAP

    @property
    def source_name(self) -> str:
        return "csv"

    def ingest(self, params: IngestParams) -> Iterator[Article]:
        """Yield Article objects from one CSV file or a directory."""
        if params.input_path is None:
            raise ValueError("input_path is required for CsvGenericAdapter")

        path = Path(params.input_path)
        if path.is_file():
            yield from self._read_csv(path, params)
        elif path.is_dir():
            for csv_path in sorted(path.glob("*.csv")):
                yield from self._read_csv(csv_path, params)
        else:
            raise FileNotFoundError(f"Input not found: {path}")

    def _read_csv(self, csv_path: Path, params: IngestParams) -> Iterator[Article]:
        """Read one CSV file."""
        encoding = _detect_encoding(csv_path)
        now = datetime.now(timezone.utc).isoformat()

        with open(csv_path, "r", encoding=encoding, newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames is None:
                return

            for row in reader:
                title = self._get_mapped(row, "title")
                if not title:
                    continue

                date = self._get_mapped(row, "date", "")
                if params.date_from and date and date < params.date_from:
                    continue
                if params.date_to and date and date > params.date_to:
                    continue

                publisher = self._get_mapped(row, "publisher", "")
                body = self._get_mapped(row, "body", "")
                keywords_raw = self._get_mapped(row, "keywords", "")
                keywords = (
                    [keyword.strip() for keyword in keywords_raw.split(",") if keyword.strip()]
                    if keywords_raw
                    else []
                )
                unique_key = f"{title}|{date}|{publisher}"

                yield Article(
                    article_id=generate_article_id("csv", unique_key),
                    source="csv",
                    date=date,
                    publisher=publisher,
                    title=title,
                    body_internal=body,
                    body_excerpt=make_excerpt(body, BODY_EXCERPT_MAX_LEN),
                    keywords=keywords,
                    url=self._get_mapped(row, "url", ""),
                    raw=dict(row),
                    cleaned_at=now,
                    project_id=params.project_id,
                )

    def _get_mapped(self, row: dict, field: str, default: str = "") -> str:
        """Get a value from row using the configured column mapping."""
        csv_col = self.column_map.get(field, field)
        value = row.get(csv_col)
        if value is None:
            value = row.get(field)
        return str(value).strip() if value else default
