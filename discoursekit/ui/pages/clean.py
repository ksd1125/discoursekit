"""Clean page: deduplication, filtering, and text normalization."""

from __future__ import annotations

import streamlit as st

from discoursekit.ui.components import confirm_action, empty_state, metric_row, page_header, section_header


def render() -> None:
    page_header("정제", "중복 제거, 짧은 글 필터링, 본문 정리를 실행합니다.")

    project_id = st.session_state.get("current_project_id")
    if not project_id:
        empty_state("먼저 프로젝트를 선택하세요.")
        return

    stats = _load_clean_stats(project_id)
    if stats["articles"] == 0:
        empty_state("수집된 기사가 없습니다. 먼저 데이터 만들기 화면에서 수집을 완료하세요.")
        if st.button("데이터 만들기로 이동"):
            st.session_state["nav_page"] = "데이터 만들기"
            st.rerun()
        return

    metric_row(
        [
            ("전체 기사", stats["articles"], ""),
            ("분석 가능", stats["active"], ""),
            ("제외됨", stats["articles"] - stats["active"], ""),
            ("정제 완료", "예" if stats["cleaned"] else "아니오", ""),
        ]
    )

    st.markdown("---")
    section_header("정제 설정")
    col1, col2 = st.columns(2)
    with col1:
        min_body = st.number_input(
            "최소 본문 길이",
            value=20,
            min_value=1,
            max_value=500,
            help="이보다 짧은 본문은 분석 대상에서 제외합니다.",
        )
    with col2:
        sim_threshold = st.slider(
            "유사 제목 중복 기준",
            0.5,
            1.0,
            0.85,
            0.05,
            help="제목이 매우 비슷한 기사를 중복으로 볼 기준입니다.",
        )

    st.markdown("---")
    section_header("정제 순서")
    st.markdown(
        f"""
1. **텍스트 정리**: HTML 태그와 불필요한 공백을 제거합니다.
2. **중복 제거 1차**: 같은 제목, 날짜, 출처의 기사는 하나만 남깁니다.
3. **중복 제거 2차**: 제목이 매우 비슷한 기사도 중복 후보로 정리합니다. 현재 기준은 {sim_threshold:.0%}입니다.
4. **필터링**: 본문이 {min_body}자보다 짧은 기사와 광고성 기사를 제외합니다.
5. **공개용 요약문 분리**: 화면과 내보내기에는 짧은 요약문만 사용합니다.
"""
    )

    if confirm_action("clean", "정제를 실행하면 기존 분석 가능 상태가 갱신됩니다. 계속할까요?", "정제 실행"):
        _run_clean(project_id, min_body, sim_threshold)

    st.markdown("---")
    section_header("정제 이력")
    _render_history(project_id)


def _load_clean_stats(project_id: str) -> dict:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection

        db_path = get_projects_dir() / project_id / "project.db"
        conn = get_connection(db_path)
        articles = conn.execute("SELECT COUNT(*) AS n FROM articles WHERE project_id=?", (project_id,)).fetchone()["n"]
        active = conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE project_id=? AND is_active=1",
            (project_id,),
        ).fetchone()["n"]
        cleaned = conn.execute(
            "SELECT COUNT(*) AS n FROM clean_runs WHERE project_id=? AND status='success'",
            (project_id,),
        ).fetchone()["n"]
        conn.close()
        return {"articles": articles, "active": active, "cleaned": cleaned > 0}
    except Exception:
        return {"articles": 0, "active": 0, "cleaned": False}


def _run_clean(project_id: str, min_body: int, sim_threshold: float) -> None:
    with st.spinner("정제 중입니다."):
        try:
            from discoursekit.clean.pipeline import run_clean_pipeline
            from discoursekit.config import get_projects_dir

            db_path = get_projects_dir() / project_id / "project.db"
            run_id = run_clean_pipeline(
                db_path,
                project_id,
                min_body_chars=min_body,
                similarity_threshold=sim_threshold,
            )
            st.success(f"정제 완료: {run_id[:8]}...")
            st.rerun()
        except Exception as exc:
            st.error(f"정제 실패: {exc}")


def _render_history(project_id: str) -> None:
    try:
        import pandas as pd

        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection

        db_path = get_projects_dir() / project_id / "project.db"
        conn = get_connection(db_path)
        runs = conn.execute(
            """
            SELECT run_id, started_at, status, input_count, output_count,
                   dedup_primary, dedup_fallback, dropped_short, dropped_advert
            FROM clean_runs
            WHERE project_id=?
            ORDER BY started_at DESC
            """,
            (project_id,),
        ).fetchall()
        conn.close()
        if not runs:
            st.caption("아직 정제 이력이 없습니다.")
            return
        df = pd.DataFrame([dict(row) for row in runs])
        df.columns = [
            "Run ID",
            "시작 시간",
            "상태",
            "입력 건수",
            "출력 건수",
            "동일 중복",
            "유사 중복",
            "짧은 글 제외",
            "광고 제외",
        ]
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.caption(f"이력 조회 실패: {exc}")
