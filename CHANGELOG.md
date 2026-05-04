# Changelog

All notable changes will be documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

## [0.1.0] - 2026-05-04

### Added
- Backend skeleton: 9-table SQLite schema, core domain models
- `config.py`: path management, BOM-safe .env loader, sha256 utilities
- Ingest layer: BIGKinds XLSX adapter, generic CSV adapter, ingest runner, handoff export
- Clean layer: text normalization, dedup (exact + fuzzy trigram), filters, pipeline
- LLM layer: Gemini 3-slot manager, RPM/TPM/RPD rate limiter, classifier with resume
- Analyze layer: descriptive stats, time series, cross-tab, agreement (Cohen's kappa), safe export, methodology report
- Handoff: ingest-only zip export/import for multi-PC workflows
- Streamlit UI: 6 pages (Home, Ingest, Clean, LLM, Analyze, Settings)
- UI-backend wiring: LLM classification, export, handoff, API key .env persistence
- 63 tests covering all modules
