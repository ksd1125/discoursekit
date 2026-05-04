"""Ingest page — data collection from BIGKinds XLSX and CSV."""

import streamlit as st
from pathlib import Path
from discoursekit.ui.components import page_header, section_header, metric_row, empty_state, file_upload_area


def render():
    page_header("1. 자료 수집", "BIGKinds XLSX 또는 사용자 CSV 파일에서 기사를 수집합니다.")

    project_id = st.session_state.get("current_project_id")
    if not project_id:
        empty_state("먼저 프로젝트를 선택하세요.", "📂")
        return

    # ─── Source tabs ───
    tab_bigkinds, tab_csv, tab_history = st.tabs(["📊 BIGKinds XLSX", "📄 사용자 CSV", "📋 수집 이력"])

    with tab_bigkinds:
        _render_bigkinds_tab(project_id)

    with tab_csv:
        _render_csv_tab(project_id)

    with tab_history:
        _render_history(project_id)

    # ─── Extension hint + CTA ───
    st.markdown("---")
    st.caption("💡 향후 지원 예정: NAVER News API, NAVER Blog API, 공공데이터포털, RSS/URL 수집")
    st.markdown("")
    if st.button("수집 완료 → 정제 단계로 이동", key="cta_ingest_to_clean"):
        st.session_state["nav_page"] = "2. 정제"
        st.rerun()


def _render_bigkinds_tab(project_id: str):
    section_header("BIGKinds XLSX 업로드", "📊")

    st.info("💡 BIGKinds(빅카인즈)에서 다운로드한 XLSX 파일을 업로드하세요. 여러 파일을 한 번에 올릴 수 있습니다.")

    files = file_upload_area(
        "XLSX 파일 선택",
        accepted_types=["xlsx", "xls"],
        help_text="BIGKinds 뉴스 검색 결과 다운로드 파일",
        multiple=True,
    )

    date_from = None
    date_to = None
    if st.checkbox("날짜 필터 적용", key="bigkinds_date_filter"):
        col1, col2 = st.columns(2)
        with col1:
            date_from = st.date_input("시작 날짜", help="이 날짜 이후 기사만 수집합니다.")
        with col2:
            date_to = st.date_input("종료 날짜", help="이 날짜 이전 기사만 수집합니다.")

    if files:
        st.markdown(f"**{len(files)}개 파일 선택됨**")
        for f in files:
            st.caption(f"  - {f.name} ({f.size / 1024:.1f} KB)")

        if st.button("수집 시작", type="primary", key="btn_ingest_bigkinds"):
            _run_bigkinds_ingest(project_id, files, date_from, date_to)


def _render_csv_tab(project_id: str):
    section_header("사용자 CSV 업로드", "📄")

    st.info("💡 직접 준비한 CSV 파일을 업로드하세요. 컬럼 매핑을 지정할 수 있습니다.")

    files = file_upload_area(
        "CSV 파일 선택",
        accepted_types=["csv"],
        help_text="UTF-8 또는 UTF-8 BOM 인코딩 권장",
        multiple=True,
    )

    # Column mapping
    with st.expander("컬럼 매핑 설정"):
        st.caption("CSV 헤더와 DiscourseKit 필드를 매핑합니다. 기본값을 사용하면 영문 헤더를 자동 인식합니다.")
        col1, col2 = st.columns(2)
        with col1:
            map_date = st.text_input("날짜 컬럼명", value="date")
            map_title = st.text_input("제목 컬럼명", value="title")
            map_body = st.text_input("본문 컬럼명", value="body")
        with col2:
            map_publisher = st.text_input("언론사 컬럼명", value="publisher")
            map_keywords = st.text_input("키워드 컬럼명", value="keywords")
            map_url = st.text_input("URL 컬럼명", value="url")

    if files:
        st.markdown(f"**{len(files)}개 파일 선택됨**")
        if st.button("수집 시작", type="primary", key="btn_ingest_csv"):
            column_map = {
                "date": map_date, "title": map_title, "body": map_body,
                "publisher": map_publisher, "keywords": map_keywords, "url": map_url,
            }
            _run_csv_ingest(project_id, files, column_map)


def _render_history(project_id: str):
    section_header("수집 이력", "📋")
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection
        db_path = get_projects_dir() / project_id / "project.db"
        conn = get_connection(db_path)
        runs = conn.execute(
            "SELECT run_id, source, started_at, status, raw_count, in_range_count "
            "FROM ingest_runs WHERE project_id=? ORDER BY started_at DESC",
            (project_id,),
        ).fetchall()
        conn.close()

        if not runs:
            empty_state("아직 수집 이력이 없습니다.", "📋")
            return

        import pandas as pd
        df = pd.DataFrame([dict(r) for r in runs])
        df.columns = ["Run ID", "자료원", "시작 시간", "상태", "Raw 건수", "범위 내 건수"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"이력 조회 실패: {e}")


def _run_bigkinds_ingest(project_id, files, date_from, date_to):
    """Execute BIGKinds ingest with progress bar."""
    with st.spinner("수집 중..."):
        try:
            import tempfile
            from discoursekit.config import get_projects_dir
            from discoursekit.ingest.bigkinds import BigKindsAdapter
            from discoursekit.ingest.base import IngestParams
            from discoursekit.ingest.runner import run_ingest

            db_path = get_projects_dir() / project_id / "project.db"

            total_articles = 0
            for f in files:
                # Save uploaded file to temp
                with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                    tmp.write(f.read())
                    tmp_path = Path(tmp.name)

                params = IngestParams(
                    project_id=project_id,
                    source="bigkinds",
                    input_path=tmp_path,
                    date_from=str(date_from) if date_from else None,
                    date_to=str(date_to) if date_to else None,
                )
                adapter = BigKindsAdapter()
                run_ingest(adapter, params, db_path)
                tmp_path.unlink(missing_ok=True)

            st.success(f"✅ 수집 완료! {len(files)}개 파일 처리됨.")
            st.rerun()
        except Exception as e:
            st.error(f"수집 실패: {e}")


def _run_csv_ingest(project_id, files, column_map):
    """Execute CSV ingest."""
    with st.spinner("수집 중..."):
        try:
            import tempfile
            from discoursekit.config import get_projects_dir
            from discoursekit.ingest.csv_generic import CsvGenericAdapter
            from discoursekit.ingest.base import IngestParams
            from discoursekit.ingest.runner import run_ingest

            db_path = get_projects_dir() / project_id / "project.db"

            for f in files:
                with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as tmp:
                    tmp.write(f.read())
                    tmp_path = Path(tmp.name)

                params = IngestParams(project_id=project_id, source="csv", input_path=tmp_path)
                adapter = CsvGenericAdapter(column_map=column_map)
                run_ingest(adapter, params, db_path)
                tmp_path.unlink(missing_ok=True)

            st.success(f"✅ 수집 완료!")
            st.rerun()
        except Exception as e:
            st.error(f"수집 실패: {e}")
