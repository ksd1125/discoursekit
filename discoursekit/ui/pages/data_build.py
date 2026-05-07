"""Data build page: collect, clean, and summarize a corpus."""

from __future__ import annotations

import re
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from discoursekit.ui.components import metric_row, page_header


def _split_date_range_monthly(date_from: str | None, date_to: str | None) -> list[tuple[str, str]]:
    """Split a date range into monthly chunks.

    Returns list of (start, end) pairs like [("2025-01-01","2025-01-31"), ...].
    If dates are missing or invalid, returns a single chunk with the originals.
    """
    if not date_from or not date_to:
        return [(date_from or "", date_to or "")]
    try:
        d_from = date.fromisoformat(date_from)
        d_to = date.fromisoformat(date_to)
    except ValueError:
        return [(date_from, date_to)]
    if d_from >= d_to:
        return [(date_from, date_to)]

    chunks: list[tuple[str, str]] = []
    cursor = d_from
    while cursor <= d_to:
        if cursor.month == 12:
            month_end = date(cursor.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(cursor.year, cursor.month + 1, 1) - timedelta(days=1)
        chunk_end = min(month_end, d_to)
        chunks.append((cursor.isoformat(), chunk_end.isoformat()))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def render() -> None:
    page_header(
        "데이터 만들기",
        "수집 조건을 확인한 뒤 자료 수집, 정제, 기본 개요 생성을 한 번에 실행합니다.",
    )
    config = st.session_state.get("analysis_config")
    project_id = st.session_state.get("current_project_id") or (config or {}).get("project_id")

    if not project_id:
        st.info("홈에서 분석 주제와 검색어를 먼저 입력하세요.")
        if st.button("홈으로 이동"):
            st.session_state["nav_page"] = "홈"
            st.rerun()
        return

    if not config:
        st.info(
            "현재 프로젝트에는 수집 조건이 없습니다. BIGKinds 또는 CSV 파일을 업로드해서 데이터를 추가할 수 있습니다."
        )
        _render_manual_upload(project_id)
        return

    _render_config_summary(config)
    sources = config.get("sources", [])

    naver_sources = [s for s in sources if s.startswith("naver_")]
    if naver_sources or "naver_news" in sources:
        _render_naver_run(project_id, config)

    st.markdown("---")
    _render_place_review_run(project_id, config)

    file_sources = [source for source in sources if source in {"bigkinds", "csv"}]
    if file_sources:
        st.markdown("---")
        _render_file_upload_runs(project_id, config, file_sources)

    _render_last_summary()


def _render_config_summary(config: dict) -> None:
    st.markdown("#### 수집 조건")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("검색어", config.get("query", "-"))
    with col2:
        st.metric("기간", f"{config.get('date_from')} ~ {config.get('date_to')}")
    with col3:
        st.metric("자료원", ", ".join(config.get("sources", [])))

    if "naver_news" in config.get("sources", []):
        st.caption(
            "NAVER News는 제목과 요약문만 제공하는 자료입니다. "
            "추이, 출처 분포, 키워드 개요에는 적합하지만 전문 기반 정성 분석에는 제한이 있습니다."
        )


_NAVER_CHANNEL_OPTIONS: list[tuple[str, str]] = [
    ("naver_news", "뉴스"),
    ("naver_blog", "블로그"),
    ("naver_cafe", "카페"),
    ("naver_web", "웹문서"),
]


def _render_naver_run(project_id: str, config: dict) -> None:
    st.markdown("#### NAVER 자동 수집")
    from discoursekit.ui.env_keys import load_naver_keys

    keys = load_naver_keys()
    client_id = keys.get("NAVER_CLIENT_ID", "")
    client_secret = keys.get("NAVER_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        st.warning(
            "NAVER API Client ID와 Client Secret이 필요합니다. 설정 화면에서 먼저 저장하세요."
        )
        st.markdown(
            "[NAVER Developers](https://developers.naver.com)에서 애플리케이션을 등록하고 "
            "검색 API를 사용하도록 설정하면 발급받을 수 있습니다."
        )
        if st.button("설정으로 이동", key="go_settings_naver"):
            st.session_state["nav_page"] = "설정"
            st.rerun()
        return
    if client_id == client_secret:
        st.error(
            "NAVER Client ID와 Client Secret이 같은 값으로 저장되어 있습니다. "
            "NAVER Developers에서 Client ID와 Client Secret을 각각 확인해 다시 저장하세요."
        )
        if st.button("설정으로 이동", key="go_settings_naver_same_key"):
            st.session_state["nav_page"] = "설정"
            st.rerun()
        return

    st.markdown("##### 채널 선택")
    st.caption("같은 키워드를 여러 채널에서 수집하면 채널별 담론 차이를 비교할 수 있습니다.")
    channel_cols = st.columns(len(_NAVER_CHANNEL_OPTIONS))
    selected_channels: list[str] = []
    for idx, (channel_key, channel_label) in enumerate(_NAVER_CHANNEL_OPTIONS):
        default_on = channel_key == "naver_news"
        with channel_cols[idx]:
            if st.checkbox(channel_label, value=default_on, key=f"ch_{channel_key}_{project_id}"):
                selected_channels.append(channel_key)

    if not selected_channels:
        st.info("수집할 채널을 하나 이상 선택하세요.")
        return

    from discoursekit.config import get_projects_dir
    from discoursekit.core.db import count_articles, get_connection, init_db

    db_path = get_projects_dir() / project_id / "project.db"
    existing_count = 0
    if db_path.exists():
        _conn = get_connection(db_path)
        try:
            existing_count = count_articles(_conn, project_id)
        finally:
            _conn.close()

    date_from = config.get("date_from", "")
    date_to = config.get("date_to", "")
    monthly_chunks = _split_date_range_monthly(date_from, date_to)
    max_results = 1000

    if existing_count > 0:
        st.info(f"이미 수집된 자료: **{existing_count:,}건**. 추가 수집 시 기존 자료에 누적됩니다 (중복 자동 제외).")

    channel_names = ", ".join(ch for _, ch in _NAVER_CHANNEL_OPTIONS if _ in selected_channels)
    if len(monthly_chunks) > 1:
        st.caption(
            f"검색어 '{config.get('query')}'로 {channel_names}에서 수집합니다. "
            f"기간을 **{len(monthly_chunks)}개 월**로 분할하여 월별 최대 1,000건씩 수집합니다. "
            "이미 수집된 자료와 중복되는 건은 자동으로 건너뜁니다."
        )
    else:
        st.caption(
            f"검색어 '{config.get('query')}'로 {channel_names}에서 "
            "채널당 최대 1,000건을 수집합니다. 기존 자료에 누적됩니다."
        )

    with st.expander("고급 수집 설정", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            display = st.number_input(
                "1회 요청 건수",
                min_value=10,
                max_value=100,
                value=100,
                step=10,
                help="NAVER API가 한 번에 가져오는 건수입니다. 기본값은 100건입니다.",
            )
        with col2:
            sort = st.selectbox(
                "정렬",
                ["date", "sim"],
                format_func=lambda value: "최신순" if value == "date" else "관련도순",
            )

    if st.button("NAVER 수집 및 정제 시작", type="primary", key="run_naver_auto"):
        from discoursekit.workflow.auto_pipeline import CleanConfig, SourceConfig, run_collect_clean_overview

        progress_bar = st.progress(0.0)
        status_text = st.empty()
        started_at = time.time()
        total_raw = 0
        total_active = 0
        last_summary = None

        total_steps = len(selected_channels) * len(monthly_chunks)
        step = 0

        for ch_idx, channel in enumerate(selected_channels):
            channel_label = dict(_NAVER_CHANNEL_OPTIONS).get(channel, channel)

            for chunk_idx, (chunk_from, chunk_to) in enumerate(monthly_chunks):
                step += 1
                chunk_label = chunk_from[:7] if chunk_from else ""

                def on_progress(message: str, label=channel_label, period=chunk_label) -> None:
                    prefix = f"[{label}]" if not period else f"[{label} {period}]"
                    _update_progress(progress_bar, status_text, f"{prefix} {message}", started_at)

                try:
                    summary = run_collect_clean_overview(
                        project_id=project_id,
                        source_config=SourceConfig(
                            source_type=channel,
                            query=config["query"],
                            date_from=chunk_from or None,
                            date_to=chunk_to or None,
                            display=int(display),
                            sort=sort,
                            max_results=int(max_results),
                            client_id=client_id,
                            client_secret=client_secret,
                        ),
                        clean_config=CleanConfig(),
                        db_path=db_path,
                        progress_callback=on_progress,
                    )
                    total_raw += summary.raw_count
                    total_active += summary.active_count
                    last_summary = summary
                except Exception as exc:
                    st.warning(f"[{channel_label} {chunk_label}] 수집 실패: {exc}")

                progress_bar.progress(step / total_steps)

        progress_bar.progress(1.0)

        final_count = 0
        if db_path.exists():
            _conn = get_connection(db_path)
            try:
                final_count = count_articles(_conn, project_id)
            finally:
                _conn.close()
        new_count = final_count - existing_count

        if last_summary:
            status_text.success(
                f"완료: {len(selected_channels)}개 채널 × {len(monthly_chunks)}개 월 / "
                f"신규 {new_count:,}건 추가 (총 {final_count:,}건)"
            )
            st.session_state["last_workflow_summary"] = last_summary


def _render_place_review_run(project_id: str, config: dict) -> None:
    st.markdown("#### NAVER Place 리뷰 수집")
    st.caption(
        "업소 Place ID를 입력하면 해당 업소의 방문자 리뷰를 수집합니다. "
        "수집된 리뷰에서 메뉴명을 추출하여 업소·메뉴 관측 패널을 만듭니다."
    )

    place_input = st.text_area(
        "Place ID 목록 (한 줄에 place_id,업소명)",
        placeholder="1852279382,다이소 이태원점\n37814859,이태원 부대찌개",
        height=120,
        key=f"place_ids_{project_id}",
    )

    with st.expander("수집 설정", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            max_pages = st.number_input(
                "업소당 최대 페이지",
                min_value=1, max_value=50, value=10,
                help="1페이지 = 약 20건 리뷰",
            )
        with col2:
            stop_month = st.text_input(
                "수집 종료 월 (이 월까지만)",
                value="2020-01",
                help="이 월 이전 리뷰에 도달하면 수집을 중단합니다.",
            )

    if st.button("Place 리뷰 수집 시작", type="primary", key=f"run_place_{project_id}"):
        lines = [l.strip() for l in place_input.strip().splitlines() if l.strip()]
        if not lines:
            st.warning("Place ID를 입력하세요.")
            return

        from discoursekit.ingest.naver_place import PlaceTarget, collect_place_reviews
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import init_db, insert_place_review

        targets = []
        for line in lines:
            parts = line.split(",", 1)
            pid = parts[0].strip()
            pname = parts[1].strip() if len(parts) > 1 else pid
            targets.append(PlaceTarget(place_id=pid, place_name=pname))

        progress_bar = st.progress(0.0)
        status_text = st.empty()
        started_at = time.time()
        count = 0

        db_path = get_projects_dir() / project_id / "project.db"
        conn = init_db(db_path)
        from discoursekit.core.db import count_place_reviews
        existing_count = count_place_reviews(conn, project_id)
        if existing_count:
            st.info(f"이미 수집된 리뷰: {existing_count:,}건 (중복은 자동 무시)")
        try:
            for row in collect_place_reviews(
                project_id=project_id,
                places=targets,
                max_pages_per_place=int(max_pages),
                stop_month=stop_month,
                progress_callback=lambda msg: status_text.info(
                    f"{msg} / 경과 {time.time() - started_at:.0f}초"
                ),
            ):
                insert_place_review(conn, {
                    "review_id": row.review_id,
                    "project_id": row.project_id,
                    "place_id": row.place_id,
                    "place_name": row.place_name,
                    "review_month": row.review_month,
                    "body": row.body,
                    "voted_keywords": row.voted_keywords,
                    "menu_item": row.menu_item,
                    "origin_type": row.origin_type,
                    "raw_json": row.raw_json,
                    "collected_at": row.collected_at,
                })
                count += 1
                if count % 20 == 0:
                    conn.commit()
                    progress_bar.progress(min(count / (len(targets) * int(max_pages) * 20), 0.95))
            conn.commit()
        except Exception as exc:
            st.error(f"수집 실패: {exc}")
        finally:
            conn.close()

        progress_bar.progress(1.0)
        final_count = count_place_reviews(conn, project_id)
        new_count = final_count - existing_count
        elapsed = time.time() - started_at
        status_text.success(
            f"완료: {len(targets)}개 업소 / 신규 {new_count:,}건 추가 (총 {final_count:,}건) / 경과 {elapsed:.0f}초"
        )


def _render_file_upload_runs(project_id: str, config: dict, file_sources: list[str]) -> None:
    st.markdown("#### 파일 업로드 수집")
    selected = st.selectbox(
        "업로드 자료원",
        file_sources,
        format_func=lambda value: "BIGKinds XLSX" if value == "bigkinds" else "CSV",
    )
    if selected == "bigkinds":
        st.info(
            "BIGKinds에서 내려받은 XLSX 파일을 업로드합니다. 기사 전문이 포함되어 있으면 정성 분석에 더 적합합니다."
        )
    else:
        st.info("CSV는 `date`, `title`, `body` 열이 필요합니다. `publisher`, `keywords`, `url`은 선택입니다.")

    file_types = ["xlsx", "xls"] if selected == "bigkinds" else ["csv"]
    uploaded = st.file_uploader("파일 선택", type=file_types, accept_multiple_files=True)

    if not uploaded:
        return

    if st.button("업로드 및 정제 시작", type="primary", key=f"run_upload_{selected}"):
        from discoursekit.config import get_projects_dir
        from discoursekit.workflow.auto_pipeline import CleanConfig, SourceConfig, run_collect_clean_overview

        summaries = []
        progress_bar = st.progress(0.0)
        status_text = st.empty()
        started_at = time.time()
        for idx, file in enumerate(uploaded, start=1):
            suffix = Path(file.name).suffix or f".{file_types[0]}"
            tmp_path = None
            try:
                status_text.info(f"{file.name}: 임시 파일을 준비하고 있습니다.")
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(file.getvalue())
                    tmp_path = Path(tmp.name)
                summary = run_collect_clean_overview(
                    project_id=project_id,
                    source_config=SourceConfig(
                        source_type=selected,
                        input_path=tmp_path,
                        query=config.get("query"),
                        date_from=config.get("date_from"),
                        date_to=config.get("date_to"),
                    ),
                    clean_config=CleanConfig(),
                    db_path=get_projects_dir() / project_id / "project.db",
                    progress_callback=lambda msg, name=file.name: status_text.info(f"{name}: {msg}"),
                )
                summaries.append(summary)
                progress_bar.progress(idx / len(uploaded))
            except Exception as exc:
                st.error(f"{file.name} 처리 실패: {exc}")
            finally:
                if tmp_path is not None:
                    tmp_path.unlink(missing_ok=True)
        elapsed = time.time() - started_at
        if summaries:
            st.session_state["last_workflow_summary"] = summaries[-1]
            status_text.success(f"{len(summaries)}개 파일 처리 완료 / 경과 {elapsed:.0f}초")


def _render_manual_upload(project_id: str) -> None:
    config = {
        "project_id": project_id,
        "query": "",
        "date_from": None,
        "date_to": None,
        "sources": ["bigkinds"],
    }
    _render_file_upload_runs(project_id, config, ["bigkinds", "csv"])


def _render_last_summary() -> None:
    summary = st.session_state.get("last_workflow_summary")
    if not summary:
        return

    st.markdown("---")
    st.markdown("#### 결과 요약")
    metric_row(
        [
            ("수집", summary.raw_count, ""),
            ("분석 가능", summary.active_count, ""),
            ("제외", summary.dropped_count, ""),
            ("출처 수", summary.publisher_count, ""),
        ]
    )
    st.caption(
        "수집: 자료원에서 가져온 전체 기사 / "
        "분석 가능: 중복과 짧은 글 등을 정리한 뒤 남은 기사 / "
        "제외: 정제 과정에서 빠진 기사 / "
        "출처 수: 분석 가능 기사에 포함된 언론사 또는 매체 수"
    )
    st.caption(
        f"기간: {summary.date_min or '-'} ~ {summary.date_max or '-'} / "
        f"자료 깊이: {_source_depth_label(summary.source_depth)}"
    )
    if summary.keyword_top_n:
        st.markdown("주요 키워드")
        st.write(", ".join(f"{word}({count})" for word, count in summary.keyword_top_n[:10]))

    st.markdown("#### 다음 단계")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**1. 분석 대시보드**")
        st.caption("보도량 추이, 키워드, 출처 분포를 확인합니다.")
        if st.button("분석 대시보드로 이동", key="go_analyze_after_build"):
            st.session_state["nav_page"] = "분석 대시보드"
            st.rerun()
    with col2:
        st.markdown("**2. LLM 보정**")
        st.caption("관련성 후보, 의미 태그, 표준화 후보를 만들고 사람이 검토합니다.")
        if st.button("LLM 보정으로 이동", key="go_llm_after_build"):
            st.session_state["nav_page"] = "LLM 보정"
            st.rerun()
    with col3:
        st.markdown("**3. 정성 분석**")
        st.caption("코드북을 만들고 기사별로 질적 코딩을 진행합니다.")
        if st.button("정성 분석으로 이동", key="go_qual_after_build"):
            st.session_state["nav_page"] = "정성 분석"
            st.rerun()


def _update_progress(progress_bar, status_text, message: str, started_at: float) -> None:
    match = re.search(r"(\d+)\s*/\s*(\d+)", message)
    elapsed = time.time() - started_at
    if match:
        current, total = int(match.group(1)), int(match.group(2))
        ratio = min(current / total, 1.0) if total else 0.0
        progress_bar.progress(ratio)
        eta = elapsed / current * (total - current) if current else 0.0
        status_text.info(f"{message} / 경과 {elapsed:.0f}초 / 남은 예상 {eta:.0f}초")
    elif "정제" in message:
        progress_bar.progress(0.8)
        status_text.info(f"{message} / 경과 {elapsed:.0f}초")
    elif "요약" in message:
        progress_bar.progress(0.9)
        status_text.info(f"{message} / 경과 {elapsed:.0f}초")
    else:
        progress_bar.progress(0.15)
        status_text.info(f"{message} / 경과 {elapsed:.0f}초")


def _source_depth_label(value: str) -> str:
    if value == "excerpt_only":
        return "요약문만 제공"
    if value == "full_body":
        return "전문 포함"
    return value or "-"
