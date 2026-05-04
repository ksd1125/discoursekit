"""Home page — onboarding, project creation, and project dashboard."""

import streamlit as st
from discoursekit.ui.components import page_header, metric_row, empty_state, pipeline_progress


def render():
    project_id = st.session_state.get("current_project_id")

    if not project_id:
        _render_onboarding()
    else:
        _render_dashboard(project_id)


# ─────────────────────────────────────────────
# Onboarding (no project selected)
# ─────────────────────────────────────────────

def _render_onboarding():
    page_header("DiscourseKit", "뉴스·블로그·공공데이터 기반 담론 분석 워크벤치")

    st.markdown("")

    # ─── Primary actions ───
    col_new, col_open, col_import = st.columns(3)

    with col_new:
        st.markdown("""
        <div class="status-card" style="text-align:center;min-height:160px;">
            <div style="font-size:2.5rem;margin-bottom:0.5rem;">🆕</div>
            <h4 style="text-transform:none;font-size:1rem;">새 프로젝트 시작</h4>
            <p style="font-size:0.85rem;color:#6c757d;">연구 주제를 정하고 분석을 시작합니다</p>
        </div>
        """, unsafe_allow_html=True)

    with col_open:
        st.markdown("""
        <div class="status-card" style="text-align:center;min-height:160px;">
            <div style="font-size:2.5rem;margin-bottom:0.5rem;">📂</div>
            <h4 style="text-transform:none;font-size:1rem;">기존 프로젝트 열기</h4>
            <p style="font-size:0.85rem;color:#6c757d;">사이드바에서 프로젝트를 선택하세요</p>
        </div>
        """, unsafe_allow_html=True)

    with col_import:
        st.markdown("""
        <div class="status-card" style="text-align:center;min-height:160px;">
            <div style="font-size:2.5rem;margin-bottom:0.5rem;">📦</div>
            <h4 style="text-transform:none;font-size:1rem;">Handoff 가져오기</h4>
            <p style="font-size:0.85rem;color:#6c757d;">다른 PC에서 받은 zip을 import</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ─── Project creation form ───
    st.markdown("### 새 프로젝트 만들기")

    col1, col2 = st.columns(2)
    with col1:
        new_name = st.text_input("프로젝트 이름 *", placeholder="예: 이태원 담론 분석 2022")
    with col2:
        new_keywords = st.text_input("키워드 (선택)", placeholder="예: 이태원, 참사, 안전")

    new_desc = st.text_area(
        "연구 목적 / 설명 (선택)",
        placeholder="분석 범위, 연구 질문 등을 자유롭게 기술하세요.",
        height=80,
    )

    if st.button("프로젝트 생성", type="primary", key="btn_create_home"):
        if not new_name.strip():
            st.error("프로젝트 이름을 입력하세요.")
        else:
            _create_project(new_name.strip(), new_desc.strip())

    # ─── Handoff import ───
    st.markdown("---")
    st.markdown("### Handoff Import")
    st.caption("수집 PC에서 생성한 ingest-only handoff zip을 가져옵니다.")
    uploaded_zip = st.file_uploader("Handoff zip 파일", type=["zip"], key="home_import_zip")
    import_name = st.text_input("Import 프로젝트 이름 (비워두면 원래 이름 유지)", key="home_import_name")
    if uploaded_zip and st.button("Import 실행", key="btn_home_import"):
        from discoursekit.ui.pages.settings import _run_handoff_import

        _run_handoff_import(uploaded_zip, import_name)

    # ─── Workflow overview ───
    st.markdown("---")
    st.markdown("### 분석 워크플로우")
    st.markdown("""
    | 단계 | 설명 |
    |:---:|------|
    | **1. 수집** | BIGKinds XLSX, CSV 파일에서 기사를 수집합니다 |
    | **2. 정제** | 중복 제거, 단문 필터, 본문 정규화를 수행합니다 |
    | **3. LLM 분류** | Gemini API로 기사를 자동 분류합니다 (resume 지원) |
    | **4. 분석** | 기술통계, 시계열, 일치율 분석 및 보고서를 생성합니다 |

    > 향후 NAVER News API, 공공데이터포털 등 추가 수집원을 지원할 예정입니다.
    """)


# ─────────────────────────────────────────────
# Project Dashboard (project selected)
# ─────────────────────────────────────────────

def _render_dashboard(project_id: str):
    project_name = st.session_state.get("current_project_name", "")
    page_header(f"{project_name}", "프로젝트 대시보드")

    # Pipeline progress
    step = _get_current_step(project_id)
    pipeline_progress(step)

    st.markdown("---")

    # Metrics
    stats = _load_project_stats(project_id)
    metric_row([
        ("전체 기사", stats.get("total", 0), ""),
        ("Active 기사", stats.get("active", 0), ""),
        ("LLM 분류", stats.get("classified", 0), ""),
        ("산출물", stats.get("artifacts", 0), ""),
    ])

    # ─── Next step CTA ───
    st.markdown("---")
    st.markdown("#### 다음 작업")
    _render_next_step_cta(step)

    # Recent activity
    st.markdown("---")
    st.markdown("#### 최근 활동")
    activities = _load_recent_activity(project_id)
    if activities:
        for act in activities[:5]:
            st.markdown(f"- `{act['time']}` {act['action']}")
    else:
        st.caption("아직 활동 기록이 없습니다.")


def _render_next_step_cta(step: int):
    """Show a contextual call-to-action based on current pipeline stage."""
    cta_map = {
        0: ("아직 수집된 기사가 없습니다.", "📥 수집 페이지로 이동하여 데이터를 업로드하세요."),
        1: ("수집이 완료되었습니다.", "🧹 정제 페이지에서 중복 제거와 필터링을 실행하세요."),
        2: ("정제가 완료되었습니다.", "🤖 LLM 분류 페이지에서 API 설정 후 분류를 시작하세요."),
        3: ("LLM 분류가 완료되었습니다.", "📊 분석·리포트 페이지에서 결과를 확인하세요."),
        4: ("모든 단계가 완료되었습니다.", "📦 내보내기를 하거나 추가 분석을 수행할 수 있습니다."),
    }
    title, desc = cta_map.get(step, cta_map[0])
    st.info(f"**{title}** {desc}")


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _create_project(name: str, description: str):
    try:
        from discoursekit.core.project import Project
        proj = Project.create(name=name, description=description)
        st.success(f"프로젝트 '{name}' 생성 완료! (ID: {proj.project_id[:8]}...)")
        st.session_state["current_project_id"] = proj.project_id
        st.session_state["current_project_name"] = name
        st.rerun()
    except Exception as e:
        st.error(f"생성 실패: {e}")


def _get_current_step(project_id: str) -> int:
    """Determine which pipeline step the project is at."""
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection
        db_path = get_projects_dir() / project_id / "project.db"
        if not db_path.exists():
            return 0
        conn = get_connection(db_path)

        articles = conn.execute("SELECT COUNT(*) AS n FROM articles WHERE project_id=?", (project_id,)).fetchone()["n"]
        if articles == 0:
            conn.close()
            return 0

        cleans = conn.execute("SELECT COUNT(*) AS n FROM clean_runs WHERE project_id=? AND status='success'", (project_id,)).fetchone()["n"]
        if cleans == 0:
            conn.close()
            return 1

        jobs = conn.execute("SELECT COUNT(*) AS n FROM llm_jobs WHERE project_id=? AND status='success'", (project_id,)).fetchone()["n"]
        if jobs == 0:
            conn.close()
            return 2

        artifacts = conn.execute("SELECT COUNT(*) AS n FROM artifacts WHERE project_id=?", (project_id,)).fetchone()["n"]
        conn.close()
        return 4 if artifacts > 0 else 3
    except Exception:
        return 0


def _load_project_stats(project_id: str) -> dict:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection
        db_path = get_projects_dir() / project_id / "project.db"
        if not db_path.exists():
            return {}
        conn = get_connection(db_path)
        total = conn.execute("SELECT COUNT(*) AS n FROM articles WHERE project_id=?", (project_id,)).fetchone()["n"]
        active = conn.execute("SELECT COUNT(*) AS n FROM articles WHERE project_id=? AND is_active=1", (project_id,)).fetchone()["n"]
        classified = conn.execute("SELECT COUNT(*) AS n FROM llm_results r JOIN articles a ON r.article_id=a.article_id WHERE a.project_id=?", (project_id,)).fetchone()["n"]
        artifacts = conn.execute("SELECT COUNT(*) AS n FROM artifacts WHERE project_id=?", (project_id,)).fetchone()["n"]
        conn.close()
        return {"total": total, "active": active, "classified": classified, "artifacts": artifacts}
    except Exception:
        return {"total": 0, "active": 0, "classified": 0, "artifacts": 0}


def _load_recent_activity(project_id: str) -> list[dict]:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection
        db_path = get_projects_dir() / project_id / "project.db"
        if not db_path.exists():
            return []
        conn = get_connection(db_path)
        rows = conn.execute(
            "SELECT started_at AS time, 'ingest: ' || source AS action FROM ingest_runs WHERE project_id=? "
            "UNION ALL "
            "SELECT started_at AS time, 'clean: ' || status AS action FROM clean_runs WHERE project_id=? "
            "UNION ALL "
            "SELECT started_at AS time, 'llm: ' || provider || ' ' || status AS action FROM llm_jobs WHERE project_id=? "
            "ORDER BY time DESC LIMIT 5",
            (project_id, project_id, project_id),
        ).fetchall()
        conn.close()
        return [{"time": r["time"][:16], "action": r["action"]} for r in rows]
    except Exception:
        return []
