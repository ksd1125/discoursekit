# DiscourseKit

> Academic-grade discourse analysis toolkit for news, blogs, and public data.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-63%20passed-brightgreen)]()

## What is DiscourseKit?

DiscourseKit is an open-source research workbench that takes you from raw data collection to publication-ready discourse analysis. It supports:

- **Multi-source ingestion**: BIGKinds XLSX, CSV (NAVER API planned for v0.2)
- **Automated cleaning**: deduplication (exact + fuzzy trigram), short-text filtering, HTML normalization
- **LLM classification**: Gemini API with 3-slot rotation, resume support, rate limiting
- **Statistical analysis**: descriptive stats, time series, Cohen's kappa agreement
- **Safe export**: `body_internal` never leaves the project; only `body_excerpt` (200 chars) is exported
- **Reproducibility**: SHA-256 tracking, prompt versioning, methodology report generation
- **Streamlit UI**: full pipeline interface with project management

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Verify
python -m discoursekit --version
pytest tests/

# Launch UI
streamlit run discoursekit/ui/app.py
```

## Architecture

```
discoursekit/
├── config.py          # Paths, env vars
├── core/              # DB schema (9 tables), Project model
├── ingest/            # BIGKinds, CSV adapters (extensible)
├── clean/             # Text normalization, dedup, filters
├── llm/               # Slot manager, classifier, rate limiter
├── analyze/           # Descriptive, time series, agreement, export
├── report/            # Methodology report generator
├── handoff/           # Portable project export/import
└── ui/                # Streamlit interface (6 pages)
```

## Pipeline

| Step | Module | Description |
|:---:|--------|-------------|
| 1 | `ingest` | Collect articles from BIGKinds XLSX or CSV files |
| 2 | `clean` | Deduplicate, filter, normalize, split body fields |
| 3 | `llm` | Classify articles via Gemini API (resume-safe) |
| 4 | `analyze` | Statistics, charts, agreement metrics, safe export |

## Key Design Decisions

- **SQLite** (raw `sqlite3`, no ORM) — 9-table schema, portable per-project DB
- **body_internal vs body_excerpt** — full text stays internal; only 200-char excerpts are exported
- **Gemini "project slots"** — 3 independent GCP projects with separate RPM/TPM/RPD quotas
- **Resume via UNIQUE constraint** — `(job_id, article_id)` prevents duplicate classification
- **Handoff** — ingest-only zip export for multi-PC workflows

## Configuration

Set environment variables or create a `.env` file:

```bash
DISCOURSEKIT_DATA_DIR=/path/to/data    # Default: ~/discoursekit_data
GEMINI_KEY_1=AIzaSy...
GEMINI_KEY_2=AIzaSy...
GEMINI_KEY_3=AIzaSy...
```

## Development

```bash
# Run tests
pytest tests/ -v

# Lint
ruff check discoursekit/

# Format
black discoursekit/ tests/
```

## License

MIT. See [LICENSE](LICENSE).

---

[한국어 README](README.ko.md)
