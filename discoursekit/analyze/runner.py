"""Analysis runner that orchestrates descriptive, trend, crosstab, and exports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from discoursekit.analyze.agreement import AgreementResult
from discoursekit.analyze.cross_tab import (
    CrossTabResult,
    cross_tab_label_month,
    cross_tab_label_publisher,
)
from discoursekit.analyze.descriptive import DescriptiveStats, compute_descriptive
from discoursekit.analyze.export import export_articles_parquet, export_results_csv
from discoursekit.analyze.time_series import TimeSeriesData, compute_monthly, compute_weekly


@dataclass(frozen=True)
class AnalysisBundle:
    """Complete analysis output for a project."""

    descriptive: DescriptiveStats
    monthly: TimeSeriesData
    weekly: TimeSeriesData
    cross_tab_publisher: CrossTabResult | None = None
    cross_tab_month: CrossTabResult | None = None
    agreement: AgreementResult | None = None


def run_full_analysis(
    db_path: Path,
    project_id: str,
    job_id: str | None = None,
    output_dir: Path | None = None,
) -> AnalysisBundle:
    """Run all analyses that are possible with the supplied project/job context."""
    descriptive = compute_descriptive(db_path, project_id)
    monthly = compute_monthly(db_path, project_id, job_id)
    weekly = compute_weekly(db_path, project_id)

    cross_tab_publisher = None
    cross_tab_month = None
    if job_id:
        cross_tab_publisher = cross_tab_label_publisher(db_path, project_id, job_id)
        cross_tab_month = cross_tab_label_month(db_path, project_id, job_id)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        export_articles_parquet(db_path, project_id, output_dir / "articles.parquet")
        if job_id:
            export_results_csv(db_path, project_id, job_id, output_dir / "results.csv")

    return AnalysisBundle(
        descriptive=descriptive,
        monthly=monthly,
        weekly=weekly,
        cross_tab_publisher=cross_tab_publisher,
        cross_tab_month=cross_tab_month,
    )

