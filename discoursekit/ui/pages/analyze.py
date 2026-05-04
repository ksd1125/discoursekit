"""Analyze page — statistics, charts, and report generation."""

import streamlit as st
from discoursekit.ui.components import page_header, section_header, metric_row, empty_state


def render():
    page_header("4. 분석·리포트", "통계 분석, 시각화, 보고서 생성을 수행합니다.")

    project_id = st.session_state.get("current_project_id")
    if not project_id:
        empty_state("먼저 프로젝트를 선택하세요.", "📂")
        return

    tab_overview, tab_charts, tab_agreement, tab_export = st.tabs(
        ["📊 개요", "📈 시각화", "🎯 일치율", "📦 내보내기"]
    )

    with tab_overview:
        _render_overview(project_id)
    with tab_charts:
        _render_charts(project_id)
    with tab_agreement:
        _render_agreement(project_id)
    with tab_export:
        _render_export(project_id)


def _render_overview(project_id: str):
    section_header("기술통계", "📊")
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.analyze.descriptive import compute_descriptive
        db_path = get_projects_dir() / project_id / "project.db"
        stats = compute_descriptive(db_path, project_id)

        metric_row([
            ("전체 기사", stats.total_articles, ""),
            ("Active 기사", stats.active_articles, ""),
            ("기간", f"{stats.date_min} ~ {stats.date_max}", ""),
            ("언론사 수", len(stats.publisher_counts), ""),
        ])

        # Publisher distribution
        st.markdown("---")
        section_header("언론사 분포 (Top 15)", "📰")
        import pandas as pd
        pub_df = pd.DataFrame(
            list(stats.publisher_counts.items())[:15],
            columns=["언론사", "건수"],
        )
        st.bar_chart(pub_df.set_index("언론사"))

        # Keywords
        if stats.keyword_top_n:
            st.markdown("---")
            section_header("주요 키워드 (Top 20)", "🏷️")
            kw_df = pd.DataFrame(stats.keyword_top_n[:20], columns=["키워드", "빈도"])
            st.dataframe(kw_df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"분석 실패: {e}")


def _render_charts(project_id: str):
    section_header("시계열 추이", "📈")
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.analyze.time_series import compute_monthly
        db_path = get_projects_dir() / project_id / "project.db"
        ts = compute_monthly(db_path, project_id)

        if not ts.periods:
            empty_state("시계열 데이터가 없습니다.", "📈")
            return

        import pandas as pd
        df = pd.DataFrame({"월": ts.periods, "기사 수": ts.total_counts})
        st.line_chart(df.set_index("월"))

        # Label breakdown if available
        if ts.label_counts:
            st.markdown("---")
            section_header("라벨별 월별 추이", "🏷️")
            label_df = pd.DataFrame(ts.label_counts, index=ts.periods)
            st.area_chart(label_df)

    except Exception as e:
        st.error(f"시각화 실패: {e}")


def _render_agreement(project_id: str):
    section_header("Rule vs LLM 일치율", "🎯")

    st.info("""
    💡 Rule-based 분류와 LLM 분류의 일치율을 측정합니다.
    Cohen's kappa ≥ 0.61이면 'substantial agreement'로 학술적으로 수용 가능합니다.
    """)

    # For now, show interface for manual comparison
    st.markdown("#### 비교 데이터 업로드")
    col1, col2 = st.columns(2)
    with col1:
        rule_file = st.file_uploader("Rule-based 결과 CSV", type=["csv"], key="rule_csv")
    with col2:
        llm_file = st.file_uploader("LLM 결과 CSV", type=["csv"], key="llm_csv")

    if rule_file and llm_file:
        if st.button("일치율 계산", type="primary"):
            try:
                import pandas as pd
                from discoursekit.analyze.agreement import compute_agreement
                rule_df = pd.read_csv(rule_file)
                llm_df = pd.read_csv(llm_file)

                # Assume 'label' column exists
                result = compute_agreement(
                    rule_df["label"].tolist(),
                    llm_df["label"].tolist(),
                )
                st.markdown("---")
                metric_row([
                    ("Accuracy", f"{result.accuracy:.4f}", ""),
                    ("Cohen's Kappa", f"{result.cohens_kappa:.4f}", ""),
                    ("샘플 수", result.n_samples, ""),
                ])

                # Per-label table
                if result.per_label:
                    st.markdown("#### 라벨별 Precision / Recall / F1")
                    rows = []
                    for label, metrics in result.per_label.items():
                        rows.append({
                            "라벨": label,
                            "Precision": f"{metrics['precision']:.3f}",
                            "Recall": f"{metrics['recall']:.3f}",
                            "F1": f"{metrics['f1']:.3f}",
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"계산 실패: {e}")


def _render_export(project_id: str):
    section_header("데이터 내보내기", "📦")

    st.warning("⚠️ 내보내기에는 `body_excerpt` (200자)만 포함됩니다. `body_internal`은 저작권 보호를 위해 제외됩니다.")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 기사 Export")
        export_format = st.radio("형식", ["CSV", "Parquet"], key="export_format")
        if st.button("기사 내보내기", key="btn_export_articles"):
            with st.spinner("내보내기 중..."):
                try:
                    from discoursekit.config import get_projects_dir
                    from discoursekit.analyze.export import (
                        export_articles_csv,
                        export_articles_parquet,
                    )

                    db_path = get_projects_dir() / project_id / "project.db"
                    output_dir = get_projects_dir() / project_id / "artifacts"
                    output_dir.mkdir(parents=True, exist_ok=True)

                    if export_format == "CSV":
                        path = export_articles_csv(db_path, project_id, output_dir / "articles.csv")
                    else:
                        path = export_articles_parquet(
                            db_path,
                            project_id,
                            output_dir / "articles.parquet",
                        )
                    st.success(f"✅ 내보내기 완료: `{path}`")
                except Exception as e:
                    st.error(f"내보내기 실패: {e}")

    with col2:
        st.markdown("#### 보고서 생성")
        if st.button("Methodology Report 생성", type="primary", key="btn_report"):
            _generate_report(project_id)

    st.markdown("---")
    section_header("Handoff 패키지", "📋")
    st.markdown("프로젝트 전체를 다른 PC로 이관할 수 있는 portable bundle을 생성합니다.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Ingest-only Handoff", key="btn_handoff_ingest"):
            with st.spinner("Handoff zip 생성 중..."):
                try:
                    from discoursekit.config import get_projects_dir
                    from discoursekit.handoff.export_ingest import export_ingest_handoff

                    db_path = get_projects_dir() / project_id / "project.db"
                    output_dir = get_projects_dir() / project_id / "artifacts"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    zip_path = export_ingest_handoff(
                        db_path,
                        project_id,
                        output_dir / f"{project_id}_ingest_handoff.zip",
                    )
                    st.success(f"✅ Handoff zip 생성 완료: `{zip_path}`")
                except Exception as e:
                    st.error(f"Handoff 생성 실패: {e}")
    with col2:
        if st.button("Full Project Bundle", key="btn_handoff_full"):
            st.warning("⏳ Backend 연결 필요: full bundle export는 아직 설계되지 않았습니다.")


def _generate_report(project_id: str):
    with st.spinner("보고서 생성 중..."):
        try:
            from discoursekit.config import get_projects_dir
            from discoursekit.analyze.runner import run_full_analysis
            from discoursekit.report.methodology import generate_methodology_report
            from pathlib import Path

            db_path = get_projects_dir() / project_id / "project.db"
            project_name = st.session_state.get("current_project_name", "Project")
            output_dir = get_projects_dir() / project_id / "artifacts"
            output_dir.mkdir(exist_ok=True)

            bundle = run_full_analysis(db_path, project_id, output_dir=output_dir)
            report_path = output_dir / "methodology_report.html"
            generate_methodology_report(bundle, project_name, report_path)

            st.success(f"✅ 보고서 생성 완료: `{report_path}`")
        except Exception as e:
            st.error(f"보고서 생성 실패: {e}")
