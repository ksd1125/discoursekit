"""Time-series aggregations and optional Plotly figures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from discoursekit.core.db import get_connection


@dataclass(frozen=True)
class TimeSeriesData:
    """Monthly or weekly article counts plus optional label breakdown."""

    period_type: str
    periods: list[str]
    total_counts: list[int]
    label_counts: dict[str, list[int]]


def compute_monthly(db_path: Path, project_id: str, job_id: str | None = None) -> TimeSeriesData:
    """Aggregate active article counts by calendar month."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT SUBSTR(date, 1, 7) AS period, COUNT(*) AS n
            FROM articles
            WHERE project_id = ? AND is_active = 1
            GROUP BY period
            ORDER BY period
            """,
            (project_id,),
        ).fetchall()
        periods = [row["period"] for row in rows]
        total_counts = [int(row["n"]) for row in rows]
        label_counts = _label_counts_by_period(conn, periods, job_id, "%Y-%m") if job_id else {}
    finally:
        conn.close()

    return TimeSeriesData("monthly", periods, total_counts, label_counts)


def compute_weekly(db_path: Path, project_id: str) -> TimeSeriesData:
    """Aggregate active article counts by SQLite week number."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT SUBSTR(date, 1, 4) || '-W' ||
                   PRINTF('%02d', CAST(STRFTIME('%W', date) AS INTEGER)) AS period,
                   COUNT(*) AS n
            FROM articles
            WHERE project_id = ? AND is_active = 1
            GROUP BY period
            ORDER BY period
            """,
            (project_id,),
        ).fetchall()
    finally:
        conn.close()

    return TimeSeriesData(
        "weekly",
        [row["period"] for row in rows],
        [int(row["n"]) for row in rows],
        {},
    )


def make_total_count_figure(data: TimeSeriesData):
    """Return a Plotly bar figure when Plotly is installed, otherwise a dict."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        return {
            "type": "bar",
            "period_type": data.period_type,
            "x": data.periods,
            "y": data.total_counts,
        }

    fig = go.Figure()
    fig.add_bar(x=data.periods, y=data.total_counts, name="Articles")
    fig.update_layout(
        title=f"{data.period_type.title()} Article Counts",
        xaxis_title="Period",
        yaxis_title="Articles",
        template="plotly_white",
    )
    return fig


def _label_counts_by_period(conn, periods: list[str], job_id: str, fmt: str) -> dict[str, list[int]]:
    if fmt != "%Y-%m":
        raise ValueError(f"Unsupported period format: {fmt}")
    index = {period: idx for idx, period in enumerate(periods)}
    label_counts: dict[str, list[int]] = {}
    rows = conn.execute(
        """
        SELECT SUBSTR(a.date, 1, 7) AS period,
               COALESCE(NULLIF(r.label, ''), 'unknown') AS label,
               COUNT(*) AS n
        FROM llm_results r
        JOIN articles a ON r.article_id = a.article_id
        WHERE r.job_id = ? AND a.is_active = 1
        GROUP BY period, label
        ORDER BY period, label
        """,
        (job_id,),
    ).fetchall()
    for row in rows:
        period = row["period"]
        if period not in index:
            continue
        label = row["label"]
        label_counts.setdefault(label, [0] * len(periods))[index[period]] = int(row["n"])
    return label_counts

