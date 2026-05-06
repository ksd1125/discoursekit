"""Sidebar navigation and project selector."""

from __future__ import annotations

import streamlit as st


def render_sidebar(pages: list[str]) -> str:
    """Render the sidebar and return the selected page name."""
    with st.sidebar:
        st.markdown("## DiscourseKit")
        st.caption("v0.1 / 담론 분석 자료 만들기")
        st.divider()

        st.markdown("##### 프로젝트")
        projects = _get_project_list()
        if projects:
            names = [p["name"] for p in projects]
            selected_idx = st.selectbox(
                "프로젝트 선택",
                range(len(names)),
                format_func=lambda idx: names[idx],
                label_visibility="collapsed",
            )
            st.session_state["current_project_id"] = projects[selected_idx]["project_id"]
            st.session_state["current_project_name"] = projects[selected_idx]["name"]
        else:
            st.caption("아직 프로젝트가 없습니다. 홈에서 분석 주제를 입력해 시작하세요.")
            st.session_state["current_project_id"] = None
            st.session_state["current_project_name"] = ""

        st.divider()

        st.markdown("##### 메뉴")
        if "nav_page" in st.session_state:
            target_page = st.session_state["nav_page"]
            if target_page in pages:
                st.session_state["sidebar_page"] = target_page
        st.session_state.setdefault("sidebar_page", "홈")
        page = st.radio(
            "페이지",
            pages,
            key="sidebar_page",
            label_visibility="collapsed",
        )

        st.divider()
        st.markdown("##### 진행 상태")
        _render_pipeline_status()

        st.divider()
        st.markdown("##### LLM 사용량")
        _render_llm_budget_status()

        st.divider()
        with st.expander("도움말", expanded=False):
            st.markdown(
                """
- **처음 사용**: 홈에서 검색어 입력 후 데이터 만들기로 이동하세요.
- **NAVER API 발급**: [developers.naver.com](https://developers.naver.com)에서 애플리케이션 등록 후 검색 API를 선택합니다.
- **Gemini API 발급**: [aistudio.google.com](https://aistudio.google.com)에서 API Key를 만듭니다.
- **BIGKinds 자료**: [bigkinds.or.kr](https://www.bigkinds.or.kr)에서 검색 결과 XLSX를 내려받아 업로드합니다.
"""
            )
        st.caption("로컬 우선 / SQLite / Streamlit")

    return page


def _get_project_list() -> list[dict]:
    """Load project list from local project databases."""
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection

        projects_dir = get_projects_dir()
        if not projects_dir.exists():
            return []

        results = []
        for sub in sorted(projects_dir.iterdir()):
            db_path = sub / "project.db"
            if not db_path.exists():
                continue
            try:
                conn = get_connection(db_path)
                row = conn.execute("SELECT project_id, name FROM projects LIMIT 1").fetchone()
                conn.close()
                if row:
                    results.append({"project_id": row["project_id"], "name": row["name"]})
            except Exception:
                continue
        return results
    except Exception:
        return []


def _render_pipeline_status() -> None:
    project_id = st.session_state.get("current_project_id")
    if not project_id:
        st.caption("프로젝트를 선택하면 진행 상태가 표시됩니다.")
        return

    steps = [
        ("기사 수집", _check_ingest(project_id)),
        ("정제", _check_clean(project_id)),
        ("LLM 보정", _check_llm(project_id)),
        ("결과물", _check_analyze(project_id)),
    ]
    for name, status in steps:
        if status == "done":
            st.markdown(f"[완료] {name}")
        elif status == "running":
            st.markdown(f"[진행 중] {name}")
        else:
            st.markdown(f"[대기] {name}")


def _render_llm_budget_status() -> None:
    project_id = st.session_state.get("current_project_id")
    if not project_id:
        st.caption("프로젝트 선택 후 LLM 사용량을 볼 수 있습니다.")
        return
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection
        from discoursekit.llm.budget_manager import BudgetTracker

        db_path = get_projects_dir() / project_id / "project.db"
        if not db_path.exists():
            st.caption("아직 LLM 사용 기록이 없습니다.")
            return
        conn = get_connection(db_path)
        enrichment = conn.execute(
            "SELECT COUNT(*) AS n FROM llm_results r JOIN articles a ON a.article_id = r.article_id WHERE a.project_id = ?",
            (project_id,),
        ).fetchone()["n"]
        conn.close()
        tracker = BudgetTracker(daily_limit=4500, used={"enrichment": int(enrichment or 0)})
        summary = tracker.summary()
        st.progress(min(summary["usage_pct"] / 100, 1.0))
        st.caption(
            f"오늘 추정 {summary['total_used']:,} / {summary['daily_limit']:,}회 "
            f"({summary['usage_pct']}%)"
        )
    except Exception:
        st.caption("LLM 사용량을 불러오지 못했습니다.")


def _check_ingest(project_id: str) -> str:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection

        db_path = get_projects_dir() / project_id / "project.db"
        if not db_path.exists():
            return "pending"
        conn = get_connection(db_path)
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        conn.close()
        return "done" if row["n"] > 0 else "pending"
    except Exception:
        return "pending"


def _check_clean(project_id: str) -> str:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection

        db_path = get_projects_dir() / project_id / "project.db"
        if not db_path.exists():
            return "pending"
        conn = get_connection(db_path)
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM clean_runs WHERE project_id = ? AND status = 'success'",
            (project_id,),
        ).fetchone()
        conn.close()
        return "done" if row["n"] > 0 else "pending"
    except Exception:
        return "pending"


def _check_llm(project_id: str) -> str:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection

        db_path = get_projects_dir() / project_id / "project.db"
        if not db_path.exists():
            return "pending"
        conn = get_connection(db_path)
        running = conn.execute(
            "SELECT COUNT(*) AS n FROM llm_jobs WHERE project_id = ? AND status = 'running'",
            (project_id,),
        ).fetchone()
        done = conn.execute(
            "SELECT COUNT(*) AS n FROM llm_jobs WHERE project_id = ? AND status = 'success'",
            (project_id,),
        ).fetchone()
        conn.close()
        if running["n"] > 0:
            return "running"
        return "done" if done["n"] > 0 else "pending"
    except Exception:
        return "pending"


def _check_analyze(project_id: str) -> str:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection

        db_path = get_projects_dir() / project_id / "project.db"
        if not db_path.exists():
            return "pending"
        conn = get_connection(db_path)
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM artifacts WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        conn.close()
        return "done" if row["n"] > 0 else "pending"
    except Exception:
        return "pending"
