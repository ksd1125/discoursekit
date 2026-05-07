"""Qualitative analysis workbench UI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from discoursekit.config import get_projects_dir
from discoursekit.core.db import get_connection
from discoursekit.qual.codebook import (
    ALLOWED_METHODS,
    codebook_history,
    get_template,
    load_codebook,
    save_codebook,
    validate_codebook,
)
from discoursekit.qual.coding import (
    CodingRecord,
    EvidenceSentence,
    code_frequency,
    coding_progress,
    load_all_codings,
    load_coding,
    save_coding,
)
from discoursekit.qual.evidence import build_evidence_index, export_evidence_csv
from discoursekit.qual.reliability import compute_cohens_kappa, disagreement_table
from discoursekit.qual.report import generate_qualitative_report, save_report
from discoursekit.ui.components import empty_state, page_header


METHOD_LABELS = {
    "qualitative_content_analysis": "질적 내용분석",
    "frame_analysis": "프레임 분석",
    "thematic_analysis": "주제 분석",
    "discourse_analysis": "담론 분석",
    "place_discourse": "장소 담론 분석",
}

METHOD_DESCRIPTIONS = {
    "qualitative_content_analysis": "문장 또는 문단 단위로 범주를 부여하고 빈도와 근거를 함께 검토합니다.",
    "frame_analysis": "문제 정의, 원인 진단, 도덕 평가, 해결책 제시의 프레임 요소를 확인합니다.",
    "thematic_analysis": "반복되는 의미 패턴을 초기 코드에서 주제로 묶어갑니다.",
    "discourse_analysis": "행위자, 권력 관계, 표현 방식, 주체 위치를 메모 중심으로 해석합니다.",
    "place_discourse": "장소 이미지, 정체성, 행위자, 평판 서사를 추적합니다.",
}

STRATEGY_LABELS = {
    "random": "무작위",
    "peak_period": "보도량 최대 시기",
    "keyword_match": "키워드 매칭",
    "stratified": "출처 층화",
    "recent": "최신순",
}


def render() -> None:
    page_header(
        "정성 분석",
        "연구 질문, 분석 방법, 표본, 코드북, 코딩, 근거 문장, 신뢰도, 리포트를 한 흐름으로 관리합니다.",
    )
    project_id = st.session_state.get("current_project_id")
    if not project_id:
        empty_state("먼저 프로젝트를 선택하세요.")
        return

    tabs = st.tabs(
        [
            "분석 질문",
            "분석 방법",
            "표본 추출",
            "코드북",
            "코딩",
            "근거 문장",
            "신뢰도",
            "리포트",
        ]
    )
    with tabs[0]:
        _render_research_question(project_id)
    with tabs[1]:
        _render_method_selection(project_id)
    with tabs[2]:
        _render_sampling(project_id)
    with tabs[3]:
        _render_codebook(project_id)
    with tabs[4]:
        _render_coding(project_id)
    with tabs[5]:
        _render_evidence(project_id)
    with tabs[6]:
        _render_reliability(project_id)
    with tabs[7]:
        _render_report(project_id)


def _render_research_question(project_id: str) -> None:
    project_dir = _get_project_dir(project_id)
    config = _load_qual_config(project_dir)
    st.markdown("#### 분석의 기준점")
    st.caption("정성 코딩은 질문이 먼저입니다. 이 값은 코드북, 코딩 메모, 리포트에서 계속 참조됩니다.")

    research_question = st.text_area(
        "분석 질문",
        value=str(config.get("research_question", "")),
        height=110,
        placeholder="예: 특정 기간 뉴스에서 이태원동은 어떤 장소 이미지와 책임 서사로 구성되는가?",
    )
    purpose = st.text_area(
        "분석 목적",
        value=str(config.get("purpose", "")),
        height=90,
        placeholder="이 분석으로 확인하려는 비교 기준, 기간, 대상, 활용 목적을 적습니다.",
    )
    theoretical_background = st.text_area(
        "이론/선행연구 메모",
        value=str(config.get("theoretical_background", "")),
        height=120,
        placeholder="예: Entman의 프레임 분석, Mayring의 질적 내용분석, 장소 담론 연구 등",
    )

    if st.button("분석 질문 저장", type="primary"):
        now = _now_iso()
        next_config = {
            **config,
            "project_id": project_id,
            "method": config.get("method", "qualitative_content_analysis"),
            "research_question": research_question.strip(),
            "purpose": purpose.strip(),
            "theoretical_background": theoretical_background.strip(),
            "created_at": config.get("created_at") or now,
            "updated_at": now,
        }
        _save_qual_config(project_dir, next_config)
        st.success("분석 질문을 저장했습니다.")


def _render_method_selection(project_id: str) -> None:
    project_dir = _get_project_dir(project_id)
    config = _load_qual_config(project_dir)
    current_method = str(config.get("method") or "qualitative_content_analysis")
    if current_method not in ALLOWED_METHODS:
        current_method = "qualitative_content_analysis"

    method = st.radio(
        "분석 방법",
        ALLOWED_METHODS,
        index=ALLOWED_METHODS.index(current_method),
        format_func=lambda item: METHOD_LABELS.get(item, item),
    )
    st.info(METHOD_DESCRIPTIONS.get(method, ""))

    col1, col2 = st.columns(2)
    with col1:
        if st.button("분석 방법 저장", type="primary"):
            now = _now_iso()
            _save_qual_config(
                project_dir,
                {
                    **config,
                    "project_id": project_id,
                    "method": method,
                    "created_at": config.get("created_at") or now,
                    "updated_at": now,
                },
            )
            st.success("분석 방법을 저장했습니다.")
    with col2:
        if st.button("선택 방법의 코드북 초안 불러오기"):
            st.session_state["qual_codebook_draft"] = get_template(method)
            st.success("코드북 탭에서 초안을 확인하고 수정할 수 있습니다.")

    st.markdown("#### 방법별 사용 기준")
    st.dataframe(
        [
            {"방법": METHOD_LABELS[key], "적합한 질문": value}
            for key, value in METHOD_DESCRIPTIONS.items()
        ],
        use_container_width=True,
        hide_index=True,
    )


def _render_sampling(project_id: str) -> None:
    from discoursekit.analyze.sampling import sample_representative_articles

    project_dir = _get_project_dir(project_id)
    config = _load_qual_config(project_dir)
    st.markdown("#### 코딩 표본 만들기")
    st.caption("표본은 연구자가 직접 코딩할 기사 목록입니다. NAVER 자료는 제목과 요약문 기반임을 해석에 반영하세요.")

    strategy = st.selectbox(
        "표본 전략",
        list(STRATEGY_LABELS),
        format_func=lambda item: STRATEGY_LABELS.get(item, item),
    )
    size = st.number_input("표본 크기", min_value=5, max_value=500, value=30, step=5)
    keyword = None
    if strategy == "keyword_match":
        keyword = st.text_input("매칭 키워드", value=str(config.get("query", "")))
        if not keyword.strip():
            st.info("키워드 매칭 표본을 만들려면 매칭 키워드를 입력하세요.")

    if st.button("표본 추출", type="primary"):
        try:
            result = sample_representative_articles(
                _db_path(project_id),
                project_id,
                strategy=strategy,
                n=int(size),
                keyword=keyword,
            )
            st.session_state["qual_sample_preview"] = result.articles
            st.session_state["qual_sample_meta"] = {
                "strategy": result.strategy,
                "sample_size": result.sample_size,
                "population_size": result.population_size,
                "sampled_at": _now_iso(),
            }
        except Exception as exc:
            st.error(f"표본 추출 실패: {exc}")

    rows = st.session_state.get("qual_sample_preview") or _load_sample(project_dir)
    if not rows:
        empty_state("아직 표본이 없습니다.")
        return

    st.dataframe(rows, use_container_width=True, hide_index=True)
    meta = st.session_state.get("qual_sample_meta", {})
    if meta:
        st.caption(
            f"전략: {meta.get('strategy')} / 표본: {meta.get('sample_size')}건 / 모집단: {meta.get('population_size')}건"
        )

    if st.button("현재 표본 저장"):
        _save_sample(project_dir, rows)
        st.success("qual/sample.json에 표본을 저장했습니다.")


def _render_codebook(project_id: str) -> None:
    project_dir = _get_project_dir(project_id)
    config = _load_qual_config(project_dir)
    method = str(config.get("method") or "qualitative_content_analysis")
    if method not in ALLOWED_METHODS:
        method = "qualitative_content_analysis"

    st.markdown("#### 코드북")
    st.caption("최종 코딩 전에 코드, 정의, 포함/제외 기준을 고정합니다. 코드북이 없으면 코딩 탭은 진행하지 않습니다.")

    uploaded = st.file_uploader("코드북 JSON 가져오기", type=["json"])
    if uploaded is not None:
        try:
            st.session_state["qual_codebook_draft"] = json.loads(uploaded.getvalue().decode("utf-8"))
            st.success("업로드한 코드북을 초안으로 불러왔습니다.")
        except Exception as exc:
            st.error(f"코드북 JSON 로드 실패: {exc}")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("템플릿 불러오기"):
            st.session_state["qual_codebook_draft"] = get_template(method)
    with col2:
        if st.button("저장된 코드북 불러오기"):
            try:
                st.session_state["qual_codebook_draft"] = load_codebook(project_dir)
            except ValueError:
                st.warning("저장된 코드북이 없습니다.")
    with col3:
        if st.button("초기화"):
            st.session_state.pop("qual_codebook_draft", None)

    draft = st.session_state.get("qual_codebook_draft")
    if draft is None:
        try:
            draft = load_codebook(project_dir)
        except ValueError:
            draft = get_template(method)
        st.session_state["qual_codebook_draft"] = draft

    _render_codebook_quick_add(draft)
    raw_json = st.text_area(
        "코드북 JSON 편집",
        value=json.dumps(st.session_state["qual_codebook_draft"], ensure_ascii=False, indent=2),
        height=440,
        key="qual_codebook_json_editor",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("코드북 검증"):
            _validate_codebook_text(raw_json)
    with col2:
        if st.button("코드북 저장", type="primary"):
            try:
                payload = json.loads(raw_json)
                errors = validate_codebook(payload)
                if errors:
                    st.error(" / ".join(errors))
                else:
                    save_codebook(project_dir, payload)
                    st.session_state["qual_codebook_draft"] = payload
                    st.success("코드북을 저장했습니다.")
            except Exception as exc:
                st.error(f"코드북 저장 실패: {exc}")

    with st.expander("코드북 이력"):
        history = codebook_history(project_dir)
        if history:
            st.dataframe(history, use_container_width=True, hide_index=True)
        else:
            st.caption("아직 저장 이력이 없습니다.")


def _render_coding(project_id: str) -> None:
    project_dir = _get_project_dir(project_id)
    sample = _load_sample(project_dir)
    if not sample:
        empty_state("먼저 표본 추출 탭에서 코딩 표본을 저장하세요.")
        return

    codebook = _load_codebook_or_none(project_dir)
    if codebook is None:
        st.warning(
            "코드북이 없습니다. 코딩을 시작하려면 먼저 코드북이 필요합니다.\n\n"
            "**방법 1:** 코드북 탭에서 템플릿을 불러온 뒤 연구 목적에 맞게 수정하고 저장하세요.\n\n"
            "**방법 2:** 기존 코드북 JSON 파일이 있다면 코드북 탭에서 업로드하세요."
        )
        return

    codes = _code_options(codebook)
    if not codes:
        st.warning("코드북에 사용할 코드가 없습니다.")
        return

    sample_ids = [str(row.get("article_id", "")) for row in sample if row.get("article_id")]
    progress = coding_progress(project_dir, sample_ids)
    st.progress(progress["complete"] / progress["total"] if progress["total"] else 0.0)
    st.caption(
        f"완료 {progress['complete']} / 진행 중 {progress['in_progress']} / 대기 {progress['pending']} / 전체 {progress['total']}"
    )

    index = int(st.session_state.get("qual_coding_index", 0))
    index = max(0, min(index, len(sample) - 1))
    st.session_state["qual_coding_index"] = index

    nav1, nav2, nav3 = st.columns([1, 2, 1])
    with nav1:
        if st.button("이전 기사", disabled=index <= 0):
            st.session_state["qual_coding_index"] = index - 1
            st.rerun()
    with nav2:
        st.markdown(f"**기사 {index + 1}/{len(sample)}**")
    with nav3:
        if st.button("다음 기사", disabled=index >= len(sample) - 1):
            st.session_state["qual_coding_index"] = index + 1
            st.rerun()

    article_id = str(sample[index].get("article_id", ""))
    article = _load_article(project_id, article_id) or sample[index]
    record = load_coding(project_dir, article_id)
    suggestions = _load_llm_suggestions(project_id, article_id)

    st.markdown(f"#### {article.get('title', '(제목 없음)')}")
    st.caption(f"{article.get('date', '')} / {article.get('publisher', '')} / article_id: {article_id}")
    st.text_area(
        "본문 요약",
        value=str(article.get("body_excerpt") or ""),
        height=170,
        disabled=True,
    )

    code_labels = {item["code"]: f"{item['code']} - {item['label']}" for item in codes}
    selected_codes = st.multiselect(
        "부여할 코드",
        options=[item["code"] for item in codes],
        default=record.codes if record else [],
        format_func=lambda item: code_labels.get(item, item),
    )

    with st.expander("LLM 제안 참고", expanded=bool(suggestions)):
        if not suggestions:
            st.caption("이 기사에 저장된 LLM 보정 제안이 없습니다.")
        else:
            st.caption("LLM 제안은 검토 후보일 뿐이며 최종 코딩이 아닙니다.")
            if suggestions.get("semantic_tags"):
                st.write("의미 태그 제안:", ", ".join(suggestions["semantic_tags"]))
            if suggestions.get("canonical_entities"):
                st.write("표준화 후보:", ", ".join(suggestions["canonical_entities"]))
            if suggestions.get("evidence_sentences"):
                st.write("근거 문장 후보")
                for sentence in suggestions["evidence_sentences"]:
                    st.markdown(f"- {sentence}")
            if suggestions.get("relevance_score") is not None:
                st.write(f"관련성 참고 점수: {suggestions['relevance_score']}")

    existing_evidence = "\n".join([item.text for item in record.evidence_sentences]) if record else ""
    evidence_text = st.text_area(
        "근거 문장",
        value=existing_evidence,
        height=130,
        placeholder="한 줄에 한 문장씩 입력합니다. 실제 화면에 표시된 요약문 또는 원문 검토 자료에서 확인한 문장만 넣으세요.",
    )
    evidence_code = st.selectbox(
        "근거 문장에 연결할 대표 코드",
        options=[item["code"] for item in codes],
        format_func=lambda item: code_labels.get(item, item),
    )
    memo = st.text_area("연구자 메모", value=record.memo if record else "", height=120)
    llm_agreement = st.selectbox(
        "LLM 제안과의 관계 메모",
        ["", "agree", "partial", "disagree"],
        index=["", "agree", "partial", "disagree"].index(record.llm_agreement or "") if record else 0,
    )
    status = st.selectbox(
        "코딩 상태",
        ["pending", "in_progress", "complete"],
        index=["pending", "in_progress", "complete"].index(record.status if record else "complete"),
    )

    if st.button("코딩 저장", type="primary"):
        evidence_rows = [
            EvidenceSentence(text=line.strip(), code=evidence_code, source="body_excerpt")
            for line in evidence_text.splitlines()
            if line.strip()
        ]
        save_coding(
            project_dir,
            CodingRecord(
                article_id=article_id,
                coder_id="researcher",
                codes=selected_codes,
                evidence_sentences=evidence_rows,
                memo=memo.strip(),
                coded_at=_now_iso(),
                llm_codes=suggestions.get("semantic_tags") or None,
                llm_agreement=llm_agreement or None,
                status=status,
            ),
        )
        st.success("코딩을 저장했습니다.")

    frequencies = code_frequency(project_dir)
    if frequencies:
        st.markdown("#### 코드 빈도")
        st.bar_chart(frequencies)


def _render_evidence(project_id: str) -> None:
    project_dir = _get_project_dir(project_id)
    index = build_evidence_index(project_dir)
    if not index:
        empty_state("저장된 근거 문장이 없습니다.")
        return

    codebook = _load_codebook_or_none(project_dir) or {}
    labels = {item["code"]: item["label"] for item in _code_options(codebook)}
    for code, rows in sorted(index.items()):
        with st.expander(f"{code} {labels.get(code, '')} / 근거 {len(rows)}건", expanded=True):
            st.dataframe(rows, use_container_width=True, hide_index=True)

    output_path = project_dir / "qual" / "evidence" / "evidence.csv"
    if st.button("근거 CSV 만들기"):
        try:
            export_evidence_csv(project_dir, output_path)
            st.success(f"CSV를 만들었습니다: {output_path}")
        except Exception as exc:
            st.error(f"CSV 생성 실패: {exc}")
    if output_path.exists():
        st.download_button(
            "근거 CSV 다운로드",
            data=output_path.read_bytes(),
            file_name="qualitative_evidence.csv",
            mime="text/csv",
        )


def _render_reliability(project_id: str) -> None:
    project_dir = _get_project_dir(project_id)
    codebook = _load_codebook_or_none(project_dir)
    if codebook is None:
        st.warning("신뢰도 계산에는 코드북이 필요합니다.")
        return

    codes = [item["code"] for item in _code_options(codebook)]
    human_records = load_all_codings(project_dir)
    llm_records = _build_llm_reference_records(human_records)

    st.markdown("#### 연구자 코딩 vs LLM 제안")
    st.caption("Cohen's kappa는 일치도 참고 지표입니다. LLM 제안이 맞다는 뜻이 아니라 불일치 검토 대상을 찾기 위한 장치입니다.")
    st.caption(f"코더 A=researcher / 코더 B=enrich_v1 / 표본={len(llm_records)}건 / 코드={len(codes)}개")

    if st.button("신뢰도 계산", type="primary"):
        if not human_records or not llm_records or not codes:
            st.warning("저장된 코딩, LLM 제안, 코드북 코드가 모두 있어야 계산할 수 있습니다.")
            return
        result = compute_cohens_kappa(human_records, llm_records, codes)
        disagreements = disagreement_table(human_records, llm_records)
        payload = {
            **result,
            "comparison_type": "human_llm",
            "coder_a": "researcher",
            "coder_b": "enrich_v1",
            "disagreement_count": len(disagreements),
            "disagreements": disagreements,
            "computed_at": _now_iso(),
            "method_note": (
                "Cohen's kappa, binary per-code evaluation. "
                f"Articles={result.get('n_articles', 0)}, codes={result.get('n_codes', 0)}."
            ),
        }
        path = _save_reliability(project_dir, payload)
        st.session_state["qual_reliability_result"] = payload
        st.success(f"신뢰도 결과를 저장했습니다: {path}")

    result = st.session_state.get("qual_reliability_result") or _load_latest_reliability(project_dir)
    if not result:
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Cohen's kappa", f"{float(result.get('kappa', 0.0)):.3f}")
    col2.metric("일치율", f"{float(result.get('percent_agreement', 0.0)):.1f}%")
    col3.metric("해석", str(result.get("interpretation", "")))
    st.caption(result.get("method_note", ""))

    disagreements = result.get("disagreements", [])
    if disagreements:
        st.markdown("#### 불일치 검토표")
        st.dataframe(disagreements, use_container_width=True, hide_index=True)


def _render_report(project_id: str) -> None:
    project_dir = _get_project_dir(project_id)
    st.markdown("#### 정성 분석 리포트")
    st.caption("리포트는 연구자의 질문, 코드북, 코딩 요약, 근거 문장, 신뢰도 메모를 모은 Markdown 초안입니다.")

    if st.button("리포트 생성", type="primary"):
        try:
            st.session_state["qual_report_markdown"] = generate_qualitative_report(project_dir)
        except Exception as exc:
            st.error(f"리포트 생성 실패: {exc}")

    content = st.session_state.get("qual_report_markdown", "")
    if content:
        st.markdown(content)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("리포트 저장"):
                path = save_report(project_dir, content)
                st.success(f"리포트를 저장했습니다: {path}")
        with col2:
            st.download_button(
                "Markdown 다운로드",
                data=content.encode("utf-8"),
                file_name="qualitative_report.md",
                mime="text/markdown",
            )

    reports_dir = project_dir / "qual" / "reports"
    with st.expander("저장된 리포트"):
        if reports_dir.exists():
            rows = [
                {"filename": path.name, "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat()}
                for path in sorted(reports_dir.glob("*.md"), reverse=True)
            ]
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.caption("저장된 리포트가 없습니다.")
        else:
            st.caption("저장된 리포트가 없습니다.")


def _render_codebook_quick_add(draft: dict) -> None:
    st.markdown("#### 빠른 코드 추가")
    target = _editable_code_list(draft)
    if target is None:
        st.caption("프레임 분석 코드북은 JSON 편집 영역에서 frame_elements별 codes를 수정하세요.")
        return

    with st.expander("새 코드 추가"):
        col1, col2 = st.columns(2)
        code = col1.text_input("code", key="qual_new_code")
        label = col2.text_input("label", key="qual_new_label")
        definition = st.text_area("definition", key="qual_new_definition", height=80)
        include = st.text_input("include 기준", key="qual_new_include")
        exclude = st.text_input("exclude 기준", key="qual_new_exclude")
        if st.button("초안에 코드 추가"):
            if not code.strip() or not label.strip() or not definition.strip():
                st.warning("code, label, definition은 필수입니다.")
                return
            target.append(
                {
                    "code": code.strip(),
                    "label": label.strip(),
                    "definition": definition.strip(),
                    "include": [include.strip()] if include.strip() else [],
                    "exclude": [exclude.strip()] if exclude.strip() else [],
                }
            )
            st.session_state["qual_codebook_draft"] = draft
            st.success("초안에 코드를 추가했습니다. JSON 편집 영역에 반영됩니다.")


def _validate_codebook_text(raw_json: str) -> None:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        st.error(f"JSON 형식 오류: {exc}")
        return
    errors = validate_codebook(payload)
    if errors:
        st.error(" / ".join(errors))
    else:
        st.success("코드북 검증을 통과했습니다.")


def _editable_code_list(codebook: dict) -> list[dict] | None:
    if isinstance(codebook.get("codes"), list):
        return codebook["codes"]
    return None


def _get_project_dir(project_id: str) -> Path:
    """Return the project directory path."""
    return get_projects_dir() / project_id


def _db_path(project_id: str) -> Path:
    return _get_project_dir(project_id) / "project.db"


def _load_qual_config(project_dir: Path) -> dict:
    """Load qual/qual_config.json. Return an empty dict when missing."""
    path = project_dir / "qual" / "qual_config.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_qual_config(project_dir: Path, config: dict) -> None:
    """Save qual/qual_config.json."""
    path = project_dir / "qual" / "qual_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_sample(project_dir: Path) -> list[dict]:
    """Load qual/sample.json. Return an empty list when missing."""
    path = project_dir / "qual" / "sample.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else payload.get("articles", [])
    except Exception:
        return []


def _save_sample(project_dir: Path, sample: list[dict]) -> None:
    path = project_dir / "qual" / "sample.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_rows = [
        {
            key: row.get(key, "")
            for key in ("article_id", "title", "date", "publisher", "reason")
            if key in row
        }
        for row in sample
    ]
    path.write_text(json.dumps(safe_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_article(project_id: str, article_id: str) -> dict | None:
    db_path = _db_path(project_id)
    if not db_path.exists():
        return None
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT article_id, title, date, publisher, body_excerpt, url
            FROM articles
            WHERE project_id = ? AND article_id = ?
            """,
            (project_id, article_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _load_codebook_or_none(project_dir: Path) -> dict | None:
    try:
        return load_codebook(project_dir)
    except ValueError:
        return None


def _code_options(codebook: dict) -> list[dict]:
    rows: list[dict] = []
    for item in codebook.get("codes", []):
        if isinstance(item, dict) and item.get("code"):
            rows.append(
                {
                    "code": str(item.get("code", "")),
                    "label": str(item.get("label", "")),
                    "definition": str(item.get("definition", "")),
                }
            )
    for element in codebook.get("frame_elements", []):
        for item in element.get("codes", []):
            if isinstance(item, dict) and item.get("code"):
                rows.append(
                    {
                        "code": str(item.get("code", "")),
                        "label": str(item.get("label", "")),
                        "definition": str(item.get("definition", "")),
                    }
                )
    return rows


def _load_llm_suggestions(project_id: str, article_id: str) -> dict[str, Any]:
    db_path = _db_path(project_id)
    if not db_path.exists():
        return {}
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT r.labels_json
            FROM llm_results r
            JOIN llm_jobs j ON j.job_id = r.job_id
            WHERE j.project_id = ? AND r.article_id = ?
            ORDER BY r.called_at DESC
            LIMIT 1
            """,
            (project_id, article_id),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["labels_json"]:
        return {}
    try:
        payload = json.loads(row["labels_json"])
    except Exception:
        return {}

    enrichment = payload.get("enrichment", payload) if isinstance(payload, dict) else {}
    if not isinstance(enrichment, dict):
        return {}
    entities = enrichment.get("canonical_entities") or enrichment.get("canonical_places") or []
    return {
        "semantic_tags": _as_string_list(enrichment.get("semantic_tags")),
        "canonical_entities": _as_string_list(entities),
        "evidence_sentences": _as_string_list(enrichment.get("evidence_sentences")),
        "relevance_score": enrichment.get("relevance_score"),
    }


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict):
            text = item.get("text") or item.get("name") or item.get("value")
            if text:
                result.append(str(text))
        elif item:
            result.append(str(item))
    return result


def _build_llm_reference_records(records: list[CodingRecord]) -> list[CodingRecord]:
    result = []
    for record in records:
        if not record.llm_codes:
            continue
        result.append(
            CodingRecord(
                article_id=record.article_id,
                coder_id="enrich_v1",
                codes=record.llm_codes,
                evidence_sentences=[],
                memo="LLM suggestion reference",
                coded_at=record.coded_at,
                status="complete",
            )
        )
    return result


def _save_reliability(project_dir: Path, payload: dict) -> Path:
    directory = project_dir / "qual" / "reliability"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"reliability_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _load_latest_reliability(project_dir: Path) -> dict | None:
    directory = project_dir / "qual" / "reliability"
    if not directory.exists():
        return None
    files = sorted(directory.glob("*.json"), reverse=True)
    if not files:
        return None
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
