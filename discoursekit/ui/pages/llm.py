"""LLM classification page — Gemini slot management and classification runs."""

import asyncio

import streamlit as st
from discoursekit.ui.components import (
    page_header, section_header, metric_row, empty_state,
    job_status_badge,
)


def render():
    page_header("3. LLM 분류", "Gemini API를 사용해 기사를 자동 분류합니다.")

    project_id = st.session_state.get("current_project_id")
    if not project_id:
        empty_state("먼저 프로젝트를 선택하세요.", "📂")
        return

    tab_classify, tab_slots, tab_jobs = st.tabs(["🏷️ 분류 실행", "🔑 API 슬롯", "📋 작업 이력"])

    with tab_classify:
        _render_classify_tab(project_id)
    with tab_slots:
        _render_slots_tab()
    with tab_jobs:
        _render_jobs_tab(project_id)


def _render_classify_tab(project_id: str):
    section_header("분류 설정", "🏷️")

    # Check prerequisites
    stats = _load_stats(project_id)
    if stats["active"] == 0:
        empty_state("정제된 기사가 없습니다. 먼저 '정제' 단계를 완료하세요.", "⬅️")
        return

    metric_row([
        ("Active 기사", stats["active"], ""),
        ("이미 분류됨", stats["classified"], ""),
        ("미분류", stats["active"] - stats["classified"], ""),
    ])

    st.markdown("---")

    # Classification config
    col1, col2 = st.columns(2)
    with col1:
        provider = st.selectbox("LLM 공급자", ["gemini", "claude (v0.2)", "openai (v0.2)"])
        model = st.text_input("모델명", value="gemini-2.5-flash")
        temperature = st.slider("Temperature", 0.0, 1.0, 0.0, 0.1, help="재현성을 위해 0.0 권장")

    with col2:
        sample_size = st.number_input("분류 건수 (0=전체)", value=0, min_value=0)
        schema_id = st.text_input("라벨 스키마 ID", value="relevance_v1",
                                   help="label_schemas 테이블에 등록된 schema_id")
        prompt_version = st.text_input("프롬프트 버전 ID", value="relevance_v1.0")

    # Prompt preview
    with st.expander("프롬프트 미리보기"):
        prompt_text = st.text_area(
            "프롬프트 텍스트",
            value=_get_default_prompt(),
            height=200,
            help="이 프롬프트가 각 기사 앞에 붙어 LLM에 전송됩니다.",
        )

    # Resume option
    st.markdown("---")
    resume_job = st.text_input("Resume Job ID (선택)", value="",
                                help="이전 작업을 이어서 실행할 때 job_id를 입력하세요.")

    st.markdown("---")

    # Warning
    st.warning(
        "⚠️ **API 호출 비용이 발생합니다.** "
        f"예상 건수: {stats['active'] - stats['classified']}건. "
        "Gemini Flash 기준 약 $0.15/1M input tokens."
    )

    if st.button("분류 시작", type="primary", key="btn_classify"):
        provider_id = provider.split(" ")[0]
        if provider_id != "gemini":
            st.error("MVP에서는 Gemini provider만 실제 실행됩니다.")
            return

        slot_manager = _build_gemini_slot_manager()
        if slot_manager.slot_count == 0:
            st.error("Gemini API 슬롯을 먼저 저장하세요. 최소 1개 key가 필요합니다.")
            return

        progress_bar = st.progress(0)
        progress_text = st.empty()

        def on_progress(progress):
            progress_bar.progress(min(progress.pct / 100.0, 1.0))
            progress_text.caption(
                f"{progress.processed}/{progress.total}건 처리 | "
                f"errors={progress.errors} | cost=${progress.estimated_cost_usd:.4f}"
            )

        with st.spinner("분류 실행 중... 장시간 소요될 수 있습니다."):
            try:
                from discoursekit.config import get_projects_dir
                from discoursekit.llm.classifier import ClassifyConfig, run_classification

                db_path = get_projects_dir() / project_id / "project.db"
                config = ClassifyConfig(
                    project_id=project_id,
                    schema_id=schema_id,
                    prompt_version_id=prompt_version,
                    prompt_text=prompt_text,
                    provider=provider_id,
                    model=model,
                    temperature=temperature,
                    sample_size=int(sample_size) if sample_size else 0,
                    resume_job_id=resume_job.strip() or None,
                )
                job_id = asyncio.run(
                    run_classification(
                        config,
                        db_path,
                        slot_manager=slot_manager,
                        progress_callback=on_progress,
                    )
                )
                summary = _load_job_summary(project_id, job_id)
                st.success(
                    f"✅ 분류 완료! job_id: `{job_id}` | "
                    f"처리: {summary['n_processed']}건 | "
                    f"비용: ${summary['estimated_cost_usd']:.4f}"
                )
                st.rerun()
            except Exception as e:
                st.error(f"분류 실패: {e}")

    # ─── CTA ───
    st.markdown("---")
    if st.button("분류 완료 → 분석·리포트로 이동", key="cta_llm_to_analyze"):
        st.session_state["nav_page"] = "4. 분석·리포트"
        st.rerun()


def _render_slots_tab():
    section_header("Gemini API 슬롯 관리", "🔑")

    _ensure_gemini_keys_loaded()

    st.markdown("""
    💡 **효과적인 rotation을 위해 각 키는 다른 Google Cloud 프로젝트에서 발급받으세요.**
    같은 프로젝트의 여러 키는 quota를 공유합니다.
    """)

    # Slot inputs
    for i in range(1, 4):
        with st.expander(f"슬롯 {i}", expanded=(i == 1)):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.text_input(
                    f"🔑 Gemini Key {i}",
                    type="password",
                    key=f"gemini_key_{i}",
                    help="Google Cloud 프로젝트별로 서로 다른 키를 사용하면 quota가 독립됩니다.",
                )
            with col2:
                st.markdown("<br>", unsafe_allow_html=True)
                st.checkbox("활성", value=True, key=f"slot_{i}_enabled")

            col_rpm, col_tpm, col_rpd = st.columns(3)
            with col_rpm:
                st.number_input("RPM", value=15, key=f"slot_{i}_rpm", help="분당 요청 한도")
            with col_tpm:
                st.number_input("TPM", value=1000000, key=f"slot_{i}_tpm", help="분당 토큰 한도")
            with col_rpd:
                st.number_input("RPD", value=1500, key=f"slot_{i}_rpd", help="일일 요청 한도")

    if st.button("슬롯 저장", key="btn_save_slots"):
        try:
            from discoursekit.ui.env_keys import save_gemini_keys

            keys = {
                i: st.session_state.get(f"gemini_key_{i}", "")
                for i in range(1, 4)
            }
            env_path = save_gemini_keys(keys)
            st.success(f"✅ 슬롯이 `{env_path}`에 저장되었습니다.")
        except Exception as e:
            st.error(f"슬롯 저장 실패: {e}")

    st.markdown("---")
    st.caption("💡 RPD(일일 한도)는 Pacific Time 자정(한국시간 오후 4~5시)에 리셋됩니다.")


def _render_jobs_tab(project_id: str):
    section_header("LLM 작업 이력", "📋")
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection
        db_path = get_projects_dir() / project_id / "project.db"
        conn = get_connection(db_path)
        jobs = conn.execute(
            "SELECT job_id, provider, model, status, n_processed, sample_size, "
            "started_at, estimated_cost_usd FROM llm_jobs "
            "WHERE project_id=? ORDER BY started_at DESC",
            (project_id,),
        ).fetchall()
        conn.close()

        if not jobs:
            empty_state("아직 분류 작업이 없습니다.", "📋")
            return

        for job in jobs:
            j = dict(job)
            badge = job_status_badge(j["status"])
            st.markdown(
                f"{badge} **{j['provider']}/{j['model']}** — "
                f"{j['n_processed']}/{j['sample_size']}건 | "
                f"${j['estimated_cost_usd']:.4f} | {j['started_at'][:16]}",
                unsafe_allow_html=True,
            )
            if j["status"] in ("cancelled", "failed"):
                st.caption(f"  Resume 가능: `{j['job_id']}`")
    except Exception as e:
        st.error(f"이력 조회 실패: {e}")


def _load_stats(project_id: str) -> dict:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection
        db_path = get_projects_dir() / project_id / "project.db"
        conn = get_connection(db_path)
        active = conn.execute("SELECT COUNT(*) AS n FROM articles WHERE project_id=? AND is_active=1", (project_id,)).fetchone()["n"]
        classified = conn.execute(
            "SELECT COUNT(DISTINCT r.article_id) AS n FROM llm_results r "
            "JOIN articles a ON r.article_id=a.article_id "
            "WHERE a.project_id=? AND a.is_active=1",
            (project_id,),
        ).fetchone()["n"]
        conn.close()
        return {"active": active, "classified": classified}
    except Exception:
        return {"active": 0, "classified": 0}


def _ensure_gemini_keys_loaded() -> None:
    if st.session_state.get("gemini_keys_loaded"):
        return
    try:
        from discoursekit.ui.env_keys import load_gemini_keys

        saved = load_gemini_keys()
        for i in range(1, 4):
            st.session_state.setdefault(f"gemini_key_{i}", saved.get(i, ""))
        st.session_state["gemini_keys_loaded"] = True
    except Exception:
        for i in range(1, 4):
            st.session_state.setdefault(f"gemini_key_{i}", "")
        st.session_state["gemini_keys_loaded"] = True


def _build_gemini_slot_manager():
    _ensure_gemini_keys_loaded()
    from discoursekit.llm.slot_manager import GeminiProjectSlot, GeminiSlotManager

    manager = GeminiSlotManager()
    for i in range(1, 4):
        key = st.session_state.get(f"gemini_key_{i}", "").strip()
        enabled = bool(st.session_state.get(f"slot_{i}_enabled", True))
        if not key or not enabled:
            continue
        manager.add_slot(
            GeminiProjectSlot(
                slot_name=f"slot_{i}",
                api_key=key,
                rpm_quota=int(st.session_state.get(f"slot_{i}_rpm", 15)),
                tpm_quota=int(st.session_state.get(f"slot_{i}_tpm", 1_000_000)),
                rpd_quota=int(st.session_state.get(f"slot_{i}_rpd", 1500)),
                enabled=enabled,
            )
        )
    return manager


def _load_job_summary(project_id: str, job_id: str) -> dict:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection

        db_path = get_projects_dir() / project_id / "project.db"
        conn = get_connection(db_path)
        row = conn.execute(
            """
            SELECT n_processed, estimated_cost_usd
            FROM llm_jobs
            WHERE job_id = ? AND project_id = ?
            """,
            (job_id, project_id),
        ).fetchone()
        conn.close()
        if row:
            return {
                "n_processed": int(row["n_processed"] or 0),
                "estimated_cost_usd": float(row["estimated_cost_usd"] or 0.0),
            }
    except Exception:
        pass
    return {"n_processed": 0, "estimated_cost_usd": 0.0}


def _get_default_prompt() -> str:
    return """당신은 뉴스 기사 분류 전문가입니다. 아래 기사를 읽고 다음 JSON 형식으로 분류하세요.

응답 형식:
{"label": "<분류 라벨>", "confidence": <0.0~1.0>, "rationale": "<한 줄 근거>"}

분류 기준:
- relevant: 이태원 참사와 직접 관련된 보도
- irrelevant: 관련 없는 기사"""
