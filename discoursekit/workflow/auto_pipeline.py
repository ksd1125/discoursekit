"""Automatic collect -> clean -> overview workflow."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from discoursekit.clean.pipeline import run_clean_pipeline
from discoursekit.core.db import count_articles, get_connection
from discoursekit.ingest.base import BaseAdapter, IngestParams
from discoursekit.ingest.runner import run_ingest


@dataclass(frozen=True)
class SourceConfig:
    """Data source configuration for an automatic collection run."""

    source_type: str
    query: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    input_path: Path | None = None
    display: int = 100
    sort: str = "date"
    max_results: int = 1000
    client_id: str | None = None
    client_secret: str | None = None


@dataclass(frozen=True)
class CleanConfig:
    """Cleaning configuration for the automatic workflow."""

    min_body_chars: int = 20
    similarity_threshold: float = 0.85


@dataclass(frozen=True)
class WorkflowSummary:
    """Summary returned to UI after collection and cleaning."""

    project_id: str
    raw_count: int
    active_count: int
    dropped_count: int
    date_min: str
    date_max: str
    publisher_count: int
    keyword_top_n: list[tuple[str, int]]
    ingest_run_id: str
    clean_run_id: str
    source_type: str
    source_depth: str


def run_collect_clean_overview(
    project_id: str,
    source_config: SourceConfig,
    clean_config: CleanConfig,
    db_path: Path,
    progress_callback=None,
) -> WorkflowSummary:
    """Run collection, cleaning, and summary generation for one project."""
    adapter, source_depth = _adapter_for_source(source_config.source_type)
    params = IngestParams(
        project_id=project_id,
        source=source_config.source_type,
        input_path=source_config.input_path,
        query=source_config.query,
        date_from=source_config.date_from,
        date_to=source_config.date_to,
        display=source_config.display,
        sort=source_config.sort,
        max_results=source_config.max_results,
        client_id=source_config.client_id,
        client_secret=source_config.client_secret,
    )

    _notify(progress_callback, "수집 중...")
    ingest_run_id = run_ingest(adapter, params, db_path)

    clean_run_id = ""
    try:
        _notify(progress_callback, "정제 중...")
        clean_run_id = run_clean_pipeline(
            db_path,
            project_id,
            min_body_chars=clean_config.min_body_chars,
            similarity_threshold=clean_config.similarity_threshold,
        )
    except Exception:
        clean_run_id = ""

    _notify(progress_callback, "요약 생성 중...")
    return _compute_summary(
        db_path,
        project_id,
        ingest_run_id,
        clean_run_id,
        source_config.source_type,
        source_depth,
    )


def _adapter_for_source(source_type: str) -> tuple[BaseAdapter, str]:
    if source_type == "naver_news":
        from discoursekit.ingest.naver_news import NaverNewsAdapter

        return NaverNewsAdapter(), "excerpt_only"
    if source_type == "naver_blog":
        from discoursekit.ingest.naver_blog import NaverBlogAdapter

        return NaverBlogAdapter(), "excerpt_only"
    if source_type == "naver_cafe":
        from discoursekit.ingest.naver_cafe import NaverCafeAdapter

        return NaverCafeAdapter(), "excerpt_only"
    if source_type == "naver_web":
        from discoursekit.ingest.naver_web import NaverWebAdapter

        return NaverWebAdapter(), "excerpt_only"
    if source_type == "bigkinds":
        from discoursekit.ingest.bigkinds import BigKindsAdapter

        return BigKindsAdapter(), "full_body"
    if source_type == "csv":
        from discoursekit.ingest.csv_generic import CsvGenericAdapter

        return CsvGenericAdapter(), "full_body"
    raise ValueError(f"Unknown source_type: {source_type}")


def _compute_summary(
    db_path: Path,
    project_id: str,
    ingest_run_id: str,
    clean_run_id: str,
    source_type: str,
    source_depth: str,
) -> WorkflowSummary:
    """Compute UI-ready summary fields from the project database."""
    conn = get_connection(db_path)
    try:
        raw_count = count_articles(conn, project_id, active_only=False)
        active_count = count_articles(conn, project_id, active_only=True)
        date_row = conn.execute(
            """
            SELECT MIN(date) AS d_min, MAX(date) AS d_max
            FROM articles
            WHERE project_id = ? AND is_active = 1
            """,
            (project_id,),
        ).fetchone()
        pub_row = conn.execute(
            """
            SELECT COUNT(DISTINCT publisher) AS n
            FROM articles
            WHERE project_id = ? AND is_active = 1 AND publisher IS NOT NULL AND publisher != ''
            """,
            (project_id,),
        ).fetchone()
        return WorkflowSummary(
            project_id=project_id,
            raw_count=raw_count,
            active_count=active_count,
            dropped_count=raw_count - active_count,
            date_min=date_row["d_min"] or "",
            date_max=date_row["d_max"] or "",
            publisher_count=int(pub_row["n"] or 0),
            keyword_top_n=_title_keyword_top_n(conn, project_id, n=20),
            ingest_run_id=ingest_run_id,
            clean_run_id=clean_run_id,
            source_type=source_type,
            source_depth=source_depth,
        )
    finally:
        conn.close()


def _title_keyword_top_n(conn, project_id: str, n: int = 20) -> list[tuple[str, int]]:
    """Return simple title-token frequencies for MVP overview cards."""
    rows = conn.execute(
        """
        SELECT title
        FROM articles
        WHERE project_id = ? AND is_active = 1
        """,
        (project_id,),
    ).fetchall()
    stopwords = {
        "그리고",
        "그러나",
        "대한",
        "관련",
        "기자",
        "뉴스",
        "오늘",
        "이번",
        "지난",
        "위해",
    }
    counter: Counter[str] = Counter()
    for row in rows:
        for token in (row["title"] or "").split():
            cleaned = token.strip(".,!?()\"'·“”[]{}<>:;")
            if len(cleaned) >= 2 and cleaned not in stopwords:
                counter[cleaned] += 1
    return counter.most_common(n)


def _notify(callback, message: str) -> None:
    if callback is not None:
        callback(message)
