"""Generate self-contained methodology reports from analysis bundles."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

from discoursekit.analyze.runner import AnalysisBundle


def generate_methodology_report(
    bundle: AnalysisBundle,
    project_name: str,
    output_path: Path,
    job_id: str | None = None,
) -> Path:
    """Generate ``methodology_report.html`` without exposing internal article bodies."""
    generated_at = datetime.now(timezone.utc).isoformat()
    safe_project_name = html.escape(project_name)
    desc = bundle.descriptive
    sections = [
        _overview_section(bundle, safe_project_name, job_id),
        _publisher_section(desc.publisher_counts),
        _time_series_section(bundle),
        _keyword_section(desc.keyword_top_n),
        _agreement_section(bundle),
    ]
    body = "\n".join(section for section in sections if section)
    document = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>Methodology Report - {safe_project_name}</title>
  <style>
    body {{ color: #222; font-family: Arial, 'Noto Sans KR', sans-serif; line-height: 1.55; margin: 32px auto; max-width: 960px; padding: 0 20px; }}
    table {{ border-collapse: collapse; margin: 14px 0 28px; width: 100%; }}
    th, td {{ border: 1px solid #d8dee4; padding: 8px 10px; text-align: left; }}
    th {{ background: #f6f8fa; }}
    h1, h2 {{ line-height: 1.25; }}
    .meta {{ color: #667085; font-size: 13px; }}
  </style>
</head>
<body>
  <h1>Methodology Report</h1>
  <p class="meta">Project: {safe_project_name} | Generated: {generated_at} | DiscourseKit v0.1.0</p>
  {body}
  <footer><p class="meta">Generated from safe analysis tables and article excerpts only.</p></footer>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path


def _overview_section(bundle: AnalysisBundle, project_name: str, job_id: str | None) -> str:
    desc = bundle.descriptive
    job_row = f"<tr><td>LLM job</td><td>{html.escape(job_id)}</td></tr>" if job_id else ""
    sources = ", ".join(html.escape(source) for source in desc.source_counts) or "n/a"
    return f"""
<section>
  <h2>1. Data Overview</h2>
  <table>
    <tr><td>Project</td><td>{project_name}</td></tr>
    <tr><td>Total articles</td><td>{desc.total_articles:,}</td></tr>
    <tr><td>Active articles</td><td>{desc.active_articles:,}</td></tr>
    <tr><td>Date range</td><td>{html.escape(desc.date_min)} ~ {html.escape(desc.date_max)}</td></tr>
    <tr><td>Sources</td><td>{sources}</td></tr>
    <tr><td>Publishers</td><td>{len(desc.publisher_counts):,}</td></tr>
    {job_row}
  </table>
</section>
"""


def _publisher_section(publisher_counts: dict[str, int]) -> str:
    if not publisher_counts:
        return ""
    rows = "\n".join(
        f"<tr><td>{html.escape(publisher)}</td><td>{count:,}</td></tr>"
        for publisher, count in sorted(publisher_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
    )
    return f"""
<section>
  <h2>2. Publisher Distribution</h2>
  <table><tr><th>Publisher</th><th>Count</th></tr>{rows}</table>
</section>
"""


def _time_series_section(bundle: AnalysisBundle) -> str:
    if not bundle.monthly.periods:
        return ""
    rows = "\n".join(
        f"<tr><td>{html.escape(period)}</td><td>{count:,}</td></tr>"
        for period, count in zip(bundle.monthly.periods, bundle.monthly.total_counts)
    )
    return f"""
<section>
  <h2>3. Monthly Article Counts</h2>
  <table><tr><th>Month</th><th>Count</th></tr>{rows}</table>
</section>
"""


def _keyword_section(keywords: list[tuple[str, int]]) -> str:
    if not keywords:
        return ""
    rows = "\n".join(
        f"<tr><td>{html.escape(keyword)}</td><td>{count:,}</td></tr>"
        for keyword, count in keywords[:30]
    )
    return f"""
<section>
  <h2>4. Top Keywords</h2>
  <table><tr><th>Keyword</th><th>Count</th></tr>{rows}</table>
</section>
"""


def _agreement_section(bundle: AnalysisBundle) -> str:
    if bundle.agreement is None:
        return ""
    agreement = bundle.agreement
    return f"""
<section>
  <h2>5. Inter-rater Agreement</h2>
  <table>
    <tr><td>Samples</td><td>{agreement.n_samples:,}</td></tr>
    <tr><td>Accuracy</td><td>{agreement.accuracy:.4f}</td></tr>
    <tr><td>Cohen's Kappa</td><td>{agreement.cohens_kappa:.4f}</td></tr>
  </table>
</section>
"""

