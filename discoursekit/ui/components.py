"""Reusable UI components for DiscourseKit.

All shared widgets, cards, status indicators, and layout helpers.
"""

import streamlit as st
from typing import Optional


# ─────────────────────────────────────────────
# Metric Cards
# ─────────────────────────────────────────────

def metric_card(label: str, value: str | int, delta: str = "", help_text: str = ""):
    """Render a styled metric card, responsive via CSS clamp() in global styles."""
    delta_html = f'<span style="color:#2ec4b6;font-size:0.8rem;">{delta}</span>' if delta else ""
    # Format numeric values with comma separator; leave strings as-is
    if isinstance(value, (int, float)):
        display_value = f"{value:,.0f}" if isinstance(value, float) else f"{value:,}"
    else:
        display_value = str(value)
    st.markdown(f"""
    <div class="status-card">
        <h4>{label}</h4>
        <div class="value">{display_value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)
    if help_text:
        st.caption(help_text)


def metric_row(metrics: list[tuple[str, str | int, str]]):
    """Render multiple metrics in a row. Each tuple: (label, value, delta)."""
    cols = st.columns(len(metrics))
    for col, (label, value, delta) in zip(cols, metrics):
        with col:
            metric_card(label, value, delta)


# ─────────────────────────────────────────────
# Progress / Status
# ─────────────────────────────────────────────

def pipeline_progress(current_step: int, total_steps: int = 5):
    """Render a step progress indicator."""
    steps = ["수집", "정제", "LLM", "분석", "리포트"]
    cols = st.columns(total_steps)
    for i, (col, name) in enumerate(zip(cols, steps)):
        with col:
            if i < current_step:
                st.markdown(f"✅ **{name}**")
            elif i == current_step:
                st.markdown(f"🔄 **{name}**")
            else:
                st.markdown(f"⬜ {name}")


def job_status_badge(status: str) -> str:
    """Return HTML badge for job status."""
    colors = {
        "running": "#ffc107",
        "success": "#28a745",
        "failed": "#dc3545",
        "cancelled": "#6c757d",
    }
    color = colors.get(status, "#6c757d")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.8rem;">{status}</span>'


# ─────────────────────────────────────────────
# Section Headers
# ─────────────────────────────────────────────

def page_header(title: str, description: str = ""):
    """Render a page header with optional description."""
    st.markdown(f'<div class="main-header">{title}</div>', unsafe_allow_html=True)
    if description:
        st.markdown(f'<div class="sub-header">{description}</div>', unsafe_allow_html=True)


def section_header(title: str, icon: str = ""):
    """Render a section header within a page."""
    prefix = f"{icon} " if icon else ""
    st.markdown(f"### {prefix}{title}")


# ─────────────────────────────────────────────
# Data Display
# ─────────────────────────────────────────────

def info_table(data: dict[str, str]):
    """Render a simple key-value info table."""
    rows = "".join(f"<tr><td><strong>{k}</strong></td><td>{v}</td></tr>" for k, v in data.items())
    st.markdown(f"""
    <table style="width:100%;border-collapse:collapse;">
        {rows}
    </table>
    """, unsafe_allow_html=True)


def empty_state(message: str, icon: str = "📋"):
    """Render an empty state placeholder."""
    st.markdown(f"""
    <div style="text-align:center;padding:3rem;color:#adb5bd;">
        <div style="font-size:3rem;">{icon}</div>
        <p style="font-size:1.1rem;margin-top:1rem;">{message}</p>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# File Upload
# ─────────────────────────────────────────────

def file_upload_area(
    label: str,
    accepted_types: list[str],
    help_text: str = "",
    multiple: bool = True,
):
    """Render a file upload area with type hints."""
    files = st.file_uploader(
        label,
        type=accepted_types,
        accept_multiple_files=multiple,
        help=help_text,
    )
    return files


# ─────────────────────────────────────────────
# Confirmation Dialog
# ─────────────────────────────────────────────

def confirm_action(key: str, message: str, button_label: str = "실행") -> bool:
    """Two-step confirmation: checkbox + button."""
    confirmed = st.checkbox(message, key=f"confirm_{key}")
    if confirmed:
        return st.button(button_label, key=f"btn_{key}", type="primary")
    return False


# ─────────────────────────────────────────────
# API Key Input
# ─────────────────────────────────────────────

def api_key_input(slot_name: str, key: str = "") -> str:
    """Render a masked API key input with slot label."""
    return st.text_input(
        f"🔑 {slot_name}",
        value=key,
        type="password",
        help="Google Cloud 프로젝트별로 서로 다른 키를 사용하면 quota가 독립됩니다.",
    )
