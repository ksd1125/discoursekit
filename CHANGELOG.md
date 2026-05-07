# Changelog

All notable changes will be documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

## [0.3.0] - 2026-05-07

### Added — Phase 2: 업소·메뉴 관측 패널
- `place_reviews` table: raw review storage (review_id, place_id, place_name, review_month, menu_item, voted_keywords)
- `monthly_place_menu_observations` table: aggregated observations (first_seen_flag, continued_flag, normalized_menu_name)
- `discoursekit/ingest/naver_place.py`: NAVER Place GraphQL review crawler (sync, adaptive pacing)
- `discoursekit/analyze/place_menu.py`: menu name normalization (price/option/size removal), observation aggregation, first_seen_by_channel diffusion analysis
- Analyze dashboard: new "업소·메뉴" tab with place summary, menu summary, and diffusion tracking
- Data build page: Place review collection UI with place_id input and progress tracking
- `migrate_schema()` extended to auto-create new tables on existing DBs
- 22 new tests (schema migration, DB ops, menu normalization, observation aggregation, adapter)

### Changed — Collection policy
- `data_build.py`: removed max_results slider, hardcoded to 1000 (user policy: collection count is always max)

## [0.2.0] - 2026-05-06

### Added — Phase 0 + Phase 1: 상권 분류 + 채널 확장
- Taxonomy: 18 commercial-district rules across 8 categories (메뉴/상품, 업소/브랜드, 방문/경험, etc.)
- `articles.collection_method`, `articles.source_limit` columns with migration
- NAVER Blog, Cafe, Web adapters via shared `naver_search_ingest()`
- Channel selection checkboxes in data build UI
- Auto-compute network analysis on tab open
- Dynamic flow hint values (top keyword, peak period)
- Channel comparison display when multiple sources collected

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
