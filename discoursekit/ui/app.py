"""DiscourseKit Streamlit application."""

from __future__ import annotations

import streamlit as st


st.set_page_config(
    page_title="DiscourseKit",
    page_icon="DK",
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown(
    """
<style>
    /* ── Base (Desktop) ── */
    [data-testid="stSidebar"] {
        background-color: #f8f9fa;
        border-right: 1px solid #e9ecef;
    }
    [data-testid="stSidebar"] .stRadio > label {
        font-weight: 500;
    }
    .main-header {
        font-size: clamp(1.3rem, 4vw, 1.8rem);
        font-weight: 700;
        color: #16213e;
        margin-bottom: 0.2rem;
        letter-spacing: 0;
    }
    .sub-header {
        font-size: clamp(0.82rem, 2.5vw, 0.95rem);
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
        font-size: clamp(0.7rem, 2vw, 0.82rem);
        color: #596579;
        text-transform: uppercase;
        letter-spacing: 0;
    }
    .status-card .value {
        font-size: clamp(1.1rem, 3.5vw, 1.45rem);
        font-weight: 700;
        color: #16213e;
    }
    .insight-headline {
        font-size: clamp(0.92rem, 3vw, 1.08rem);
        font-weight: 700;
        color: #16213e;
        line-height: 1.45;
        margin-bottom: 0.25rem;
    }
    .insight-subhead {
        font-size: clamp(0.78rem, 2.2vw, 0.86rem);
        color: #596579;
        margin-bottom: 0.8rem;
    }
    .method-note {
        font-size: clamp(0.7rem, 2vw, 0.78rem);
        color: #6b7280;
        border-top: 1px solid #eef0f3;
        padding-top: 0.5rem;
        margin-top: 0.7rem;
    }
    .caveat {
        font-size: clamp(0.7rem, 2vw, 0.78rem);
        color: #9a3412;
        margin-top: 0.25rem;
    }
    .insight-callout {
        background: #f0f2f6;
        border-radius: 8px;
        padding: 12px 16px;
        text-align: center;
        font-weight: 600;
        font-size: clamp(0.82rem, 2.5vw, 0.95rem);
        margin-bottom: 8px;
        color: #16213e;
    }

    /* ── Mobile & Tablet shared: ≤1024px ── */
    @media (max-width: 1024px) {
        /* Ensure main content fills available width */
        .main .block-container {
            max-width: 100% !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        /* Plotly charts: ensure they don't overflow */
        [data-testid="stPlotlyChart"] {
            overflow-x: auto !important;
        }
        /* Dataframes: horizontal scroll */
        [data-testid="stDataFrame"] {
            overflow-x: auto !important;
        }
    }

    /* ── Mobile: ≤768px ── */
    @media (max-width: 768px) {
        [data-testid="stSidebar"] {
            min-width: 0 !important;
            width: 100% !important;
        }
        /* Stack metric columns: 2 per row */
        [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 0.4rem !important;
        }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            min-width: 45% !important;
            flex: 1 1 45% !important;
        }
        /* Reduce metric card padding */
        .status-card, .insight-card {
            padding: 0.7rem 0.8rem;
            margin-bottom: 0.5rem;
        }
        /* Tighter main content padding */
        .main .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
            padding-top: 1rem !important;
        }
        /* Expander content padding */
        [data-testid="stExpander"] details {
            padding: 0.3rem !important;
        }
    }

    /* ── Small mobile: ≤480px ── */
    @media (max-width: 480px) {
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            min-width: 100% !important;
            flex: 1 1 100% !important;
        }
        .main-header {
            font-size: 1.2rem;
        }
        .status-card .value {
            font-size: 1rem;
        }
        .insight-callout {
            padding: 8px 10px;
            font-size: 0.8rem;
        }
    }

    /* ── Tablet: 769px ~ 1024px ── */
    @media (min-width: 769px) and (max-width: 1024px) {
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            min-width: 30% !important;
            flex: 1 1 30% !important;
        }
    }

    /* ── Touch-friendly elements ── */
    @media (pointer: coarse) {
        /* Bigger tap targets for buttons */
        .stButton > button {
            min-height: 44px !important;
            padding: 0.5rem 1rem !important;
            font-size: 0.9rem !important;
        }
        /* Larger select/input fields */
        .stSelectbox, .stTextInput, .stNumberInput, .stDateInput {
            min-height: 44px;
        }
        .stSelectbox [data-baseweb="select"],
        .stTextInput input,
        .stNumberInput input {
            min-height: 44px !important;
            font-size: 16px !important;  /* Prevents iOS zoom on focus */
        }
        /* Expander headers: easier to tap */
        [data-testid="stExpander"] summary {
            min-height: 44px !important;
            display: flex;
            align-items: center;
        }
    }

    /* ── Streamlit metric widget responsive ── */
    [data-testid="stMetric"] {
        overflow-wrap: break-word;
        word-break: break-word;
    }
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: clamp(1rem, 3.5vw, 1.6rem);
    }
    [data-testid="stMetric"] [data-testid="stMetricLabel"] {
        font-size: clamp(0.7rem, 2vw, 0.85rem);
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
