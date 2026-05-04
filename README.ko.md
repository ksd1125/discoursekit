# DiscourseKit

> 뉴스·블로그·공공데이터 기반 학술 담론 분석 도구

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-63%20passed-brightgreen)]()

## DiscourseKit이란?

DiscourseKit은 원시 데이터 수집부터 학술 논문 수준의 담론 분석까지 지원하는 오픈소스 연구 워크벤치입니다.

- **다중 수집원**: BIGKinds XLSX, CSV (NAVER API v0.2 예정)
- **자동 정제**: 중복 제거(정확+퍼지 trigram), 단문 필터, HTML 정규화
- **LLM 분류**: Gemini API 3-슬롯 rotation, resume 지원, rate limiting
- **통계 분석**: 기술통계, 시계열, Cohen's kappa 일치율
- **안전 Export**: `body_internal`은 절대 외부로 나가지 않음 (200자 excerpt만 export)
- **재현성**: SHA-256 추적, 프롬프트 버전 관리, 방법론 보고서 자동 생성
- **Streamlit UI**: 프로젝트 관리 + 전체 파이프라인 인터페이스

## 빠른 시작

```bash
# 설치
pip install -e ".[dev]"

# 검증
python -m discoursekit --version
pytest tests/

# UI 실행
streamlit run discoursekit/ui/app.py
```

## 파이프라인

| 단계 | 모듈 | 설명 |
|:---:|--------|------|
| 1 | `ingest` | BIGKinds XLSX 또는 CSV에서 기사 수집 |
| 2 | `clean` | 중복 제거, 필터링, 정규화, body 분리 |
| 3 | `llm` | Gemini API로 기사 자동 분류 (resume 안전) |
| 4 | `analyze` | 통계, 차트, 일치율, 안전 export |

## 핵심 설계

- **SQLite** (raw sqlite3, ORM 없음) — 9-테이블 스키마, 프로젝트별 독립 DB
- **body_internal vs body_excerpt** — 전문은 내부용, export에는 200자 요약만
- **Gemini 프로젝트 슬롯** — 3개 GCP 프로젝트에서 독립 RPM/TPM/RPD quota
- **Resume** — `UNIQUE(job_id, article_id)` 제약으로 중복 분류 방지
- **Handoff** — ingest-only zip으로 다른 PC에서 이어서 분석

## 설정

환경변수 또는 `.env` 파일:

```bash
DISCOURSEKIT_DATA_DIR=/path/to/data    # 기본: ~/discoursekit_data
GEMINI_KEY_1=AIzaSy...
GEMINI_KEY_2=AIzaSy...
GEMINI_KEY_3=AIzaSy...
```

## 개발

```bash
pytest tests/ -v
ruff check discoursekit/
black discoursekit/ tests/
```

## 라이선스

MIT. [LICENSE](LICENSE) 참조.

---

[English README](README.md)
