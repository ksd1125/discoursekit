"""BIGKinds XLSX adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import openpyxl

from discoursekit.config import BODY_EXCERPT_MAX_LEN
from discoursekit.core.article import Article
from discoursekit.ingest.base import BaseAdapter, IngestParams, generate_article_id, make_excerpt


BIGKINDS_COLUMN_MAP: dict[str, str] = {
    "뉴스 식별자": "news_id",
    "일자": "date",
    "언론사": "publisher",
    "제목": "title",
    "본문": "body",
    "키워드": "keywords",
    "URL": "url",
    "통합 분류1": "category1",
    "통합 분류2": "category2",
    "통합 분류3": "category3",
    "사건/사고 분류1": "event_category",
}


def _normalize_date(raw_date: str | int | float) -> str:
    """Normalize BIGKinds date format to YYYY-MM-DD."""
    if isinstance(raw_date, (int, float)):
        text = str(int(raw_date))
    else:
        text = str(raw_date).strip()
    text = text.replace("-", "").replace("/", "").replace(".", "")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return str(raw_date).strip()


def _parse_keywords(raw: str | None) -> list[str]:
    """Parse comma-separated BIGKinds keywords."""
    if not raw:
        return []
    return [keyword.strip() for keyword in str(raw).split(",") if keyword.strip()]


class BigKindsAdapter(BaseAdapter):
    """Adapter for BIGKinds XLSX exports."""

    @property
    def source_name(self) -> str:
        return "bigkinds"

    def ingest(self, params: IngestParams) -> Iterator[Article]:
        """Yield Article objects from one BIGKinds XLSX file or a directory."""
        if params.input_path is None:
            raise ValueError("input_path is required for BigKindsAdapter")

        path = Path(params.input_path)
        if path.is_file():
            yield from self._read_xlsx(path, params)
        elif path.is_dir():
            for xlsx_path in sorted(path.glob("*.xlsx")):
                yield from self._read_xlsx(xlsx_path, params)
        else:
            raise FileNotFoundError(f"Input not found: {path}")

    def _read_xlsx(self, xlsx_path: Path, params: IngestParams) -> Iterator[Article]:
        """Read a single XLSX file and yield Articles."""
        workbook = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
        try:
            worksheet = workbook.active
            rows_iter = worksheet.iter_rows(values_only=True)
            header_row = next(rows_iter, None)
            if header_row is None:
                return
            header = [str(value).strip() if value is not None else "" for value in header_row]

            col_idx: dict[str, int] = {}
            for index, heading in enumerate(header):
                if heading in BIGKINDS_COLUMN_MAP:
                    col_idx[BIGKINDS_COLUMN_MAP[heading]] = index

            now = datetime.now(timezone.utc).isoformat()

            for row in rows_iter:
                if not row or all(cell is None for cell in row):
                    continue

                def get(field: str, default: str = "") -> str:
                    idx = col_idx.get(field)
                    if idx is None or idx >= len(row):
                        return default
                    value = row[idx]
                    return str(value).strip() if value is not None else default

                title = get("title")
                if not title:
                    continue

                date_raw = get("date")
                date = _normalize_date(date_raw) if date_raw else ""
                if params.date_from and date < params.date_from:
                    continue
                if params.date_to and date > params.date_to:
                    continue

                publisher = get("publisher")
                body = get("body")
                keywords = _parse_keywords(get("keywords"))
                unique_key = f"{title}|{date}|{publisher}"
                raw_dict = {
                    heading: str(row[index]) if row[index] is not None else None
                    for index, heading in enumerate(header)
                    if index < len(row)
                }

                yield Article(
                    article_id=generate_article_id("bigkinds", unique_key),
                    source="bigkinds",
                    date=date,
                    publisher=publisher,
                    title=title,
                    body_internal=body,
                    body_excerpt=make_excerpt(body, BODY_EXCERPT_MAX_LEN),
                    keywords=keywords,
                    url=get("url"),
                    raw=raw_dict,
                    cleaned_at=now,
                    project_id=params.project_id,
                )
        finally:
            workbook.close()
