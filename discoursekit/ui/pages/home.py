"""Home page focused on researcher-friendly analysis setup."""

from __future__ import annotations

import json
import shutil
from datetime import date, timedelta

import streamlit as st

from discoursekit.ui.components import metric_row, page_header


ANALYSIS_OPTIONS = {
    "time_series": "보도량 추이",
    "publisher_dist": "언론사/출처 분포",
    "keyword_frequency": "키워드 빈도",
    "keyword_trends": "시기별 키워드 변화",
    "before_after": "사건 전후 비교",
    "qual_sample": "정성 분석 표본 추천",
}

ANALYSIS_HELP = {
    "time_series": "월별 기사 건수 추이를 꺾은선 차트로 확인합니다.",
    "publisher_dist": "어떤 언론사나 출처가 많이 보도했는지 분포를 봅니다.",
    "keyword_frequency": "기사 제목과 요약문에서 자주 등장하는 키워드를 추출합니다.",
    "keyword_trends": "특정 시점 전후로 키워드 순위가 어떻게 바뀌었는지 비교합니다.",
    "before_after": "사건일 또는 기준일 전후의 보도량과 키워드 차이를 비교합니다.",
    "qual_sample": "정성 분석을 위해 직접 읽고 코딩할 기사 표본을 추천합니다.",
}

SOURCE_LABELS = {
    "naver_news": "NAVER News",
    "bigkinds": "BIGKinds 파일",
    "csv": "CSV 업로드",
}


def render() -> None:
    page_header(
        "무엇을 분석하고 싶나요?",
        "분석 주제, 검색어, 기간, 자료원을 먼저 정하면 수집부터 기본 분석까지 이어집니다.",
    )
    _render_analysis_starter()
    st.markdown("---")
    _render_existing_projects()


def _render_analysis_starter() -> None:
    default_to = date.today()
    default_from = default_to - timedelta(days=365)

    projects = _list_projects()
    if not projects:
        st.markdown(
            """
### 처음 오셨나요?

DiscourseKit은 뉴스와 블로그성 자료를 수집하고, 정제하고, 분석 가능한 데이터로 만드는 연구용 워크벤치입니다.

**시작 방법**
1. 분석 주제와 검색어를 입력합니다.
2. 기간과 자료원을 선택합니다.
3. **수집 및 분석 시작**을 누르면 데이터 만들기 화면으로 이동합니다.

**준비물**
- NAVER News 자동 수집: [NAVER Developers](https://developers.naver.com)에서 검색 API Client ID/Secret 발급
- BIGKinds 전문 자료: [BIGKinds](https://www.bigkinds.or.kr)에서 검색 결과 XLSX 다운로드
"""
        )

    with st.form("analysis_starter_form"):
        research_topic = st.text_input(
            "분석 주제",
            placeholder="예: 이태원동 사건 이후 지역 담론 변화",
        )
        query = st.text_input(
            "검색 키워드 *",
            placeholder="예: 이태원동",
        )

        col1, col2 = st.columns(2)
        with col1:
            date_from = st.date_input("기간 시작", value=default_from)
        with col2:
            date_to = st.date_input("기간 종료", value=default_to)

        st.markdown("#### 자료원")
        selected_source_labels = st.multiselect(
            "자료원 선택 *",
            list(SOURCE_LABELS.values()),
            default=["NAVER News"],
            label_visibility="collapsed",
        )
        selected_sources = [
            key for key, label in SOURCE_LABELS.items() if label in selected_source_labels
        ]

        _render_source_guidance(selected_source_labels)

        st.markdown("#### 보고 싶은 기본 분석")
        cols = st.columns(2)
        selected_analyses: list[str] = []
        for i, (key, label) in enumerate(ANALYSIS_OPTIONS.items()):
            with cols[i % 2]:
                default_checked = key in {
                    "time_series",
                    "publisher_dist",
                    "keyword_frequency",
                    "keyword_trends",
                }
                if st.checkbox(
                    label,
                    value=default_checked,
                    key=f"analysis_{key}",
                    help=ANALYSIS_HELP.get(key, ""),
                ):
                    selected_analyses.append(key)

        cutoff_date = None
        if "before_after" in selected_analyses:
            cutoff_date = st.date_input(
                "비교 기준일",
                value=date_from,
                help="사건 발생일 또는 분석자가 전후를 나누고 싶은 기준일입니다.",
            )

        col_submit, col_advice = st.columns(2)
        with col_submit:
            submitted = st.form_submit_button("수집 및 분석 시작", type="primary")
        with col_advice:
            advice_requested = st.form_submit_button("LLM 검색안 생성")

    if advice_requested:
        if not query.strip() and not research_topic.strip():
            st.error("검색안을 만들려면 분석 주제나 검색 키워드를 입력하세요.")
        else:
            from discoursekit.llm.search_advisor import generate_search_advice

            api_key = _get_interactive_api_key()
            advice = generate_search_advice(research_topic.strip(), query.strip(), api_key=api_key)
            st.session_state["search_advice"] = advice
            st.session_state.setdefault("search_advice_history", []).append(advice)
            st.session_state["search_advice_round"] = len(st.session_state["search_advice_history"])

    _render_search_advice_panel()

    with st.expander("다른 자료원 안내", expanded=False):
        st.markdown(
            """
| 자료원 | 설명 | 링크 |
|--------|------|------|
| **BIGKinds** | 국내 종합 뉴스 DB. 기사 전문 XLSX 다운로드 가능 | [bigkinds.or.kr](https://www.bigkinds.or.kr) |
| **공공데이터포털** | 정부/공공기관 데이터와 보도자료성 자료 | [data.go.kr](https://www.data.go.kr) |
| **한국언론진흥재단** | 미디어 관련 조사와 통계 | [kpf.or.kr](https://www.kpf.or.kr) |
| **학술 DB** | RISS, KCI, DBpia 등 논문 검색 | [riss.kr](https://www.riss.kr) |

CSV로 정리하면 어떤 자료도 DiscourseKit으로 가져올 수 있습니다.
"""
        )

    if not submitted:
        return

    if not query.strip():
        st.error("검색 키워드를 입력하세요.")
        return
    if not selected_sources:
        st.error("자료원을 1개 이상 선택하세요.")
        return
    if date_from > date_to:
        st.error("기간 시작일은 종료일보다 늦을 수 없습니다.")
        return

    project = _create_project(research_topic.strip() or query.strip(), research_topic.strip())
    st.session_state["current_project_id"] = project.project_id
    st.session_state["current_project_name"] = project.name
    st.session_state["analysis_config"] = {
        "project_id": project.project_id,
        "research_topic": research_topic.strip(),
        "query": query.strip(),
        "date_from": str(date_from),
        "date_to": str(date_to),
        "sources": selected_sources,
        "analyses": selected_analyses,
        "cutoff_date": str(cutoff_date) if cutoff_date else None,
    }
    st.session_state["nav_page"] = "데이터 만들기"
    st.rerun()


def _render_source_guidance(selected_source_labels: list[str]) -> None:
    if "NAVER News" in selected_source_labels:
        st.info(
            "**NAVER News API**는 기사 제목과 요약문만 제공합니다.\n\n"
            "보도량 추이, 출처 분포, 키워드 빈도에는 적합합니다. "
            "기사 전문을 직접 읽는 정성 분석에는 BIGKinds 또는 CSV 전문 자료를 함께 쓰는 편이 좋습니다."
        )
    if "BIGKinds 파일" in selected_source_labels:
        st.info(
            "**BIGKinds**는 기사 전문이 포함된 XLSX 파일을 업로드하는 방식입니다.\n\n"
            "1. [bigkinds.or.kr](https://www.bigkinds.or.kr)에 접속\n"
            "2. 검색어와 기간을 설정해 검색\n"
            "3. 검색 결과에서 기사 분석 또는 원문 다운로드 메뉴 선택\n"
            "4. 다음 화면에서 내려받은 XLSX 파일 업로드"
        )
    if "CSV 업로드" in selected_source_labels:
        st.info(
            "**CSV 업로드**는 직접 준비한 데이터 파일을 사용합니다.\n\n"
            "필수 열: `date`, `title`, `body`\n\n"
            "선택 열: `publisher`, `keywords`, `url`\n\n"
            "인코딩은 UTF-8을 권장합니다."
        )


def _render_existing_projects() -> None:
    st.markdown("#### 기존 프로젝트")
    projects = _list_projects()
    if not projects:
        st.caption("아직 저장된 프로젝트가 없습니다. 위에서 검색어를 입력하고 분석을 시작하세요.")
        return

    for project in projects[:8]:
        stats = _load_project_stats(project["project_id"])
        meta = _load_project_meta(project["project_id"])

        with st.container():
            col_title, col_action = st.columns([3, 1])
            with col_title:
                st.markdown(f"**{project['name']}**")
                meta_parts = []
                if meta.get("created_at"):
                    meta_parts.append(f"생성: {meta['created_at'][:10]}")
                if meta.get("query"):
                    meta_parts.append(f"검색어: {meta['query']}")
                if meta.get("date_range"):
                    meta_parts.append(meta["date_range"])
                st.caption(" / ".join(meta_parts) if meta_parts else "수집 조건을 아직 확인할 수 없습니다.")
            with col_action:
                if st.button("선택", key=f"select_{project['project_id']}"):
                    st.session_state["current_project_id"] = project["project_id"]
                    st.session_state["current_project_name"] = project["name"]

            total = stats.get("total", 0)
            active = stats.get("active", 0)
            if total == 0:
                st.warning("아직 기사를 수집하지 않았습니다.")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("수집 시작하기", key=f"collect_{project['project_id']}"):
                        st.session_state["current_project_id"] = project["project_id"]
                        st.session_state["current_project_name"] = project["name"]
                        st.session_state["nav_page"] = "데이터 만들기"
                        st.rerun()
                with col2:
                    if st.button("빈 프로젝트 삭제", key=f"delete_{project['project_id']}"):
                        _delete_project(project["project_id"])
                        st.rerun()
            else:
                metric_row(
                    [
                        ("전체 기사", total, ""),
                        ("분석 가능", active, ""),
                        ("출처", stats.get("publishers", 0), ""),
                    ]
                )
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("분석 대시보드 열기", key=f"analyze_{project['project_id']}"):
                        st.session_state["current_project_id"] = project["project_id"]
                        st.session_state["current_project_name"] = project["name"]
                        st.session_state["nav_page"] = "분석 대시보드"
                        st.rerun()
                with col2:
                    if st.button("정성 분석 열기", key=f"qual_{project['project_id']}"):
                        st.session_state["current_project_id"] = project["project_id"]
                        st.session_state["current_project_name"] = project["name"]
                        st.session_state["nav_page"] = "정성 분석"
                        st.rerun()
            st.markdown("---")


def _create_project(name: str, description: str):
    from discoursekit.core.project import Project

    return Project.create(name=name, description=description)


def _list_projects() -> list[dict]:
    try:
        from discoursekit.core.project import Project

        return [
            {
                "project_id": p.project_id,
                "name": p.name,
                "created_at": p.created_at,
                "description": p.description,
            }
            for p in Project.list_all()
        ]
    except Exception:
        return []


def _load_project_stats(project_id: str) -> dict:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection

        db_path = get_projects_dir() / project_id / "project.db"
        if not db_path.exists():
            return {"total": 0, "active": 0, "artifacts": 0, "publishers": 0}
        conn = get_connection(db_path)
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE project_id=?",
            (project_id,),
        ).fetchone()["n"]
        active = conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE project_id=? AND is_active=1",
            (project_id,),
        ).fetchone()["n"]
        artifacts = conn.execute(
            "SELECT COUNT(*) AS n FROM artifacts WHERE project_id=?",
            (project_id,),
        ).fetchone()["n"]
        publishers = conn.execute(
            "SELECT COUNT(DISTINCT publisher) AS n FROM articles WHERE project_id=? AND is_active=1",
            (project_id,),
        ).fetchone()["n"]
        conn.close()
        return {"total": total, "active": active, "artifacts": artifacts, "publishers": publishers}
    except Exception:
        return {"total": 0, "active": 0, "artifacts": 0, "publishers": 0}


def _load_project_meta(project_id: str) -> dict:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection

        db_path = get_projects_dir() / project_id / "project.db"
        if not db_path.exists():
            return {}
        conn = get_connection(db_path)
        row = conn.execute(
            "SELECT created_at, description FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        dates = conn.execute(
            "SELECT MIN(date) AS d_min, MAX(date) AS d_max FROM articles WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        params_row = conn.execute(
            "SELECT params_json FROM ingest_runs WHERE project_id = ? ORDER BY started_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        conn.close()

        meta = {}
        if row:
            meta["created_at"] = row["created_at"] or ""
        if dates and dates["d_min"]:
            meta["date_range"] = f"{dates['d_min']} ~ {dates['d_max']}"
        if params_row and params_row["params_json"]:
            params = json.loads(params_row["params_json"])
            meta["query"] = params.get("query", "")
        return meta
    except Exception:
        return {}


def _delete_project(project_id: str) -> None:
    try:
        from discoursekit.config import get_projects_dir

        project_dir = get_projects_dir() / project_id
        if project_dir.exists():
            shutil.rmtree(project_dir)
        if st.session_state.get("current_project_id") == project_id:
            st.session_state["current_project_id"] = None
            st.session_state["current_project_name"] = ""
        st.success("빈 프로젝트를 삭제했습니다.")
    except Exception as exc:
        st.error(f"삭제 실패: {exc}")


def _render_search_advice_panel() -> None:
    advice = st.session_state.get("search_advice")
    if not advice:
        return
    with st.expander("LLM 제안: 검색안", expanded=True):
        st.caption("검색안은 제안입니다. 연구자가 선택하고 수정한 뒤 수집에 사용하세요.")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**핵심 검색어**")
            for item in advice.core_queries:
                st.markdown(f"- {item}")
            st.markdown("**확장 검색어**")
            for item in advice.expansion_queries:
                st.markdown(f"- {item}")
        with col2:
            st.markdown("**제외 추천 패턴**")
            for item in advice.exclude_patterns:
                st.markdown(f"- {item}")
            st.markdown("**기간/방법 제안**")
            st.write(advice.time_suggestion)
            st.write(advice.method_suggestion)
        st.info(advice.reasoning)

        feedback = st.text_input("수정 의견", key="search_advice_feedback")
        if st.button("수정 반영 요청"):
            from discoursekit.llm.search_advisor import revise_search_advice

            round_no = int(st.session_state.get("search_advice_round", 1)) + 1
            api_key = _get_interactive_api_key()
            revision = revise_search_advice(advice, feedback, revision_round=round_no, api_key=api_key)
            st.session_state["search_advice"] = revision.advice
            st.session_state["search_advice_round"] = revision.revision_round
            st.session_state.setdefault("search_advice_history", []).append(revision.advice)
            st.success(revision.revision_note)


def _get_interactive_api_key() -> str | None:
    """Return an API key from the interactive slot, or None."""
    try:
        from discoursekit.ui.env_keys import load_gemini_keys

        keys = load_gemini_keys()
        if not keys:
            return None
        from discoursekit.llm.slot_manager import GeminiProjectSlot, GeminiSlotManager

        manager = GeminiSlotManager()
        for idx, key in enumerate(sorted(keys.keys()), 1):
            manager.add_slot(GeminiProjectSlot(
                slot_name=f"slot_{idx}",
                api_key=keys[key],
                role="interactive" if idx == len(keys) else "general",
            ))
        slot = manager.get_next_available(role="interactive")
        return slot.api_key if slot else None
    except Exception:
        return None
