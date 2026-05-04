"""Settings page — project management and configuration."""

import streamlit as st
from discoursekit.ui.components import page_header, section_header, empty_state, info_table


def render():
    page_header("설정", "프로젝트 관리 및 환경 설정")

    tab_project, tab_env, tab_about = st.tabs(["📁 프로젝트", "🔧 환경", "ℹ️ 정보"])

    with tab_project:
        _render_project_settings()
    with tab_env:
        _render_env_settings()
    with tab_about:
        _render_about()


def _render_project_settings():
    section_header("프로젝트 관리", "📁")

    # Create new project
    st.caption("💡 프로젝트 생성은 홈 화면에서도 할 수 있습니다.")
    with st.expander("새 프로젝트 만들기", expanded=False):
        new_name = st.text_input("프로젝트 이름", placeholder="예: 이태원 2022 분석")
        new_desc = st.text_area("설명 (선택)", placeholder="연구 목적, 분석 범위 등", height=80)

        if st.button("프로젝트 생성", type="primary", key="btn_create_project"):
            if not new_name.strip():
                st.error("프로젝트 이름을 입력하세요.")
            else:
                _create_project(new_name.strip(), new_desc.strip())

    st.markdown("---")

    # Existing projects
    section_header("기존 프로젝트", "📋")
    projects = _list_projects()
    if not projects:
        st.caption("프로젝트가 없습니다.")
    else:
        for p in projects:
            with st.expander(f"📁 {p['name']}", expanded=False):
                info_table({
                    "ID": p["project_id"][:8] + "...",
                    "생성일": p.get("created_at", "")[:16],
                    "설명": p.get("description", "") or "-",
                })

    # Import handoff
    st.markdown("---")
    section_header("Handoff Import", "📦")
    uploaded_zip = st.file_uploader("Handoff zip 파일", type=["zip"], key="import_zip")
    import_name = st.text_input("Import 프로젝트 이름", placeholder="새 이름 (비워두면 원래 이름 유지)")

    if uploaded_zip and st.button("Import 실행", key="btn_import"):
        _run_handoff_import(uploaded_zip, import_name)


def _render_env_settings():
    section_header("환경 설정", "🔧")

    st.markdown("#### 데이터 디렉터리")
    from discoursekit.config import DEFAULT_DATA_DIR
    st.code(str(DEFAULT_DATA_DIR))
    st.caption("변경하려면 환경변수 `DISCOURSEKIT_DATA_DIR`을 설정하세요.")

    st.markdown("---")
    st.markdown("#### .env 파일")
    st.markdown("""
    프로젝트 루트에 `.env` 파일을 만들어 API 키를 관리할 수 있습니다:
    ```
    GEMINI_KEY_1=AIzaSy...
    GEMINI_KEY_2=AIzaSy...
    GEMINI_KEY_3=AIzaSy...
    ```
    """)

    st.markdown("---")
    st.markdown("#### Gemini RPD 리셋")
    st.caption("Google Gemini API의 일일 한도(RPD)는 **Pacific Time 자정** 기준으로 리셋됩니다.")
    st.caption("한국시간 기준 약 오후 4~5시(서머타임 유무에 따라)에 리셋됩니다.")


def _render_about():
    section_header("DiscourseKit 정보", "ℹ️")

    from discoursekit import __version__

    info_table({
        "버전": __version__,
        "라이선스": "MIT",
        "Python": "3.10+",
        "UI": "Streamlit",
        "DB": "SQLite (9 tables)",
        "LLM": "Gemini 2.5 Flash (primary)",
    })

    st.markdown("---")
    st.markdown("""
    **DiscourseKit**은 뉴스·블로그·SNS 담론을 학술적으로 분석하기 위한 오픈소스 도구입니다.

    - 📰 다양한 자료원 지원 (BIGKinds, CSV, NAVER API)
    - 🧹 자동 정제·중복 제거
    - 🤖 LLM 기반 자동 분류 (resume 지원)
    - 📊 통계 분석 + 시각화
    - 📄 자동 보고서 생성
    - 🔬 학술 재현성 보장 (sha256, prompt versioning)

    [GitHub Repository](https://github.com) · [Documentation](https://github.com)
    """)


def _create_project(name: str, description: str):
    try:
        from discoursekit.core.project import Project
        proj = Project.create(name=name, description=description)
        st.success(f"✅ 프로젝트 '{name}' 생성 완료! (ID: {proj.project_id[:8]}...)")
        st.session_state["current_project_id"] = proj.project_id
        st.session_state["current_project_name"] = name
        st.rerun()
    except Exception as e:
        st.error(f"생성 실패: {e}")


def _run_handoff_import(uploaded_zip, import_name: str):
    """Import an ingest-only handoff zip into a new local project folder."""
    with st.spinner("Handoff import 중..."):
        tmp_path = None
        try:
            import tempfile
            import uuid
            from datetime import datetime, timezone
            from pathlib import Path

            from discoursekit.config import get_projects_dir
            from discoursekit.core.db import get_connection
            from discoursekit.handoff.import_handoff import import_ingest_handoff

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(uploaded_zip.getvalue())
                tmp_path = Path(tmp.name)

            result = import_ingest_handoff(
                tmp_path,
                target_project_id=str(uuid.uuid4()),
                target_base_dir=get_projects_dir(),
            )
            project_id = result["project_id"]
            project_name = import_name.strip()
            if project_name:
                db_path = Path(result["project_dir"]) / "project.db"
                conn = get_connection(db_path)
                with conn:
                    conn.execute(
                        "UPDATE projects SET name = ?, updated_at = ? WHERE project_id = ?",
                        (project_name, datetime.now(timezone.utc).isoformat(), project_id),
                    )
                conn.close()
            else:
                project_name = _project_name_for_id(project_id) or project_id

            st.success(
                f"✅ Import 완료! Project ID: `{project_id[:8]}...` | "
                f"기사 {result['article_count']}건"
            )
            st.session_state["current_project_id"] = project_id
            st.session_state["current_project_name"] = project_name
            st.rerun()
        except Exception as e:
            st.error(f"Import 실패: {e}")
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)


def _project_name_for_id(project_id: str) -> str:
    try:
        from discoursekit.config import get_projects_dir
        from discoursekit.core.db import get_connection

        db_path = get_projects_dir() / project_id / "project.db"
        conn = get_connection(db_path)
        row = conn.execute(
            "SELECT name FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        conn.close()
        return row["name"] if row else ""
    except Exception:
        return ""


def _list_projects() -> list[dict]:
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
                    row = conn.execute("SELECT * FROM projects LIMIT 1").fetchone()
                    if row:
                        results.append(dict(row))
                    conn.close()
                except Exception:
                    pass
        return results
    except Exception:
        return []
