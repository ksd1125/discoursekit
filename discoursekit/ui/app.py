"""DiscourseKit Streamlit application."""

from __future__ import annotations

import streamlit as st


st.set_page_config(
    page_title="DiscourseKit",
    page_icon="DK",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    [data-testid="stSidebar"] {
        background-color: #f8f9fa;
        border-right: 1px solid #e9ecef;
    }
    [data-testid="stSidebar"] .stRadio > label {
        font-weight: 500;
    }
    .main-header {
        font-size: 1.8rem;
        font-weight: 700;
        color: #16213e;
        margin-bottom: 0.2rem;
        letter-spacing: 0;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #596579;
        margin-bottom: 1.5rem;
        letter-spacing: 0;
    }
    .status-card, .insight-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .status-card h4 {
        margin: 0 0 0.3rem 0;
        font-size: 0.82rem;
        color: #596579;
        text-transform: uppercase;
        letter-spacing: 0;
    }
    .status-card .value {
        font-size: 1.45rem;
        font-weight: 700;
        color: #16213e;
    }
    .insight-headline {
        font-size: 1.08rem;
        font-weight: 700;
        color: #16213e;
        line-height: 1.45;
        margin-bottom: 0.25rem;
    }
    .insight-subhead {
        font-size: 0.86rem;
        color: #596579;
        margin-bottom: 0.8rem;
    }
    .method-note {
        font-size: 0.78rem;
        color: #6b7280;
        border-top: 1px solid #eef0f3;
        padding-top: 0.5rem;
        margin-top: 0.7rem;
    }
    .caveat {
        font-size: 0.78rem;
        color: #9a3412;
        margin-top: 0.25rem;
    }
    .insight-callout {
        background: #f0f2f6;
        border-radius: 8px;
        padding: 12px 16px;
        text-align: center;
        font-weight: 600;
        font-size: 0.95rem;
        margin-bottom: 8px;
        color: #16213e;
    }
</style>
""",
    unsafe_allow_html=True,
)

from discoursekit.ui.sidebar import render_sidebar
from discoursekit.ui.pages import (
    analyze,
    data_build,
    export_page,
    home,
    llm,
    qual,
    settings,
)


PAGE_MAP = {
    "홈": home.render,
    "데이터 만들기": data_build.render,
    "LLM 보정": llm.render,
    "분석 대시보드": analyze.render,
    "정성 분석": qual.render,
    "내보내기": export_page.render,
    "설정": settings.render,
}


current_page = render_sidebar(list(PAGE_MAP))
nav_override = st.session_state.pop("nav_page", None)
active_page = nav_override if nav_override in PAGE_MAP else current_page
PAGE_MAP.get(active_page, home.render)()
