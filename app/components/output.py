"""Output renderers: scalar, sentence, table, chart + label helpers."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from i18n import t
from nl_sql.render.formats import (
    BarChart,
    LineChart,
    OutputFormat,
    PieChart,
    Scalar,
    ScatterChart,
    Sentence,
    Table,
)
from nl_sql.render.labels import classify_scalar_label
from theme import style_fig


def scalar_metric_label(column: str) -> str:
    """Translate a raw SQL column label into a localized business label
    (audit P2 #5). Engine columns like ``COUNT(DISTINCT s.CDSCode)`` become
    "Count" / "Количество"; identifier-like columns (``total_revenue``) are
    kept as-is."""
    kind = classify_scalar_label(column)
    if kind == "identifier":
        return column
    return t(f"scalar_label_{kind}")


def confidence_label(value: float) -> str:
    if value >= 0.8:
        return t("conf_high")
    if value >= 0.5:
        return t("conf_med")
    if value > 0.0:
        return t("conf_low")
    return t("conf_unknown")


def render_chart(
    spec: BarChart | LineChart | PieChart | ScatterChart,
    df: pd.DataFrame,
) -> None:
    if isinstance(spec, BarChart):
        fig = px.bar(df, x=spec.x_field, y=spec.y_fields)
    elif isinstance(spec, LineChart):
        fig = px.line(df, x=spec.x_field, y=spec.y_fields)
    elif isinstance(spec, PieChart):
        y_field = spec.y_fields[0] if spec.y_fields else df.columns[1]
        fig = px.pie(df, names=spec.x_field, values=y_field)
    else:
        y_field = spec.y_fields[0] if spec.y_fields else df.columns[1]
        fig = px.scatter(df, x=spec.x_field, y=y_field)
    st.plotly_chart(style_fig(fig), use_container_width=True)


def render_output(output: OutputFormat | None, *, caption: str) -> None:
    if isinstance(output, Scalar):
        st.metric(scalar_metric_label(output.column), str(output.value))
    elif isinstance(output, Sentence):
        st.markdown(
            f"<div style=\"font-family:'NLEdSerif',Georgia,serif; "
            f"font-size:1.25rem; line-height:1.45; color:var(--ink); "
            f'margin:0.4rem 0 0.6rem;">{output.text}</div>',
            unsafe_allow_html=True,
        )
        if output.fields:
            st.json(output.fields, expanded=False)
    elif isinstance(output, Table):
        df = pd.DataFrame(output.rows, columns=output.columns)
        st.dataframe(df, use_container_width=True, hide_index=True)
    elif isinstance(output, BarChart | LineChart | PieChart | ScatterChart):
        df = pd.DataFrame(output.rows, columns=output.columns)
        render_chart(output, df)
    elif output is None:
        st.warning(t("no_output_warning"))
    if caption:
        st.caption(caption)
