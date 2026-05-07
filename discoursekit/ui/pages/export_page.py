"""Export page for data, analysis outputs, and reports."""

from __future__ import annotations

import streamlit as st

from discoursekit.ui.components import empty_state, page_header


def render() -> None:
    page_header("내보내기", "공개 가능한 기사 데이터, 분석 결과, 방법론 보고서를 생성합니다.")
    project_id = st.session_state.get("current_project_id")
    if not project_id:
        empty_state("먼저 프로젝트를 선택하세요.")
        return

    st.warning(
        "내보내기 파일에는 화면 공개용 요약문만 포함합니다. 내부 분석용 전문과 API key는 제외합니다."
    )

    tab_data, tab_report, tab_handoff = st.tabs(["기사 데이터", "보고서", "Handoff"])
    with tab_data:
        st.caption(
            "수집/정제된 기사 데이터를 파일로 내보냅니다. 공개와 공유를 위해 화면용 요약문만 포함합니다."
        )
        _render_article_export(project_id)
    with tab_report:
        _render_report_export(project_id)
    with tab_handoff:
        _render_handoff(project_id)


def _render_article_export(project_id: str) -> None:
    fmt = st.radio("형식", ["CSV", "Parquet"], horizontal=True)
    if st.button("기사 데이터 내보내기", type="primary"):
        try:
            from discoursekit.analyze.export import export_articles_csv, export_articles_parquet
            from discoursekit.config import get_projects_dir

            project_dir = get_projects_dir() / project_id
            output_dir = project_dir / "artifacts"
            output_dir.mkdir(parents=True, exist_ok=True)
            db_path = project_dir / "project.db"
            if fmt == "CSV":
                path = export_articles_csv(db_path, project_id, output_dir / "articles.csv")
            else:
                path = export_articles_parquet(db_path, project_id, output_dir / "articles.parquet")
            st.success(f"내보내기 완료: {path}")
        except Exception as exc:
            st.error(f"내보내기 실패: {exc}")


def _render_report_export(project_id: str) -> None:
    st.caption(
        "방법론 메모는 자료원, 자료 깊이, LLM 보정 역할을 기록하는 공유용 문서입니다."
    )
    if st.button("방법론 메모 생성"):
        try:
            from discoursekit.config import get_projects_dir

            output_dir = get_projects_dir() / project_id / "artifacts"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "method_note.md"
            path.write_text(_method_note_text(project_id), encoding="utf-8")
            st.success(f"방법론 메모 생성 완료: {path}")
        except Exception as exc:
            st.error(f"보고서 생성 실패: {exc}")


def _render_handoff(project_id: str) -> None:
    st.caption("수집 PC와 분석 PC를 분리해서 사용할 때 쓰는 handoff export입니다.")
    st.info("현재 handoff export UI는 기존 CLI/백엔드 기능과 연결하는 다음 작업에서 완성합니다.")


def _method_note_text(project_id: str) -> str:
    return f"""# DiscourseKit Method Note

- project_id: `{project_id}`
- public export policy: internal full text is excluded from shared exports
- NAVER News depth: title and snippet only
- BIGKinds/CSV depth: full body when provided by the uploaded file
- LLM role: enrichment assistant, not final analyst
"""
