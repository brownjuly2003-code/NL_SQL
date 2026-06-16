"""Hero block + stat cards + methodology note + sample question cards."""

from __future__ import annotations

import streamlit as st

from i18n import t
from samples import SAMPLE_QUESTIONS


def render_welcome(db_id: str) -> None:
    st.markdown(
        "<div class='nl-display'>NL<span class='arrow'>→</span>SQL</div>",
        unsafe_allow_html=True,
    )
    st.markdown(f"<div class='nl-tagline'>{t('tagline')}</div>", unsafe_allow_html=True)

    col_a, col_b = st.columns(2, gap="medium")
    with col_a:
        st.markdown(
            f"""
            <div class='nl-metric'>
              <div class='nl-kicker'>{t("metric_kicker")}</div>
              <div class='nl-metric-row'>
                <span class='nl-metric-value'>{t("metric_value")}</span>
                <span class='nl-metric-aside'>{t("metric_percent")}</span>
              </div>
              <div class='nl-metric-cap'>{t("metric_caption")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            f"""
            <div class='nl-metric'>
              <div class='nl-kicker'>{t("research_kicker")}</div>
              <div class='nl-metric-row'>
                <span class='nl-metric-value'>{t("research_value")}</span>
              </div>
              <div class='nl-metric-cap'>{t("research_short")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander(t("methodology_label"), expanded=False):
        st.markdown(
            f"<div class='nl-method-body'>{t('research_caption')}</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        f"<div class='nl-section-label'>{t('ask_intro_label')}</div>",
        unsafe_allow_html=True,
    )

    samples = SAMPLE_QUESTIONS.get(db_id)
    if not samples:
        st.info(t("no_samples"))
        return

    cols = st.columns(len(samples), gap="medium")
    diff_map = {
        "simple": t("diff_simple"),
        "moderate": t("diff_moderate"),
        "challenging": t("diff_challenging"),
    }
    for col, (difficulty, question) in zip(cols, samples, strict=False):
        with col:
            st.markdown(
                f"<div class='nl-sample-kicker'>{diff_map.get(difficulty, difficulty)}</div>",
                unsafe_allow_html=True,
            )
            if st.button(
                question,
                key=f"sample_{db_id}_{hash(question)}",
                use_container_width=True,
            ):
                st.session_state.pending_question = question
                st.rerun()
