"""DiscourseKit — Main Streamlit Application.

Run: streamlit run discoursekit/ui/app.py
"""

import streamlit as st

# ─────────────────────────────────────────────
# Page config (must be first Streamlit call)
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="DiscourseKit",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #f8f9fa;
        border-right: 1px solid #e9ecef;
    }
    [data-testid="stSidebar"] .stRadio > label {
        font-weight: 500;
    }

    /* Main header */
    .main-header {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1a1a2e;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #6c757d;
        margin-bottom: 1.5rem;
    }

    /* Status cards */
    .status-card {
        background: #ffffff;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .status-card h4 {
        margin: 0 0 0.3rem 0;
        font-size: 0.85rem;
        color: #6c757d;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .status-card .value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #1a1a2e;
    }

    /* Step indicator */
    .step-indicator {
        display: flex;
        gap: 0.3rem;
        margin-bottom: 1rem;
    }
    .step-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: #dee2e6;
    }
    .step-dot.active {
        background: #4361ee;
    }
    .step-dot.done {
        background: #2ec4b6;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────
from discoursekit.ui.sidebar import render_sidebar

current_page = render_sidebar()

# ─────────────────────────────────────────────
# Page routing
# ─────────────────────────────────────────────
from discoursekit.ui.pages import home, ingest, clean, llm, analyze, settings

PAGE_MAP = {
    "홈": home.render,
    "1. 수집": ingest.render,
    "2. 정제": clean.render,
    "3. LLM 분류": llm.render,
    "4. 분석·리포트": analyze.render,
    "설정": settings.render,
}

# Support CTA navigation (buttons that redirect to another page)
nav_override = st.session_state.pop("nav_page", None)
active_page = nav_override if nav_override in PAGE_MAP else current_page

if active_page in PAGE_MAP:
    PAGE_MAP[active_page]()
else:
    home.render()
