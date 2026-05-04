"""Clean page — deduplication, filtering, and text normalization."""

import streamlit as st
from discoursekit.ui.components import page_header, section_header, metric_row, empty_state, confirm_action


def render():
    page_header("2. 정제", "중복 제거·필터링·본문 정규화를 실행합니다.")

    project_id = st.session_state.get("current_project_id")
    if not project_id:
        empty_state("먼저 프로젝트를 선택하세요.", "📂")
        return

    # Current status
    stats = _load_clean_stats(project_id)

    if stats["articles"] == 0:
        empty_state("수집된 기사가 없습니다. 먼저 '수집' 단계를 완료하세요.", "⬅️")
        return

    # ─── Status metrics ───
    metric_row([
        ("전체 기사", stats["articles"], ""),
        ("Active 기사", stats["active"], ""),
        ("제거됨", stats["articles"] - stats["active"], ""),
        ("정제 완료", "예" if stats["cleaned"] else "아니오", ""),
    ])

    st.markdown("---")

    # ─── Parameters ───
    section_header("정제 파라미터", "⚙️")
    col1, col2 = st.columns(2)
    with col1:
        min_body = st.number_input("최소 본문 길이 (자)", value=20, min_value=1, max_value=500,
                                    help="이보다 짧은 본문은 drop됩니다.")
    with col2:
        sim_threshold = st.slider("Fuzzy dedup 임계값", 0.5, 1.0, 0.85, 0.05,
                                   help="제목 trigram 유사도가 이 값 이상이면 중복으로 판정합니다.")

    st.markdown("---")

    # ─── Execute ───
    section_header("정제 실행", "▶️")

    st.markdown("""
    정제 파이프라인은 다음 순서로 실행됩니다:
    1. **텍스트 정규화**: HTML 태그 제거, 공백 정리, `<b>` 태그 strip
    2. **Primary dedup**: 동일 제목+날짜+언론사 → 제거
    3. **Fallback dedup**: 제목 유사도 ≥ 임계값 + 같은 날짜 → 제거
    4. **필터**: 단문 drop, 광고 drop
    5. **body 분리**: `body_internal` (분석용) + `body_excerpt` (200자 export용) 갱신
    """)

    if confirm_action("clean", "정제를 실행하면 기존 is_active 상태가 갱신됩니다. 계속하시겠습니까?", "정제 실행"):
        _run_clean(project_id, min_body, sim_threshold)

    # ─── History ───
    st.markdown("---")
    section_header("정제 이력", "📋")
    _render_history(project_id)

    # ─── CTA ───
    st.markdown("---")
    col_cta1, col_cta2 = st.columns(2)
    with col_cta1:
        if st.button("정제 완료 → LLM 분류로 이동", key="cta_clean_to_llm"):
            st.session_state["nav_page"] = "3. LLM 분류"
            st.rerun()
    with col_cta2:
        if st.button("📦 Handoff Export (다른 PC에서 계속)", key="cta_clean_handoff"):
            st.warning("Backend 연결 필요: `discoursekit.handoff.export_ingest` 모듈과 연결 예정")


def _load_clean_stats(project_id: str) -> dict:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection
        db_path = get_projects_dir() / project_id / "project.db"
        conn = get_connection(db_path)
        articles = conn.execute("SELECT COUNT(*) AS n FROM articles WHERE project_id=?", (project_id,)).fetchone()["n"]
        active = conn.execute("SELECT COUNT(*) AS n FROM articles WHERE project_id=? AND is_active=1", (project_id,)).fetchone()["n"]
        cleaned = conn.execute("SELECT COUNT(*) AS n FROM clean_runs WHERE project_id=? AND status='success'", (project_id,)).fetchone()["n"]
        conn.close()
        return {"articles": articles, "active": active, "cleaned": cleaned > 0}
    except Exception:
        return {"articles": 0, "active": 0, "cleaned": False}


def _run_clean(project_id: str, min_body: int, sim_threshold: float):
    with st.spinner("정제 중..."):
        try:
            from discoursekit.config import get_projects_dir
            from discoursekit.clean.pipeline import run_clean_pipeline
            db_path = get_projects_dir() / project_id / "project.db"
            run_id = run_clean_pipeline(db_path, project_id, min_body, sim_threshold)
            st.success(f"✅ 정제 완료! (run_id: {run_id[:8]}...)")
            st.rerun()
        except Exception as e:
            st.error(f"정제 실패: {e}")


def _render_history(project_id: str):
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection
        db_path = get_projects_dir() / project_id / "project.db"
        conn = get_connection(db_path)
        runs = conn.execute(
            "SELECT run_id, started_at, status, input_count, output_count, "
            "dedup_primary, dedup_fallback, dropped_short, dropped_advert "
            "FROM clean_runs WHERE project_id=? ORDER BY started_at DESC",
            (project_id,),
        ).fetchall()
        conn.close()
        if not runs:
            st.caption("이력 없음")
            return
        import pandas as pd
        df = pd.DataFrame([dict(r) for r in runs])
        df.columns = ["Run ID", "시작", "상태", "입력", "출력", "Primary Dup", "Fallback Dup", "단문", "광고"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.caption(f"이력 조회 실패: {e}")
