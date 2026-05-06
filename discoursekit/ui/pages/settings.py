"""Settings page for project management and local API keys."""

from __future__ import annotations

import streamlit as st

from discoursekit.ui.components import info_table, page_header, section_header


def render() -> None:
    page_header("설정", "프로젝트, 자료 수집 API, LLM API key를 로컬에서 관리합니다.")

    tab_project, tab_api, tab_about = st.tabs(["프로젝트", "API 설정", "정보"])
    with tab_project:
        _render_project_settings()
    with tab_api:
        _render_api_settings()
    with tab_about:
        _render_about()


def _render_project_settings() -> None:
    section_header("프로젝트 관리")

    with st.expander("새 프로젝트 만들기", expanded=False):
        new_name = st.text_input("프로젝트 이름", placeholder="예: 이태원동 담론 분석")
        new_desc = st.text_area("설명", placeholder="연구 목적, 분석 범위", height=80)
        if st.button("프로젝트 생성", type="primary", key="btn_create_project_settings"):
            if not new_name.strip():
                st.error("프로젝트 이름을 입력하세요.")
            else:
                _create_project(new_name.strip(), new_desc.strip())

    st.markdown("---")
    section_header("기존 프로젝트")
    projects = _list_projects()
    if not projects:
        st.caption("아직 프로젝트가 없습니다. 홈에서 분석 주제와 검색어를 입력해 시작하세요.")
    for project in projects:
        with st.expander(project["name"], expanded=False):
            info_table(
                {
                    "ID": project["project_id"][:8] + "...",
                    "생성일": project.get("created_at", "")[:16],
                    "설명": project.get("description", "") or "-",
                }
            )

    st.markdown("---")
    section_header("Handoff Import")
    st.caption("수집용 PC에서 만든 ingest-only handoff zip을 분석용 PC로 가져옵니다.")
    uploaded_zip = st.file_uploader("Handoff zip 파일", type=["zip"], key="import_zip")
    import_name = st.text_input("Import 프로젝트 이름", placeholder="비워두면 원래 이름을 사용합니다.")
    if uploaded_zip and st.button("Import 실행", key="btn_import"):
        _run_handoff_import(uploaded_zip, import_name)


def _render_api_settings() -> None:
    from discoursekit.config import DEFAULT_DATA_DIR
    from discoursekit.ui.env_keys import (
        load_gemini_keys,
        load_naver_keys,
        save_gemini_keys,
        save_naver_keys,
    )

    section_header("데이터 저장 위치")
    st.code(str(DEFAULT_DATA_DIR))
    st.caption("바꾸려면 환경변수 `DISCOURSEKIT_DATA_DIR`를 설정하세요.")

    st.markdown("---")
    section_header("NAVER API")
    st.caption(
        "NAVER 검색 API를 사용하려면 Client ID와 Client Secret이 필요합니다. "
        "[developers.naver.com](https://developers.naver.com)에서 애플리케이션을 등록하고 "
        "사용 API로 검색을 선택하면 발급받을 수 있습니다."
    )
    naver = load_naver_keys()
    client_id = st.text_input(
        "Client ID",
        value=naver.get("NAVER_CLIENT_ID", ""),
        type="password",
        key="naver_client_id_input",
    )
    client_secret = st.text_input(
        "Client Secret",
        value=naver.get("NAVER_CLIENT_SECRET", ""),
        type="password",
        key="naver_client_secret_input",
    )
    if st.button("NAVER API 저장", key="save_naver_keys"):
        save_naver_keys(client_id, client_secret)
        st.success("NAVER API 설정을 .env에 저장했습니다.")

    st.caption("API key는 로컬 .env에만 저장되며 export, report, handoff에는 포함되지 않습니다.")

    st.markdown("---")
    section_header("Gemini API Slots")
    st.caption(
        "LLM 보정에 사용하는 Gemini API 슬롯입니다. 최대 3개 키를 번갈아 사용해 quota 소진 시 전환할 수 있습니다. "
        "[aistudio.google.com](https://aistudio.google.com)에서 Get API Key를 눌러 만들 수 있습니다."
    )
    gemini = load_gemini_keys()
    slots: dict[int, str] = {}
    for slot in range(1, 4):
        slots[slot] = st.text_input(
            f"Gemini Slot {slot}",
            value=gemini.get(slot, ""),
            type="password",
            key=f"gemini_slot_{slot}",
        )
    if st.button("Gemini slots 저장", key="save_gemini_slots"):
        save_gemini_keys(slots)
        st.success("Gemini API slots를 .env에 저장했습니다.")


def _render_about() -> None:
    from discoursekit import __version__

    section_header("DiscourseKit 정보")
    info_table(
        {
            "버전": __version__,
            "UI": "Streamlit",
            "DB": "SQLite",
            "수집": "NAVER News, BIGKinds, CSV",
            "LLM 역할": "정제 보조, 의미 태그 후보, 검토 후보 생성",
        }
    )
    st.markdown(
        """
DiscourseKit v0.1은 자동 수집과 정제, Python 기반 개요 분석, 정성 분석을 위한 표본 추천을 연결하는 로컬 우선 워크벤치입니다.

LLM은 최종 결론 생성기가 아니라 corpus enrichment 보조 단계로 사용합니다.
"""
    )


def _create_project(name: str, description: str) -> None:
    try:
        from discoursekit.core.project import Project

        project = Project.create(name=name, description=description)
        st.session_state["current_project_id"] = project.project_id
        st.session_state["current_project_name"] = project.name
        st.success(f"프로젝트 생성 완료: {project.name}")
        st.rerun()
    except Exception as exc:
        st.error(f"생성 실패: {exc}")


def _run_handoff_import(uploaded_zip, import_name: str) -> None:
    """Import an ingest-only handoff zip into a new local project folder."""
    tmp_path = None
    with st.spinner("Handoff import 중입니다."):
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

            st.session_state["current_project_id"] = project_id
            st.session_state["current_project_name"] = project_name
            st.success(f"Import 완료: 기사 {result['article_count']}건")
            st.rerun()
        except Exception as exc:
            st.error(f"Import 실패: {exc}")
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
        from discoursekit.core.project import Project

        return [
            {
                "project_id": p.project_id,
                "name": p.name,
                "created_at": p.created_at,
                "description": p.description,
            }
            for p in Project.list_all()
        ]
    except Exception:
        return []
