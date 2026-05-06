"""LLM enrichment page."""

from __future__ import annotations

import streamlit as st

from discoursekit.ui.components import empty_state, metric_row, page_header


DEFAULT_OPTIONS = [
    "relevance",
    "quality_flags",
    "semantic_tags",
    "canonical_entities",
]


def render() -> None:
    page_header(
        "LLM 보정",
        "LLM으로 관련성 후보, 품질 플래그, 의미 태그, 표준화 후보를 만들고 사람이 검토합니다.",
    )
    project_id = st.session_state.get("current_project_id")
    if not project_id:
        empty_state("먼저 프로젝트를 선택하세요.")
        return

    stats = _load_stats(project_id)
    metric_row(
        [
            ("정제 후 기사", stats["active"], ""),
            ("LLM 보정 후보", stats["llm_results"], ""),
            ("검토 필요", stats["needs_review"], ""),
        ]
    )
    if stats["llm_results"] == 0:
        st.info(
            "LLM 보정은 선택 단계입니다. 기사 관련성 후보, 품질 플래그, 의미 태그, 표준화 후보를 "
            "LLM이 제안하고 연구자가 검토합니다.\n\n"
            "**시작하려면** 아래에서 표본 크기와 옵션을 정한 뒤 `표본 보정 실행`을 누르세요.\n\n"
            "**필요한 것** Gemini API key. 설정 화면의 Gemini Slot에 저장할 수 있습니다."
        )
    else:
        st.info("LLM 결과는 최종 분석 결론이 아니라 검토가 필요한 보정 후보입니다.")

    tab_options, tab_sample, tab_audit = st.tabs(["보정 옵션", "표본 실행", "감사 정보"])
    with tab_options:
        _render_options()
    with tab_sample:
        _render_sample_run(project_id)
    with tab_audit:
        _render_audit_requirements()


def _render_options() -> None:
    st.markdown("#### 보정할 항목")
    col1, col2 = st.columns(2)
    selected: list[str] = []
    with col1:
        if st.checkbox("관련성 후보 점검", value=True, help="검색어와 연구 주제에 직접 관련되는지 제안합니다."):
            selected.append("relevance")
        if st.checkbox("품질 플래그", value=True, help="광고성, 중복 의심, 너무 짧은 글 같은 검토 대상을 표시합니다."):
            selected.append("quality_flags")
        if st.checkbox("의미 태그 후보", value=True, help="안전, 경제, 관광, 정책 등 연구자가 검토할 의미 태그 후보입니다."):
            selected.append("semantic_tags")
    with col2:
        if st.checkbox("장소/기관/사건명 표준화 후보", value=True, help="표기가 흔들리는 이름을 같은 이름으로 묶기 위한 후보입니다."):
            selected.append("canonical_entities")
        if st.checkbox("근거 문장 후보 추출", value=False, help="요약문 안에서 판단 근거로 보이는 문장을 후보로 뽑습니다."):
            selected.append("evidence_sentences")
        if st.checkbox("유사 중복 후보 탐지", value=False, help="사람이 추가로 확인할 중복 의심 기사를 찾습니다."):
            selected.append("duplicate_review")
    st.session_state["llm_enrichment_options"] = selected or DEFAULT_OPTIONS
    st.caption("v0.1은 sample-first 방식입니다. 표본 보정 결과를 검토한 뒤 전체 실행으로 확장합니다.")


def _render_sample_run(project_id: str) -> None:
    sample_size = st.number_input("표본 크기", min_value=5, max_value=100, value=30, step=5)
    sample_strategy = st.selectbox(
        "표본 전략",
        ["random", "recent", "stratified"],
        format_func={
            "random": "무작위",
            "recent": "최신순",
            "stratified": "출처/시기 층화",
        }.get,
    )
    model = st.text_input("모델", value="gemini-2.5-flash")
    temperature = st.slider(
        "Temperature",
        0.0,
        1.0,
        0.0,
        0.1,
        help="0에 가까울수록 응답이 더 일관적입니다. 보정 작업은 보통 0을 권장합니다.",
    )

    analysis_config = st.session_state.get("analysis_config", {})
    research_topic = st.text_input(
        "연구 주제",
        value=analysis_config.get("research_topic", ""),
        placeholder="예: 이태원동 사건 이후 지역 담론 변화",
    )
    query = st.text_input(
        "검색 키워드",
        value=analysis_config.get("query", ""),
        placeholder="예: 이태원동",
    )
    semantic_tags = st.text_input(
        "허용 의미 태그",
        value="safety,economy,tourism,policy,responsibility,memorial,local_place,recovery,culture,media_criticism,resident,other",
    )

    if not st.button("표본 보정 실행", type="primary"):
        return

    from discoursekit.config import get_projects_dir
    from discoursekit.llm.enrichment import EnrichmentConfig, run_sample_enrichment
    from discoursekit.ui.env_keys import load_gemini_keys

    gemini_keys = load_gemini_keys()
    api_keys = [{"api_key": key} for _, key in sorted(gemini_keys.items()) if key]
    if not api_keys:
        st.error("Gemini API key가 없습니다. 설정 화면에서 Gemini Slot을 먼저 저장하세요.")
        if st.button("설정으로 이동", key="go_settings_gemini"):
            st.session_state["nav_page"] = "설정"
            st.rerun()
        return

    config = EnrichmentConfig(
        project_id=project_id,
        sample_size=int(sample_size),
        sample_strategy=sample_strategy,
        options=st.session_state.get("llm_enrichment_options", DEFAULT_OPTIONS),
        provider="gemini",
        model=model,
        temperature=float(temperature),
        research_topic=research_topic,
        query=query,
        semantic_tag_list=[tag.strip() for tag in semantic_tags.split(",") if tag.strip()],
        date_from=analysis_config.get("date_from"),
        date_to=analysis_config.get("date_to"),
    )

    with st.spinner("표본 보정을 실행 중입니다."):
        try:
            result = run_sample_enrichment(
                config,
                get_projects_dir() / project_id / "project.db",
                api_keys,
            )
        except Exception as exc:
            st.error(f"표본 보정 실패: {exc}")
            return

    st.success(f"표본 보정 완료: {result.succeeded}/{result.processed}건 성공")
    metric_row(
        [
            ("성공", result.succeeded, ""),
            ("실패", result.failed, ""),
            ("평균 관련성 참고", f"{result.avg_relevance_score:.2f}", ""),
            ("근거 유효", result.evidence_valid, ""),
        ]
    )
    if result.action_counts:
        st.write(result.action_counts)


def _render_audit_requirements() -> None:
    st.markdown(
        """
#### LLM 보정 결과에 자동 저장되는 정보

| 항목 | 설명 |
|------|------|
| 프롬프트 버전 | LLM에 보낸 지시문의 버전입니다. 재현성을 위해 저장합니다. |
| 모델명 | 사용한 LLM 모델입니다. 예: gemini-2.5-flash |
| Temperature | 응답의 무작위성 수준입니다. 0이면 더 일관적인 응답을 기대합니다. |
| 근거 유효/무효 | LLM이 제안한 근거 문장이 원문 또는 요약문에 실제 있는지 확인한 결과입니다. |
| 검토 상태 | 연구자가 아직 확인하지 않은 결과인지, 확인한 결과인지 표시합니다. |

LLM 보정은 자료 정리와 검토 후보 생성을 돕는 단계이며, 연구자의 해석을 대체하지 않습니다.
"""
    )


def _load_stats(project_id: str) -> dict:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection

        db_path = get_projects_dir() / project_id / "project.db"
        conn = get_connection(db_path)
        active = conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE project_id = ? AND is_active = 1",
            (project_id,),
        ).fetchone()["n"]
        llm_results = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM llm_results r
            JOIN articles a ON r.article_id = a.article_id
            WHERE a.project_id = ?
            """,
            (project_id,),
        ).fetchone()["n"]
        needs_review = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM llm_results r
            JOIN articles a ON r.article_id = a.article_id
            WHERE a.project_id = ?
              AND COALESCE(r.human_review_status, 'pending') = 'pending'
            """,
            (project_id,),
        ).fetchone()["n"]
        conn.close()
        return {"active": active, "llm_results": llm_results, "needs_review": needs_review}
    except Exception:
        return {"active": 0, "llm_results": 0, "needs_review": 0}
