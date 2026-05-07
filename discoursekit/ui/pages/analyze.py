"""Python analysis dashboard rendered as insight cards."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

from discoursekit.analyze.insight_cards import InsightCardPayload, build_insight_card_payload
from discoursekit.ui.components import empty_state, page_header


# ── Responsive helpers ──

def _responsive_chart_height(desktop: int, mobile: int = 280) -> int:
    """Return chart height. Uses desktop value; Plotly responsive config handles mobile."""
    return desktop


def _plotly_responsive_config() -> dict:
    """Plotly config dict enabling responsive behavior."""
    return {"responsive": True, "displayModeBar": False}


def _responsive_columns(n: int):
    """Create columns that degrade gracefully on mobile via CSS.

    On mobile, CSS flex-wrap handles stacking; we still create n columns
    so desktop layout is correct.
    """
    return st.columns(n)


def render() -> None:
    page_header(
        "분석 대시보드",
        "지역·상권의 담론 구조를 한눈에 보여줍니다.",
    )
    project_id = st.session_state.get("current_project_id")
    if not project_id:
        empty_state("먼저 프로젝트를 선택하세요.")
        return

    stats = _compute_stats(project_id)
    if stats is None or stats.active_articles == 0:
        empty_state("분석할 기사가 없습니다.")
        st.caption(
            "수집이 아직 끝나지 않았거나, 정제 과정에서 모든 기사가 제외되었을 수 있습니다. "
            "데이터 만들기 화면에서 수집 조건과 정제 결과를 먼저 확인하세요."
        )
        if st.button("데이터 만들기로 이동", key="analyze_empty_go_data_build"):
            st.session_state["nav_page"] = "데이터 만들기"
            st.rerun()
        return

    config = _get_project_config(project_id, stats)

    # ── 1. 상단 요약 ──
    _render_summary_header(project_id, stats, config)

    # ── 2. 키워드 숲 ──
    st.markdown("---")
    _render_keywords(project_id)

    # ── 3. 시계열 ──
    st.markdown("---")
    st.markdown("### 시간 변화")
    _render_time_series(project_id)

    # ── 4. 채널별 차이 ──
    if stats.source_counts and len(stats.source_counts) > 1:
        st.markdown("---")
        st.markdown("### 채널별 자료 분포")
        _render_channel_summary(stats.source_counts)
        _render_publishers(project_id)

    # ── 5. 업소·메뉴 패널 ──
    st.markdown("---")
    st.markdown("### 업소·메뉴 관측")
    _render_place_menu_panel(project_id)

    # ── 6. 심화 분석 ──
    st.markdown("---")
    st.markdown("### 심화 분석")
    with st.expander("키워드 변화 (기준일 전후 비교)"):
        _render_keyword_trends(project_id)
    with st.expander("키워드 이동 추적"):
        _render_keyword_trajectory(project_id)
    with st.expander("의미망 분석"):
        _render_network(project_id)
    with st.expander("전후 비교"):
        _render_before_after(project_id)
    with st.expander("표본 추출"):
        _render_sampling(project_id)


def _render_summary_header(project_id: str, stats, config: dict) -> None:
    query = str(config.get("query") or "")
    date_min = config.get("date_min") or "-"
    date_max = config.get("date_max") or "-"
    depth = _source_depth_label(config.get("source_depth", ""))

    project_name = query or _project_display_name(project_id)
    st.markdown(f"### {project_name} | {date_min} ~ {date_max}")

    top_keyword_label = "-"
    peak_label = "-"
    top_taxonomy_label = "-"
    try:
        from discoursekit.analyze.keywords import compute_keyword_frequency
        from discoursekit.analyze.taxonomy import build_keyword_taxonomy

        excluded = [t.strip().lower() for t in query.split() if t.strip()]
        kw_result = compute_keyword_frequency(
            _db_path(project_id), project_id, top_n=5, min_count=2, stopwords=excluded,
        )
        if kw_result.keywords:
            kw, cnt = kw_result.keywords[0]
            top_keyword_label = f"{kw}({cnt:,})"
        taxonomy = build_keyword_taxonomy(
            kw_result.keywords, query=query, excluded=excluded, max_terms=50,
        )
        if taxonomy.category_totals:
            top_cat = taxonomy.category_totals[0]
            top_taxonomy_label = f"{top_cat['large']} > {top_cat['middle']}"
    except Exception:
        pass

    try:
        from discoursekit.analyze.time_series import compute_monthly

        ts = compute_monthly(_db_path(project_id), project_id)
        if ts.total_counts:
            max_idx = ts.total_counts.index(max(ts.total_counts))
            peak_label = ts.periods[max_idx] if max_idx < len(ts.periods) else "-"
    except Exception:
        pass

    cols = _responsive_columns(5)
    cols[0].metric("분석 가능 기사", f"{stats.active_articles:,}건")
    cols[1].metric("핵심 키워드", top_keyword_label)
    cols[2].metric("피크 시기", peak_label)
    cols[3].metric("가장 큰 담론군", top_taxonomy_label)
    cols[4].metric("자료 깊이", depth)

    if stats.source_counts and len(stats.source_counts) > 1:
        source_labels = []
        for src, cnt in stats.source_counts.items():
            label = _SOURCE_LABELS.get(src, src)
            source_labels.append(f"{label} {cnt:,}건")
        st.caption(f"채널: {' / '.join(source_labels)}")

    st.caption(
        f"데이터: 분석 가능 기사 / 기간: {date_min}~{date_max} / "
        f"기사 {stats.active_articles:,}건 / "
        f"계산 방법: SQLite COUNT/GROUP BY / 자료 깊이: {depth}"
    )
    st.caption(
        "NAVER API 자료는 제목과 요약문 기반이므로 기사 전문 의미 분석에는 한계가 있습니다."
    )


_SOURCE_LABELS: dict[str, str] = {
    "naver_news": "뉴스",
    "naver_blog": "블로그",
    "naver_cafe": "카페",
    "naver_web": "웹문서",
    "bigkinds": "빅카인즈",
    "csv": "CSV",
}


def _render_channel_summary(source_counts: dict[str, int]) -> None:
    cols = _responsive_columns(min(len(source_counts), 4))
    for idx, (source, count) in enumerate(source_counts.items()):
        label = _SOURCE_LABELS.get(source, source)
        cols[idx % len(cols)].metric(label, f"{count:,}건")


def _render_analysis_flow_hint(project_id: str) -> None:
    stats = _compute_stats(project_id)
    active_count = getattr(stats, "active_articles", 0) if stats else 0
    config = _get_project_config(project_id, stats) if stats else {}

    # Compute dynamic values for the hint row.
    top_keyword_label = "-"
    peak_label = "-"
    try:
        from discoursekit.analyze.keywords import compute_keyword_frequency

        query = str(config.get("query") or "")
        excluded = [t.strip().lower() for t in query.split() if t.strip()]
        kw_result = compute_keyword_frequency(
            _db_path(project_id), project_id, top_n=5, min_count=2, stopwords=excluded,
        )
        if kw_result.keywords:
            kw, cnt = kw_result.keywords[0]
            top_keyword_label = f"{kw}({cnt:,})"
    except Exception:
        pass

    try:
        from discoursekit.analyze.time_series import compute_monthly

        ts = compute_monthly(_db_path(project_id), project_id)
        if ts.total_counts:
            max_idx = ts.total_counts.index(max(ts.total_counts))
            peak_label = ts.periods[max_idx] if max_idx < len(ts.periods) else "-"
    except Exception:
        pass

    st.markdown("#### 분석 흐름")
    cols = _responsive_columns(4)
    cols[0].metric("1. 자료 규모", f"{active_count:,}건")
    cols[1].metric("2. 핵심 키워드", top_keyword_label)
    cols[2].metric("3. 피크 시기", peak_label)
    cols[3].metric("4. 자료 기반", _source_depth_label(config.get("source_depth", "")))


def _render_time_series(project_id: str) -> None:
    try:
        import pandas as pd
        import plotly.express as px

        from discoursekit.analyze.time_series import compute_monthly

        ts = compute_monthly(_db_path(project_id), project_id)
        if not ts.periods:
            empty_state("시계열 데이터가 없습니다.")
            return

        config = _get_project_config(project_id)
        payload = build_insight_card_payload("time_series", ts, config)
        df = pd.DataFrame({"period": ts.periods, "count": ts.total_counts})
        fig = px.area(df, x="period", y="count", markers=True)
        fig.update_layout(
            template="plotly_white",
            height=_responsive_chart_height(390),
            margin=dict(l=10, r=10, t=20, b=30),
            xaxis_title="Period",
            yaxis_title="Articles",
            xaxis=dict(tickangle=-45, tickfont=dict(size=11)),
            yaxis=dict(tickfont=dict(size=11)),
        )
        _add_time_series_annotations(fig, ts, config)
        _render_insight_card(replace(payload, chart_data=fig, evidence_items=_peak_evidence(project_id, ts, config)))
    except Exception as exc:
        st.error(f"시계열 분석 실패: {exc}")


def _render_keywords(project_id: str) -> None:
    st.markdown("### 키워드 숲")
    try:
        import pandas as pd
        import plotly.express as px

        from discoursekit.analyze.keywords import compute_keyword_frequency
        from discoursekit.analyze.taxonomy import build_keyword_taxonomy

        config = _get_project_config(project_id)
        default_excluded = str(config.get("query") or "").strip()
        excluded_text = st.text_input(
            "분석에서 제외할 기준어",
            value=default_excluded,
            key=f"keyword_excluded_{project_id}",
            help="검색어 자체가 반복 등장하면 주제 구조를 가리므로 기본 제외합니다. 쉼표로 추가할 수 있습니다.",
        )
        excluded_terms = _split_terms(excluded_text)
        result = compute_keyword_frequency(
            _db_path(project_id),
            project_id,
            top_n=50,
            min_count=2,
            stopwords=excluded_terms,
        )
        if not result.keywords:
            empty_state("키워드 데이터가 없습니다.")
            return

        taxonomy = build_keyword_taxonomy(
            result.keywords,
            query=str(config.get("query") or ""),
            excluded=excluded_terms,
            max_terms=50,
        )
        _render_keyword_forest(taxonomy)

        payload = build_insight_card_payload("keywords", result, config)
        df = pd.DataFrame(result.keywords[:30], columns=["keyword", "count"])
        fig = px.bar(
            df,
            y="keyword",
            x="count",
            orientation="h",
            color_discrete_sequence=["#2563eb"],
        )
        fig.update_layout(
            template="plotly_white",
            height=_responsive_chart_height(max(420, len(df) * 24)),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
            xaxis_title="Count",
            yaxis_title="",
            margin=dict(l=10, r=10, t=20, b=10),
        )
        fig.update_traces(text=df["count"], textposition="outside", cliponaxis=False)
        _render_insight_card(
            replace(payload, chart_data=fig, evidence_items=_keyword_evidence(project_id, result.keywords[:3]))
        )
        _render_keyword_distribution_summary(result)
        _render_keyword_llm_panel(project_id, result, config)
    except Exception as exc:
        st.error(f"키워드 분석 실패: {exc}")


def _render_keyword_forest(taxonomy) -> None:
    st.markdown("#### 키워드 숲")
    st.info(taxonomy.summary)
    if not taxonomy.rows:
        return
    try:
        import pandas as pd
        import plotly.express as px

        df = pd.DataFrame(taxonomy.rows)
        fig = px.sunburst(
            df,
            path=["large", "middle", "small", "keyword"],
            values="count",
            color="large",
        )
        fig.update_layout(
            template="plotly_white",
            height=_responsive_chart_height(520, 360),
            margin=dict(l=5, r=5, t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True, config=_plotly_responsive_config())

        totals_df = pd.DataFrame(taxonomy.category_totals)
        st.markdown("##### 대/중분류 요약")
        st.dataframe(totals_df, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.caption(f"키워드 숲 시각화를 만들 수 없습니다: {exc}")


def _render_keyword_trends(project_id: str) -> None:
    config = _get_project_config(project_id)
    cutoff = _cutoff_input(config, key_prefix="keyword_trends", label="키워드 변화 기준일")
    if cutoff is None:
        return

    try:
        import pandas as pd
        import plotly.express as px

        from discoursekit.analyze.keywords import compute_keyword_trends

        query_stopwords = [w.strip() for w in (config.get("query") or "").split() if w.strip()]
        result = compute_keyword_trends(
            _db_path(project_id),
            project_id,
            cutoff_date=cutoff,
            top_n=20,
            stopwords=query_stopwords or None,
        )
        payload = build_insight_card_payload(
            "keyword_trends",
            result,
            {**config, "cutoff_date": cutoff},
        )

        before = dict(result.before_keywords)
        after = dict(result.after_keywords)
        keywords = list(dict.fromkeys([kw for kw, _ in result.after_keywords[:15]] + [kw for kw, _ in result.before_keywords[:15]]))
        if not keywords:
            empty_state("비교할 키워드가 없습니다.")
            return
        df = pd.DataFrame(
            [
                {"keyword": keyword, "period": "before", "count": before.get(keyword, 0)}
                for keyword in keywords
            ]
            + [
                {"keyword": keyword, "period": "after", "count": after.get(keyword, 0)}
                for keyword in keywords
            ]
        )
        fig = px.bar(
            df,
            y="keyword",
            x="count",
            color="period",
            barmode="group",
            orientation="h",
            color_discrete_map={"before": "#94a3b8", "after": "#2563eb"},
        )
        fig.update_layout(
            template="plotly_white",
            height=_responsive_chart_height(max(420, len(keywords) * 28)),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
            xaxis_title="Count",
            yaxis_title="",
            margin=dict(l=10, r=10, t=20, b=10),
        )
        _render_insight_card(
            replace(payload, chart_data=fig, evidence_items=_trend_evidence(project_id, result))
        )
        _render_keyword_change_llm_panel(project_id, result, config)
        _render_network_comparison(project_id, cutoff)
    except Exception as exc:
        st.error(f"키워드 변화 분석 실패: {exc}")


def _render_keyword_trajectory(project_id: str) -> None:
    config = _get_project_config(project_id)
    st.caption(
        "기준 키워드가 시기별로 어떤 주변어와 연결되고, 어떤 역할로 바뀌는지 추적합니다. "
        "담론군 이동은 계산된 클러스터 흐름이며 최종 해석은 연구자가 검토해야 합니다."
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        focus = st.text_input(
            "기준 키워드",
            value=str(config.get("query") or ""),
            key=f"traj_focus_{project_id}",
        )
    with col2:
        period_label = st.selectbox(
            "시간 단위",
            ["월별", "주별"],
            key=f"traj_period_{project_id}",
        )
        period_type = "week" if period_label == "주별" else "month"
    with col3:
        default_cutoff = _default_cutoff(config)
        cutoff = st.date_input("기준일", value=default_cutoff, key=f"traj_cutoff_{project_id}")

    col4, col5, col6 = st.columns(3)
    with col4:
        top_n = st.slider("시기별 키워드 수", 15, 60, 30, step=5, key=f"traj_topn_{project_id}")
    with col5:
        min_count = st.slider("최소 빈도", 1, 10, 1, key=f"traj_mincount_{project_id}")
    with col6:
        min_cooc = st.slider("최소 동시출현", 1, 10, 1, key=f"traj_mincooc_{project_id}")

    if st.button("키워드 이동 분석", type="primary", key=f"traj_run_{project_id}"):
        if not focus.strip():
            st.warning("기준 키워드를 입력하세요.")
            return
        try:
            from discoursekit.analyze.trajectory import compute_keyword_trajectory

            result = compute_keyword_trajectory(
                _db_path(project_id),
                project_id,
                focus.strip(),
                cutoff_date=str(cutoff),
                period_type=period_type,
                top_n=int(top_n),
                min_count=int(min_count),
                min_cooccurrence=int(min_cooc),
            )
            st.session_state[f"trajectory_result_{project_id}"] = result
        except Exception as exc:
            st.error(f"키워드 이동 분석 실패: {exc}")
            return

    result = st.session_state.get(f"trajectory_result_{project_id}")
    if not result:
        st.info("기준 키워드와 시간 단위를 정한 뒤 키워드 이동 분석 버튼을 누르세요.")
        return
    if not result.snapshots:
        empty_state("키워드 이동을 계산할 기간별 데이터가 없습니다.")
        return

    st.info(result.summary)
    _render_trajectory_focus_timeline(result)
    _render_trajectory_sankey(result)
    _render_trajectory_tables(result)


def _render_trajectory_focus_timeline(result) -> None:
    import pandas as pd
    import plotly.express as px

    rows = [
        {
            "period": snapshot.period,
            "phase": snapshot.phase,
            "focus_count": snapshot.focus_count,
            "focus_role": snapshot.focus_role,
            "article_count": snapshot.article_count,
            "dominant_cluster": snapshot.dominant_cluster,
        }
        for snapshot in result.snapshots
    ]
    df = pd.DataFrame(rows)
    st.markdown("#### 기준 키워드 역할 변화")
    fig = px.line(
        df,
        x="period",
        y="focus_count",
        markers=True,
        hover_data=["focus_role", "article_count", "dominant_cluster"],
    )
    fig.update_layout(
        template="plotly_white",
        height=_responsive_chart_height(360),
        xaxis_title="Period",
        yaxis_title="Focus keyword count",
        xaxis=dict(tickangle=-45, tickfont=dict(size=11)),
        margin=dict(l=10, r=10, t=20, b=30),
    )
    st.plotly_chart(fig, use_container_width=True, config=_plotly_responsive_config())
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_trajectory_sankey(result) -> None:
    if not result.sankey_nodes or not result.sankey_links:
        st.caption("담론군 흐름을 만들 만큼 연속된 기간이 충분하지 않습니다.")
        return
    try:
        import plotly.graph_objects as go

        labels = [node["label"] for node in result.sankey_nodes]
        fig = go.Figure(
            data=[
                go.Sankey(
                    node=dict(label=labels, pad=18, thickness=16),
                    link=dict(
                        source=[link["source"] for link in result.sankey_links],
                        target=[link["target"] for link in result.sankey_links],
                        value=[link["value"] for link in result.sankey_links],
                    ),
                )
            ]
        )
        fig.update_layout(
            template="plotly_white",
            height=_responsive_chart_height(440, 320),
            margin=dict(l=5, r=5, t=20, b=10),
        )
        st.markdown("#### 담론군 흐름")
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:
        st.caption(f"담론군 흐름 시각화를 만들 수 없습니다: {exc}")


def _render_trajectory_tables(result) -> None:
    import pandas as pd

    neighbor_rows = []
    for snapshot in result.snapshots:
        for neighbor in snapshot.focus_neighbors[:10]:
            neighbor_rows.append(
                {
                    "period": snapshot.period,
                    "phase": snapshot.phase,
                    "neighbor": neighbor["keyword"],
                    "weight": neighbor["weight"],
                    "degree": round(neighbor["degree"], 3),
                    "community": neighbor["community"] + 1 if neighbor["community"] >= 0 else "",
                }
            )
    if neighbor_rows:
        st.markdown("#### 기준 키워드 주변어")
        st.dataframe(pd.DataFrame(neighbor_rows), use_container_width=True, hide_index=True)

    if result.role_changes:
        st.markdown("#### 역할/담론군 이동 후보")
        st.dataframe(pd.DataFrame(result.role_changes), use_container_width=True, hide_index=True)

    path_rows = [
        {
            "keyword": path["keyword"],
            "first_period": path["first_period"],
            "last_period": path["last_period"],
            "periods_active": path["periods_active"],
            "from_role": path["first_role"],
            "to_role": path["last_role"],
            "peak_period": path["peak_period"],
            "peak_count": path["peak_count"],
            "from_cluster": path["first_community"],
            "to_cluster": path["last_community"],
        }
        for path in result.keyword_paths[:80]
    ]
    if path_rows:
        with st.expander("전체 키워드 이동 표", expanded=False):
            st.dataframe(pd.DataFrame(path_rows), use_container_width=True, hide_index=True)


def _render_network(project_id: str) -> None:
    st.caption(
        "키워드가 기사 안에서 함께 등장한 관계를 의미망으로 봅니다. "
        "이 결과는 구조 참고 자료이며, 해석은 연구자가 검토해야 합니다."
    )
    config = _get_project_config(project_id)
    with st.expander("매개변수 조절", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            top_n = st.slider("키워드 수", 20, 60, 40, step=5, key=f"net_topn_{project_id}")
        with col2:
            min_count = st.slider("최소 키워드 빈도", 1, 10, 2, key=f"net_mincount_{project_id}")
        with col3:
            min_cooc = st.slider("최소 동시출현", 1, 10, 2, key=f"net_mincooc_{project_id}")
        if st.button("다시 계산", key=f"net_rerun_{project_id}"):
            st.session_state.pop(f"network_result_{project_id}", None)

    cache_key = f"network_result_{project_id}"
    params_key = (int(top_n), int(min_count), int(min_cooc))
    cached_params = st.session_state.get(f"network_params_{project_id}")
    if cache_key not in st.session_state or cached_params != params_key:
        try:
            from discoursekit.analyze.network import compute_keyword_network

            result = compute_keyword_network(
                _db_path(project_id),
                project_id,
                top_n=int(top_n),
                min_count=int(min_count),
                min_cooccurrence=int(min_cooc),
            )
            st.session_state[cache_key] = result
            st.session_state[f"network_params_{project_id}"] = params_key
        except Exception as exc:
            st.error(f"의미망 분석 실패: {exc}")
            return

    result = st.session_state.get(cache_key)
    if not result:
        return
    if result.num_nodes == 0:
        empty_state("의미망을 구성할 키워드 연결이 없습니다.")
        st.caption("최소 키워드 빈도 또는 최소 동시출현 기준을 낮춰보세요.")
        return

    payload = build_insight_card_payload("network", result, config)
    _render_insight_card(payload)
    _render_network_chart(result)
    _render_network_tables(result)
    _render_topic_structure(project_id, int(top_n))
    _render_network_download(project_id, result)
    _render_network_llm_panel(project_id, result, config)


def _render_network_chart(result) -> None:
    try:
        import plotly.graph_objects as go

        positions = _spring_layout(result.nodes, result.edges)
        edge_x, edge_y = [], []
        for edge in result.edges:
            source = edge["source"]
            target = edge["target"]
            if source not in positions or target not in positions:
                continue
            x0, y0 = positions[source]
            x1, y1 = positions[target]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

        edge_trace = go.Scatter(
            x=edge_x,
            y=edge_y,
            mode="lines",
            hoverinfo="none",
            line=dict(width=0.7, color="#cbd5e1"),
        )
        visible_nodes = [node for node in result.nodes if node["keyword"] in positions]
        node_trace = go.Scatter(
            x=[positions[node["keyword"]][0] for node in visible_nodes],
            y=[positions[node["keyword"]][1] for node in visible_nodes],
            mode="markers+text",
            text=[node["keyword"] for node in visible_nodes],
            textposition="top center",
            textfont=dict(size=10),
            hovertemplate=(
                "%{text}<br>"
                "빈도: %{customdata[0]}<br>"
                "연결 중심성: %{customdata[1]:.3f}<br>"
                "매개 중심성: %{customdata[2]:.3f}<extra></extra>"
            ),
            customdata=[
                [node["count"], node["degree"], node["betweenness"]]
                for node in visible_nodes
            ],
            marker=dict(
                size=[max(10, min(42, node["count"] * 3)) for node in visible_nodes],
                color=[node["community"] for node in visible_nodes],
                colorscale="Set3",
                line=dict(width=1, color="#64748b"),
            ),
        )
        fig = go.Figure(data=[edge_trace, node_trace])
        fig.update_layout(
            template="plotly_white",
            height=_responsive_chart_height(600, 380),
            showlegend=False,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            margin=dict(l=5, r=5, t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True, config=_plotly_responsive_config())
    except Exception as exc:
        st.caption(f"의미망 시각화를 만들 수 없습니다: {exc}")


def _render_network_tables(result) -> None:
    import pandas as pd

    st.markdown("#### 중심 키워드")
    centrality_df = pd.DataFrame(
        [
            {
                "키워드": node["keyword"],
                "빈도": node["count"],
                "연결 중심성": round(node["degree"], 3),
                "매개 중심성": round(node["betweenness"], 3),
                "근접 중심성": round(node["closeness"], 3),
                "클러스터": node["community"] + 1,
            }
            for node in sorted(result.nodes, key=lambda item: item["degree"], reverse=True)
        ]
    )
    st.dataframe(centrality_df, use_container_width=True, hide_index=True)

    if result.communities:
        st.markdown("#### 의미 클러스터")
        for community in result.communities:
            keywords = ", ".join(community["keywords"][:12])
            suffix = f" 외 {len(community['keywords']) - 12}개" if len(community["keywords"]) > 12 else ""
            st.markdown(f"**{community['label']}** ({len(community['keywords'])}개): {keywords}{suffix}")


def _render_topic_structure(project_id: str, top_n: int) -> None:
    try:
        from discoursekit.analyze.topic_structure import compute_topic_structure

        structure = compute_topic_structure(_db_path(project_id), project_id, top_n=top_n)
    except Exception as exc:
        st.caption(f"담론 구조 요약을 만들 수 없습니다: {exc}")
        return

    with st.expander("담론 구조 요약", expanded=True):
        st.info(structure.structural_summary)
        cols = _responsive_columns(3)
        with cols[0]:
            st.markdown("**브리지 키워드 후보**")
            for keyword in structure.bridge_keywords[:5]:
                st.markdown(f"- {keyword}")
        with cols[1]:
            st.markdown("**주변부 키워드**")
            for keyword in structure.peripheral_keywords[:5]:
                st.markdown(f"- {keyword}")
        with cols[2]:
            st.metric("상위 중심성 집중도", f"{structure.concentration_index:.1f}%")


def _render_network_download(project_id: str, result) -> None:
    try:
        from discoursekit.analyze.network import to_gexf_string

        st.download_button(
            "Gephi용 GEXF 다운로드",
            data=to_gexf_string(result),
            file_name=f"{project_id}_network.gexf",
            mime="application/gexf+xml",
            key=f"gexf_download_{project_id}",
        )
    except Exception as exc:
        st.caption(f"GEXF 파일을 만들 수 없습니다: {exc}")


def _render_network_llm_panel(project_id: str, result, config: dict) -> None:
    with st.expander("LLM 제안: 네트워크 구조 해석", expanded=False):
        st.caption(
            "버튼을 눌러야 LLM/휴리스틱 해석을 생성합니다. "
            "결과는 클러스터 이름과 중심 키워드 해석을 돕는 참고 자료입니다."
        )
        topic = st.text_input(
            "연구 주제",
            value=str(config.get("research_topic") or config.get("query") or ""),
            key=f"net_topic_{project_id}",
        )
        if st.button("LLM 네트워크 해석 요청", key=f"net_llm_{project_id}"):
            from discoursekit.llm.keyword_advisor import analyze_keywords

            top_keywords = [
                (node["keyword"], node["count"])
                for node in sorted(result.nodes, key=lambda item: item["degree"], reverse=True)[:30]
            ]
            api_key = _get_interactive_api_key()
            grouping = analyze_keywords(
                topic,
                top_keywords,
                article_count=int(config.get("active_count", 0) or 0),
                api_key=api_key,
            )
            st.session_state[f"net_grouping_{project_id}"] = grouping

        grouping = st.session_state.get(f"net_grouping_{project_id}")
        if not grouping:
            return
        st.markdown("**네트워크 기반 의미 그룹 제안**")
        st.dataframe(grouping.groups, use_container_width=True, hide_index=True)
        st.markdown("**주제 적합성 제안**")
        st.write(
            {
                "core": grouping.topic_core,
                "related": grouping.topic_related,
                "off_topic": grouping.topic_off,
            }
        )
        if grouping.noise_candidates:
            st.markdown("**노이즈 후보**")
            st.dataframe(grouping.noise_candidates, use_container_width=True, hide_index=True)
        st.info(grouping.summary)


def _render_network_comparison(project_id: str, cutoff: str) -> None:
    with st.expander("전후 의미망 구조 비교", expanded=False):
        st.caption("기준일 전후에 새로 생긴 연결, 사라진 연결, 중심성 순위 변화를 비교합니다.")
        if st.button("의미망 비교 실행", key=f"net_compare_{project_id}"):
            try:
                from discoursekit.analyze.network import compare_networks

                comparison = compare_networks(
                    _db_path(project_id),
                    project_id,
                    cutoff_date=cutoff,
                    top_n=30,
                    min_cooccurrence=1,
                )
                st.session_state[f"net_comparison_{project_id}"] = comparison
            except Exception as exc:
                st.error(f"의미망 비교 실패: {exc}")
                return

        comparison = st.session_state.get(f"net_comparison_{project_id}")
        if not comparison:
            return
        cols = _responsive_columns(3)
        cols[0].metric("새 연결", len(comparison.new_connections))
        cols[1].metric("사라진 연결", len(comparison.lost_connections))
        cols[2].metric("중심성 변화", len(comparison.centrality_shifts))

        import pandas as pd

        if comparison.centrality_shifts:
            st.markdown("**중심성 순위 변화**")
            st.dataframe(
                pd.DataFrame(comparison.centrality_shifts),
                use_container_width=True,
                hide_index=True,
            )
        if comparison.new_connections:
            st.markdown("**새로 나타난 연결**")
            st.dataframe(
                pd.DataFrame(comparison.new_connections[:20]),
                use_container_width=True,
                hide_index=True,
            )


def _spring_layout(nodes, edges, iterations: int = 50) -> dict[str, tuple[float, float]]:
    import math
    import random

    if not nodes:
        return {}
    random.seed(42)
    keywords = [node["keyword"] for node in nodes]
    positions = {
        keyword: (random.uniform(-1, 1), random.uniform(-1, 1))
        for keyword in keywords
    }
    k = 1.0 / math.sqrt(len(keywords))
    for iteration in range(iterations):
        displacement = {keyword: [0.0, 0.0] for keyword in keywords}
        for idx, source in enumerate(keywords):
            for target in keywords[idx + 1 :]:
                dx = positions[source][0] - positions[target][0]
                dy = positions[source][1] - positions[target][1]
                distance = max(0.01, math.sqrt(dx * dx + dy * dy))
                force = k * k / distance
                displacement[source][0] += dx / distance * force
                displacement[source][1] += dy / distance * force
                displacement[target][0] -= dx / distance * force
                displacement[target][1] -= dy / distance * force
        for edge in edges:
            source = edge["source"]
            target = edge["target"]
            if source not in positions or target not in positions:
                continue
            dx = positions[source][0] - positions[target][0]
            dy = positions[source][1] - positions[target][1]
            distance = max(0.01, math.sqrt(dx * dx + dy * dy))
            force = distance * distance / k
            weight = max(1.0, float(edge.get("weight", 1)))
            displacement[source][0] -= dx / distance * force * weight
            displacement[source][1] -= dy / distance * force * weight
            displacement[target][0] += dx / distance * force * weight
            displacement[target][1] += dy / distance * force * weight
        temperature = 0.12 * (1 - iteration / max(1, iterations))
        for keyword in keywords:
            dx, dy = displacement[keyword]
            distance = max(0.01, math.sqrt(dx * dx + dy * dy))
            scale = min(distance, temperature) / distance
            positions[keyword] = (
                positions[keyword][0] + dx * scale,
                positions[keyword][1] + dy * scale,
            )
    return positions


def _render_place_menu_panel(project_id: str) -> None:
    from discoursekit.core.db import count_place_reviews, get_connection, migrate_schema

    conn = get_connection(_db_path(project_id))
    migrate_schema(conn)
    try:
        review_count = count_place_reviews(conn, project_id)
    finally:
        conn.close()

    if review_count == 0:
        empty_state("플레이스 리뷰 데이터가 없습니다.")
        st.caption(
            "NAVER Place 리뷰를 수집하면 업소별 메뉴 관측 패널을 볼 수 있습니다. "
            "데이터 만들기 화면에서 Place 리뷰를 수집하세요."
        )
        return

    from discoursekit.analyze.place_menu import (
        build_observations,
        get_first_seen_by_channel,
        get_menu_summary,
        get_place_summary,
    )

    cache_key = f"place_obs_{project_id}"
    if cache_key not in st.session_state:
        with st.spinner("메뉴 관측 테이블 생성 중..."):
            summary = build_observations(_db_path(project_id), project_id)
        st.session_state[cache_key] = summary

    obs_summary = st.session_state[cache_key]

    cols = _responsive_columns(4)
    cols[0].metric("리뷰 수", f"{obs_summary.total_reviews:,}")
    cols[1].metric("메뉴 보유 리뷰", f"{obs_summary.reviews_with_menu:,}")
    cols[2].metric("관측 업소", f"{obs_summary.unique_places:,}")
    cols[3].metric("관측 메뉴", f"{obs_summary.unique_menus:,}")

    conn = get_connection(_db_path(project_id))
    try:
        place_data = get_place_summary(conn, project_id)
        menu_data = get_menu_summary(conn, project_id)
    finally:
        conn.close()

    st.markdown("##### 업소별 관측")
    if place_data:
        try:
            import pandas as pd

            df = pd.DataFrame(place_data)
            df.columns = ["place_id", "업소명", "리뷰 수", "메뉴 수", "최초 관측"]
            st.dataframe(
                df[["업소명", "리뷰 수", "메뉴 수", "최초 관측"]],
                use_container_width=True,
                hide_index=True,
            )
        except ImportError:
            for p in place_data[:20]:
                st.text(
                    f"{p['place_name']}  리뷰 {p['review_count']}  "
                    f"메뉴 {p['menu_count']}  최초 {p['first_observed']}"
                )
    else:
        st.info("업소 관측 데이터가 없습니다.")

    st.markdown("##### 메뉴별 관측")
    if menu_data:
        try:
            import pandas as pd

            df = pd.DataFrame(menu_data)
            df.columns = ["메뉴명", "관측 점포 수", "총 리뷰 수", "최초 관측"]
            st.dataframe(df, use_container_width=True, hide_index=True)
        except ImportError:
            for m in menu_data[:30]:
                st.text(
                    f"{m['normalized_menu_name']}  점포 {m['place_count']}  "
                    f"리뷰 {m['total_reviews']}  최초 {m['first_observed']}"
                )
    else:
        st.info("메뉴 관측 데이터가 없습니다.")

    st.markdown("##### 확산 분석")
    st.caption(
        "키워드를 입력하면 어떤 채널에서 먼저 관측되었는지 확인합니다. "
        "(플레이스 메뉴 선행 → 메뉴 주도형, 블로그 선행 → 콘텐츠 주도형)"
    )
    diffusion_kw = st.text_input(
        "확산 추적 키워드",
        placeholder="예: 두쫀쿠, 돈카츠, 약과",
        key=f"diffusion_kw_{project_id}",
    )
    if diffusion_kw.strip():
        conn = get_connection(_db_path(project_id))
        try:
            results = get_first_seen_by_channel(conn, project_id, diffusion_kw.strip())
        finally:
            conn.close()
        if results:
            _CHANNEL_LABELS = {
                "naver_news": "뉴스",
                "naver_blog": "블로그",
                "naver_cafe": "카페",
                "naver_web": "웹문서",
                "naver_place": "플레이스 리뷰",
            }
            _LEAD_TYPES = {
                "naver_place": "메뉴 주도형",
                "naver_blog": "콘텐츠 주도형",
                "naver_news": "보도 주도형",
                "naver_cafe": "커뮤니티 주도형",
                "naver_web": "웹 주도형",
            }
            for r in results:
                ch = _CHANNEL_LABELS.get(r["channel"], r["channel"])
                st.markdown(
                    f"- **{ch}**: {r['first_seen_at']} — {r.get('first_seen_text', '')[:60]}"
                )
            lead = results[0]["channel"]
            st.info(f"선행 채널: {_CHANNEL_LABELS.get(lead, lead)} → {_LEAD_TYPES.get(lead, '확인 필요')}")
        else:
            st.info(f"'{diffusion_kw}'에 해당하는 관측이 없습니다.")

    if st.button("관측 테이블 재생성", key=f"rebuild_obs_{project_id}"):
        if cache_key in st.session_state:
            del st.session_state[cache_key]
        st.rerun()


def _render_publishers(project_id: str) -> None:
    stats = _compute_stats(project_id)
    if stats is None or not stats.publisher_counts:
        empty_state("출처 데이터가 없습니다.")
        return

    try:
        import pandas as pd
        import plotly.express as px

        config = _get_project_config(project_id, stats)
        payload = build_insight_card_payload("publishers", stats, config)
        rows = list(stats.publisher_counts.items())[:20]
        df = pd.DataFrame(rows, columns=["publisher", "count"])
        df["group"] = ["Top 5" if idx < 5 else "Other" for idx in range(len(df))]
        fig = px.bar(
            df,
            y="publisher",
            x="count",
            color="group",
            orientation="h",
            color_discrete_map={"Top 5": "#2563eb", "Other": "#cbd5e1"},
        )
        fig.update_layout(
            template="plotly_white",
            height=_responsive_chart_height(max(420, len(df) * 26)),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
            xaxis_title="Articles",
            yaxis_title="",
            margin=dict(l=10, r=10, t=20, b=10),
            showlegend=False,
        )
        fig.update_traces(text=df["count"], textposition="outside", cliponaxis=False)
        _render_insight_card(
            replace(payload, chart_data=fig, evidence_items=_publisher_evidence(project_id, rows[:3]))
        )
    except Exception as exc:
        st.error(f"출처 분석 실패: {exc}")


def _render_before_after(project_id: str) -> None:
    config = _get_project_config(project_id)
    cutoff = _cutoff_input(config, key_prefix="before_after", label="전후 비교 기준일")
    if cutoff is None:
        return

    try:
        import pandas as pd
        import plotly.express as px

        from discoursekit.analyze.before_after import compare_before_after

        result = compare_before_after(_db_path(project_id), project_id, cutoff_date=cutoff)
        payload = build_insight_card_payload(
            "before_after",
            result,
            {**config, "cutoff_date": cutoff},
        )
        df = pd.DataFrame(
            [
                {"period": "before", "count": result.before_count},
                {"period": "after", "count": result.after_count},
            ]
        )
        fig = px.bar(
            df,
            x="period",
            y="count",
            color="period",
            color_discrete_map={"before": "#94a3b8", "after": "#2563eb"},
        )
        fig.update_layout(
            template="plotly_white",
            height=_responsive_chart_height(360),
            xaxis_title="Period",
            yaxis_title="Articles",
            margin=dict(l=10, r=10, t=20, b=10),
            showlegend=False,
        )
        if result.after_monthly_avg or result.before_monthly_avg:
            fig.add_annotation(
                x="after",
                y=result.after_count,
                text=f"after avg {result.after_monthly_avg:.1f}/month",
                showarrow=True,
                arrowhead=2,
                ax=0,
                ay=-35,
            )
        _render_insight_card(
            replace(payload, chart_data=fig, evidence_items=_cutoff_evidence(project_id, cutoff))
        )
    except Exception as exc:
        st.error(f"전후 비교 실패: {exc}")


def _render_sampling(project_id: str) -> None:
    from discoursekit.analyze.sampling import sample_representative_articles

    strategy_labels = {
        "random": "무작위",
        "peak_period": "보도량 최대 시기",
        "keyword_match": "키워드 매칭",
        "stratified": "출처 층화",
        "recent": "최신순",
    }
    strategy = st.selectbox(
        "표본 전략",
        list(strategy_labels),
        format_func=strategy_labels.get,
    )
    n = st.number_input("표본 크기", min_value=5, max_value=100, value=10, step=5)
    keyword = None
    if strategy == "keyword_match":
        keyword = st.text_input("매칭 키워드", value=_get_project_config(project_id).get("query", ""))
        if not keyword.strip():
            st.info("키워드 매칭 표본을 위해 매칭 키워드를 입력하세요.")
            return

    if not st.button("표본 추출", type="primary"):
        return

    try:
        result = sample_representative_articles(
            _db_path(project_id),
            project_id,
            strategy=strategy,
            n=int(n),
            keyword=keyword,
        )
        if not result.articles:
            empty_state("추출된 표본이 없습니다.")
            return
        payload = build_insight_card_payload("sampling", result, _get_project_config(project_id))
        _render_insight_card(payload)
    except Exception as exc:
        st.error(f"표본 추출 실패: {exc}")


def _render_insight_card(payload: InsightCardPayload) -> None:
    st.markdown(
        f"""
<div class="insight-card">
  <div class="insight-headline">{payload.headline}</div>
  <div class="insight-subhead">{payload.subhead}</div>
</div>
""",
        unsafe_allow_html=True,
    )

    if payload.chart_data is not None:
        st.plotly_chart(payload.chart_data, use_container_width=True, config=_plotly_responsive_config())

    if payload.callouts:
        cols = _responsive_columns(min(len(payload.callouts), 3))
        for idx, callout in enumerate(payload.callouts[:3]):
            with cols[idx]:
                st.markdown(
                    f'<div class="insight-callout">{callout}</div>',
                    unsafe_allow_html=True,
                )

    if payload.evidence_items:
        with st.expander("근거 기사 보기"):
            import pandas as pd

            df = pd.DataFrame(payload.evidence_items)
            st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown(f'<div class="method-note">{payload.method_note}</div>', unsafe_allow_html=True)
    if payload.caveat:
        st.markdown(f'<div class="caveat">{payload.caveat}</div>', unsafe_allow_html=True)


def _cutoff_input(config: dict, key_prefix: str, label: str) -> str | None:
    cutoff = config.get("cutoff_date")
    if cutoff:
        st.caption(f"{label}: {cutoff}")
        return str(cutoff)

    st.markdown(
        "💡 **기준일 선택 도움말**: 연구 대상 사건의 발생일, 정책 시행일, "
        "또는 시계열 탭에서 보도량이 급증한 시점을 넣으세요."
    )

    peak_info = _detect_peak(config)
    if peak_info:
        st.caption(f"시계열 피크 감지: {peak_info['period']} ({peak_info['count']:,}건)")
        if st.button(f"{peak_info['period']}-01 사용", key=f"{key_prefix}_use_peak"):
            return f"{peak_info['period']}-01"

    default = _default_cutoff(config)
    selected = st.date_input(label, value=default, key=f"{key_prefix}_cutoff")
    if not st.button("계산", key=f"{key_prefix}_compute"):
        st.info("기준일을 선택하고 계산 버튼을 누르세요.")
        return None
    return str(selected)


def _default_cutoff(config: dict) -> date:
    source = config.get("date_min") or date.today().isoformat()
    try:
        return date.fromisoformat(str(source)[:10])
    except ValueError:
        return date.today()


def _get_project_config(project_id: str, stats: Any | None = None) -> dict:
    stats = stats or _compute_stats(project_id)
    analysis_config = st.session_state.get("analysis_config", {})
    query = analysis_config.get("query", "")
    if not query:
        query = _project_display_name(project_id)
    return {
        "project_id": project_id,
        "query": query,
        "source_depth": _project_source_depth(project_id),
        "active_count": stats.active_articles if stats else 0,
        "date_min": stats.date_min if stats else "",
        "date_max": stats.date_max if stats else "",
        "cutoff_date": analysis_config.get("cutoff_date"),
    }


def _db_path(project_id: str) -> Path:
    from discoursekit.config import get_projects_dir

    return get_projects_dir() / project_id / "project.db"


def _compute_stats(project_id: str):
    try:
        from discoursekit.analyze.descriptive import compute_descriptive

        return compute_descriptive(_db_path(project_id), project_id)
    except Exception as exc:
        st.error(f"개요 분석 실패: {exc}")
        return None


def _add_time_series_annotations(fig, ts, config: dict) -> None:
    if not ts.total_counts:
        return
    mean_count = sum(ts.total_counts) / len(ts.total_counts)
    peak_idx = max(range(len(ts.total_counts)), key=lambda idx: ts.total_counts[idx])
    peak_period = ts.periods[peak_idx]
    peak_count = ts.total_counts[peak_idx]
    if mean_count > 0:
        fig.add_hline(
            y=mean_count,
            line_dash="dash",
            line_color="#64748b",
            annotation_text=f"Average {mean_count:.0f}",
        )
    if mean_count > 0 and peak_count >= mean_count * 2:
        fig.add_annotation(
            x=peak_period,
            y=peak_count,
            text=f"Peak {peak_count:,}",
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-35,
        )
    cutoff = config.get("cutoff_date")
    if cutoff:
        fig.add_vline(
            x=str(cutoff)[:7],
            line_dash="dot",
            line_color="#dc2626",
            annotation_text="Cutoff",
        )


def _project_source_depth(project_id: str) -> str:
    try:
        from discoursekit.core.db import get_connection

        conn = get_connection(_db_path(project_id))
        row = conn.execute(
            """
            SELECT source FROM articles
            WHERE project_id = ?
            GROUP BY source
            ORDER BY COUNT(*) DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        conn.close()
        if row and row["source"] in {"naver_news", "naver_blog"}:
            return "excerpt_only"
    except Exception:
        pass
    return "full_body"


def _peak_evidence(project_id: str, ts, config: dict) -> list[dict]:
    if not ts.total_counts:
        return []
    peak_idx = max(range(len(ts.total_counts)), key=lambda idx: ts.total_counts[idx])
    return _article_rows(
        project_id,
        where="AND SUBSTR(date, 1, 7) = ?",
        params=[ts.periods[peak_idx]],
        reason=f"peak period {ts.periods[peak_idx]}",
    )


def _keyword_evidence(project_id: str, keywords: list[tuple[str, int]]) -> list[dict]:
    evidence = []
    for keyword, _ in keywords:
        evidence.extend(
            _article_rows(
                project_id,
                where="AND (title LIKE ? OR body_excerpt LIKE ?)",
                params=[f"%{keyword}%", f"%{keyword}%"],
                reason=f"contains keyword '{keyword}'",
                limit=1,
            )
        )
    return evidence


def _trend_evidence(project_id: str, result) -> list[dict]:
    targets = []
    if result.new_entries:
        targets.append(result.new_entries[0][0])
    if result.risers:
        targets.append(result.risers[0][0])
    return _keyword_evidence(project_id, [(keyword, 1) for keyword in targets])


def _publisher_evidence(project_id: str, publishers: list[tuple[str, int]]) -> list[dict]:
    evidence = []
    for publisher, _ in publishers:
        evidence.extend(
            _article_rows(
                project_id,
                where="AND COALESCE(NULLIF(publisher, ''), 'unknown') = ?",
                params=[publisher],
                reason=f"top source {publisher}",
                limit=1,
            )
        )
    return evidence


def _cutoff_evidence(project_id: str, cutoff: str) -> list[dict]:
    return _article_rows(
        project_id,
        where="AND date >= ?",
        params=[cutoff],
        reason=f"on or after cutoff {cutoff}",
        limit=3,
    )


def _article_rows(
    project_id: str,
    where: str,
    params: list[Any],
    reason: str,
    limit: int = 3,
) -> list[dict]:
    try:
        from discoursekit.core.db import get_connection

        conn = get_connection(_db_path(project_id))
        rows = conn.execute(
            f"""
            SELECT article_id, title, date, publisher
            FROM articles
            WHERE project_id = ? AND is_active = 1
            {where}
            ORDER BY date DESC, article_id
            LIMIT ?
            """,
            (project_id, *params, limit),
        ).fetchall()
        conn.close()
        return [
            {
                "article_id": row["article_id"],
                "title": row["title"],
                "date": row["date"],
                "publisher": row["publisher"] or "",
                "reason": reason,
            }
            for row in rows
        ]
    except Exception:
        return []


def _render_keyword_distribution_summary(result) -> None:
    stats = getattr(result, "frequency_stats", {}) or {}
    st.markdown("#### 키워드 빈도 분포")
    cols = _responsive_columns(4)
    cols[0].metric("추출 키워드", f"{result.unique_tokens:,}")
    cols[1].metric("핵심 구간", f"{len(getattr(result, 'core_keywords', []) or []):,}")
    cols[2].metric("평균 빈도", stats.get("mean", 0))
    cols[3].metric("상위 집중도", f"{getattr(result, 'concentration', 0):.1f}%")
    st.caption(
        "핵심 구간은 평균+표준편차 이상 등장한 키워드입니다. "
        "LLM 해석 전에 Python 통계로 먼저 분포를 확인합니다."
    )


def _render_keyword_llm_panel(project_id: str, result, config: dict) -> None:
    with st.expander("LLM 제안: 키워드 의미 묶기", expanded=False):
        st.caption(
            "버튼을 누를 때만 LLM/휴리스틱 해석을 생성합니다. 결과는 제안이며 연구자가 수정해야 합니다."
        )
        topic = st.text_input(
            "연구 주제",
            value=str(config.get("research_topic") or config.get("query") or ""),
            key=f"keyword_topic_{project_id}",
        )
        manual_focus = st.text_input(
            "관심 키워드",
            value=", ".join(keyword for keyword, _ in result.keywords[:5]),
            key=f"keyword_focus_{project_id}",
        )
        if st.button("LLM 키워드 해석 요청", key=f"keyword_llm_{project_id}"):
            from discoursekit.llm.keyword_advisor import analyze_keywords

            api_key = _get_interactive_api_key()
            grouping = analyze_keywords(
                topic,
                result.keywords[:50],
                article_count=int(config.get("active_count", 0) or 0),
                api_key=api_key,
            )
            st.session_state[f"keyword_grouping_{project_id}"] = grouping
        grouping = st.session_state.get(f"keyword_grouping_{project_id}")
        if not grouping:
            return
        st.markdown("**의미 그룹 제안**")
        st.dataframe(grouping.groups, use_container_width=True, hide_index=True)
        st.markdown("**주제 적합성 제안**")
        st.write(
            {
                "core": grouping.topic_core,
                "related": grouping.topic_related,
                "off_topic": grouping.topic_off,
                "focus": [item.strip() for item in manual_focus.split(",") if item.strip()],
            }
        )
        if grouping.noise_candidates:
            st.markdown("**노이즈 후보**")
            st.dataframe(grouping.noise_candidates, use_container_width=True, hide_index=True)
        st.info(grouping.summary)


def _render_keyword_change_llm_panel(project_id: str, result, config: dict) -> None:
    with st.expander("LLM 제안: 전후 키워드 변화 해석", expanded=False):
        st.caption("버튼을 눌러야 LLM/휴리스틱 해석을 생성합니다.")
        topic = st.text_input(
            "연구 주제",
            value=str(config.get("research_topic") or config.get("query") or ""),
            key=f"kw_change_topic_{project_id}",
        )
        if st.button("LLM 변화 해석 요청", key=f"kw_change_llm_{project_id}"):
            from discoursekit.llm.keyword_advisor import interpret_keyword_change

            api_key = _get_interactive_api_key()
            interpretation = interpret_keyword_change(
                topic,
                result.before_keywords[:20],
                result.after_keywords[:20],
                result.cutoff_date,
                api_key=api_key,
            )
            st.session_state[f"kw_change_interp_{project_id}"] = interpretation

        interp = st.session_state.get(f"kw_change_interp_{project_id}")
        if not interp:
            return

        st.markdown("**변화 해석**")
        st.info(interp.interpretation)
        if interp.emerged:
            st.markdown("**새로 등장한 키워드**")
            st.dataframe(interp.emerged, use_container_width=True, hide_index=True)
        if interp.disappeared:
            st.markdown("**사라진 키워드**")
            st.dataframe(interp.disappeared, use_container_width=True, hide_index=True)
        if interp.shifted:
            st.markdown("**빈도 변화 키워드**")
            st.dataframe(interp.shifted, use_container_width=True, hide_index=True)
        st.markdown(f"**담론 전환 요약**: {interp.discourse_shift}")

        feedback = st.text_input("수정 의견", key=f"kw_change_feedback_{project_id}")
        if st.button("수정 반영", key=f"kw_change_revise_{project_id}") and feedback.strip():
            st.caption("키워드 변화 해석은 전체 키워드 분석 탭에서 수정 반영할 수 있습니다.")


def _detect_peak(config: dict) -> dict | None:
    """Detect the month with maximum article count from time series."""
    try:
        from discoursekit.analyze.time_series import compute_monthly

        project_id = config.get("project_id", "")
        if not project_id:
            return None
        ts = compute_monthly(_db_path(project_id), project_id)
        if not ts.periods or not ts.total_counts:
            return None
        max_idx = max(range(len(ts.total_counts)), key=lambda i: ts.total_counts[i])
        mean_count = sum(ts.total_counts) / len(ts.total_counts)
        peak_count = ts.total_counts[max_idx]
        if peak_count < mean_count * 2:
            return None
        return {"period": ts.periods[max_idx], "count": peak_count}
    except Exception:
        return None


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


def _split_terms(text: str) -> list[str]:
    import re

    return [term.strip().lower() for term in re.split(r"[\s,;/|]+", text or "") if term.strip()]


def _project_display_name(project_id: str) -> str:
    try:
        from discoursekit.core.db import get_connection

        conn = get_connection(_db_path(project_id))
        row = conn.execute(
            "SELECT name FROM projects WHERE project_id = ?", (project_id,),
        ).fetchone()
        conn.close()
        if row and row["name"]:
            return row["name"]
    except Exception:
        pass
    return project_id


def _source_depth_label(value: str) -> str:
    if value == "excerpt_only":
        return "요약문"
    if value == "full_body":
        return "전문 포함"
    return value or "-"
