"""Show-working expander: pipeline trace, metadata, shape, rationale."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from components.output import confidence_label
from i18n import t
from nl_sql.agent.graph import PipelineRunResult


def render_show_working(result: PipelineRunResult) -> None:
    with st.expander(t("show_working")):
        trace_rows: list[dict[str, Any]] = []
        for entry in result.trace:
            trace_rows.append(
                {
                    "node": str(entry.get("node", "?")),
                    "model": str(entry.get("model", "—")),
                    "tokens_in": str(entry.get("input_tokens", "—")),
                    "tokens_out": str(entry.get("output_tokens", "—")),
                    "confidence": str(entry.get("confidence", "—")),
                }
            )
        if trace_rows:
            st.markdown(f"**{t('trace_header')}**")
            st.dataframe(
                pd.DataFrame(trace_rows),
                width="stretch",
                hide_index=True,
            )

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**{t('meta_header')}**")
            conf_label = confidence_label(result.confidence)
            st.markdown(f"- {t('confidence_label')}: **{conf_label}** ({result.confidence:.2f})")
            st.markdown(f"- {t('repair_attempted')}: {result.repair_attempted}")
            st.markdown(f"- {t('db_field')}: `{result.db_id}`")
        with col_b:
            st.markdown(f"**{t('shape_header')}**")
            if result.outcome and result.outcome.result:
                st.markdown(f"- {t('rows_returned')}: {result.outcome.result.row_count}")
                cols = ", ".join(result.outcome.result.columns) or "—"
                st.markdown(f"- {t('columns_field')}: {cols}")
            else:
                st.markdown(f"- {t('no_rows')}")
        if result.rationale:
            st.markdown(f"**{t('rationale_header')}**")
            st.write(result.rationale)
        if result.error_kind:
            st.error(f"{t('error_kind')}: {result.error_kind} — {result.error_message}")
