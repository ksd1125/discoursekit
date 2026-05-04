"""Sidebar navigation and project selector."""

import streamlit as st


def render_sidebar() -> str:
    """Render the sidebar and return selected page name."""

    with st.sidebar:
        # Logo / title
        st.markdown("## 📰 DiscourseKit")
        st.caption("v0.1.0 · Academic Discourse Analysis")
        st.divider()

        # ─── Project selector ───
        st.markdown("##### 프로젝트")
        projects = _get_project_list()
        if projects:
            project_names = [p["name"] for p in projects]
            selected_idx = st.selectbox(
                "프로젝트 선택",
                range(len(project_names)),
                format_func=lambda i: project_names[i],
                label_visibility="collapsed",
            )
            st.session_state["current_project_id"] = projects[selected_idx]["project_id"]
            st.session_state["current_project_name"] = projects[selected_idx]["name"]
        else:
            st.info("프로젝트 없음. 홈에서 새로 만드세요.")
            st.session_state["current_project_id"] = None

        st.divider()

        # ─── Navigation ───
        st.markdown("##### 워크플로우")
        pages = ["홈", "1. 수집", "2. 정제", "3. LLM 분류", "4. 분석·리포트", "설정"]
        if "nav_page" in st.session_state:
            target_page = st.session_state.pop("nav_page")
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

        # ─── Pipeline status ───
        st.markdown("##### 파이프라인 상태")
        _render_pipeline_status()

        # ─── Footer ───
        st.divider()
        st.caption("MIT License · [GitHub](https://github.com)")

    return page


def _get_project_list() -> list[dict]:
    """Load project list from DB. Returns list of {project_id, name}."""
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection

        projects_dir = get_projects_dir()
        if not projects_dir.exists():
            return []

        results = []
        for sub in sorted(projects_dir.iterdir()):
            db_path = sub / "project.db"
            if db_path.exists():
                try:
                    conn = get_connection(db_path)
                    row = conn.execute("SELECT project_id, name FROM projects LIMIT 1").fetchone()
                    if row:
                        results.append({"project_id": row["project_id"], "name": row["name"]})
                    conn.close()
                except Exception:
                    pass
        return results
    except Exception:
        return []


def _render_pipeline_status():
    """Show which pipeline steps have been completed."""
    project_id = st.session_state.get("current_project_id")
    if not project_id:
        st.caption("프로젝트를 선택하세요")
        return

    # Determine status of each step
    steps = [
        ("수집", _check_ingest(project_id)),
        ("정제", _check_clean(project_id)),
        ("LLM", _check_llm(project_id)),
        ("분석", _check_analyze(project_id)),
    ]

    for name, status in steps:
        if status == "done":
            st.markdown(f"✅ {name}")
        elif status == "running":
            st.markdown(f"🔄 {name}")
        else:
            st.markdown(f"⬜ {name}")


def _check_ingest(project_id: str) -> str:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection
        db_path = get_projects_dir() / project_id / "project.db"
        if not db_path.exists():
            return "pending"
        conn = get_connection(db_path)
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE project_id = ?", (project_id,)
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
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM llm_jobs WHERE project_id = ? AND status IN ('success', 'running')",
            (project_id,),
        ).fetchone()
        if row["n"] == 0:
            conn.close()
            return "pending"
        running = conn.execute(
            "SELECT COUNT(*) AS n FROM llm_jobs WHERE project_id = ? AND status = 'running'",
            (project_id,),
        ).fetchone()
        conn.close()
        return "running" if running["n"] > 0 else "done"
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
            "SELECT COUNT(*) AS n FROM artifacts WHERE project_id = ?", (project_id,)
        ).fetchone()
        conn.close()
        return "done" if row["n"] > 0 else "pending"
    except Exception:
        return "pending"
