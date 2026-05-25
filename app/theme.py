"""Editorial monochrome theme: typography, chrome CSS, chart styling.

Two custom faces (Stetica sans for chrome, TT Norms Pro Serif for display).
Ink-on-paper palette. One accent — ink-fill on hover. No color drama in charts.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

FONT_CSS = """
<style>
@font-face {
  font-family: 'Stetica';
  src: url('/app/static/fonts/stetica-regular.otf') format('opentype');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'Stetica';
  src: url('/app/static/fonts/stetica-medium.otf') format('opentype');
  font-weight: 500;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'Stetica';
  src: url('/app/static/fonts/stetica-bold.otf') format('opentype');
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'NLEdSerif';
  src: url('/app/static/fonts/serif-regular.otf') format('opentype');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'NLEdSerif';
  src: url('/app/static/fonts/serif-bold.otf') format('opentype');
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}

:root {
  --ink:        #111111;
  --ink-soft:   #4A4A4A;
  --ink-mute:   #7A7A75;
  --paper:      #FAFAF7;
  --paper-warm: #F1EFE9;
  --rule:       #1A1A1A;
  --hairline:   #DCD8CE;
}

html, body, [class*="css"], .stApp, .stMarkdown, .stChatMessage {
  font-family: 'Stetica', system-ui, sans-serif !important;
  color: var(--ink);
  background: var(--paper);
}

.block-container {
  padding-top: 2.4rem;
  padding-bottom: 4rem;
  max-width: 1080px;
}

/* Hide Streamlit chrome we don't want */
#MainMenu, footer, header [data-testid="stToolbar"] { visibility: hidden; }
header { background: var(--paper) !important; }

/* Display headline — serif */
.nl-display {
  font-family: 'NLEdSerif', Georgia, serif;
  font-weight: 400;
  font-size: clamp(2.6rem, 5vw, 3.6rem);
  letter-spacing: -0.02em;
  line-height: 0.95;
  color: var(--ink);
  margin: 0 0 0.4rem 0;
}
.nl-display .arrow {
  font-weight: 700;
  display: inline-block;
  transform: translateY(-0.04em);
  margin: 0 0.25rem;
}

.nl-tagline {
  font-family: 'Stetica', system-ui, sans-serif;
  font-weight: 400;
  font-size: 1.02rem;
  line-height: 1.5;
  color: var(--ink-soft);
  max-width: 56ch;
  margin: 0 0 2rem 0;
}

/* Kicker — small uppercase letter-spaced label */
.nl-kicker {
  font-family: 'Stetica', sans-serif;
  font-size: 0.68rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin-bottom: 0.5rem;
}

/* Metric block — pure typography, no card chrome */
.nl-metric {
  border-top: 1px solid var(--rule);
  padding-top: 0.8rem;
  margin-top: 1.4rem;
}
.nl-metric-row {
  display: flex;
  align-items: baseline;
  gap: 0.9rem;
  margin-bottom: 0.5rem;
}
.nl-metric-value {
  font-family: 'NLEdSerif', Georgia, serif;
  font-weight: 700;
  font-size: 2.2rem;
  letter-spacing: -0.01em;
  color: var(--ink);
  line-height: 1;
}
.nl-metric-aside {
  font-family: 'Stetica', sans-serif;
  font-size: 0.86rem;
  color: var(--ink-mute);
  letter-spacing: 0.04em;
}
.nl-metric-cap {
  font-family: 'Stetica', sans-serif;
  font-size: 0.86rem;
  color: var(--ink-soft);
  line-height: 1.55;
  max-width: 62ch;
}
.nl-term {
  border-bottom: 1px dotted var(--ink-mute);
  cursor: help;
  text-decoration: none;
  color: inherit;
}
.nl-term:hover {
  border-bottom-color: var(--ink);
  color: var(--ink);
}

/* Section rule */
.nl-section-label {
  font-family: 'Stetica', sans-serif;
  font-size: 0.68rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin: 2.4rem 0 0.7rem 0;
  border-top: 1px solid var(--hairline);
  padding-top: 0.7rem;
}

/* Sidebar polish */
[data-testid="stSidebar"] {
  background: var(--paper-warm) !important;
  border-right: 1px solid var(--hairline);
}
[data-testid="stSidebar"] .nl-side-h {
  font-family: 'NLEdSerif', Georgia, serif;
  font-weight: 700;
  font-size: 1.1rem;
  letter-spacing: -0.005em;
  margin: 0.4rem 0 0.6rem 0;
}
[data-testid="stSidebar"] .nl-side-sub {
  font-family: 'Stetica', sans-serif;
  font-size: 0.7rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin: 1.2rem 0 0.4rem 0;
}

/* Language toggle */
.nl-lang-row { display: flex; gap: 0; }
.nl-lang-row button {
  background: transparent !important;
  color: var(--ink) !important;
  border: 1px solid var(--rule) !important;
  border-radius: 0 !important;
  font-family: 'Stetica', sans-serif !important;
  font-weight: 500 !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase;
  padding: 0.35rem 0.9rem !important;
  font-size: 0.74rem !important;
  min-height: 0 !important;
}

/* Buttons (sample questions) */
.stButton > button {
  background: transparent !important;
  color: var(--ink) !important;
  border: 1px solid var(--rule) !important;
  border-radius: 0 !important;
  font-family: 'Stetica', sans-serif !important;
  font-weight: 400 !important;
  font-size: 0.92rem !important;
  text-align: left !important;
  padding: 0.85rem 1rem !important;
  line-height: 1.45 !important;
  transition: background 0.12s;
  white-space: normal !important;
  height: auto !important;
}
.stButton > button:hover {
  background: var(--ink) !important;
  color: var(--paper) !important;
}
.stButton > button p {
  color: inherit !important;
}

/* Chat input */
.stChatInput { border-top: 1px solid var(--rule) !important; }
.stChatInput textarea {
  font-family: 'Stetica', sans-serif !important;
  font-size: 1rem !important;
  color: var(--ink) !important;
  background: var(--paper) !important;
}

/* Code blocks — keep mono but on warm paper */
pre, code {
  background: var(--paper-warm) !important;
  color: var(--ink) !important;
  border: 1px solid var(--hairline) !important;
  border-radius: 0 !important;
  font-family: 'JetBrains Mono', 'IBM Plex Mono', ui-monospace, monospace !important;
}

/* Scalar metric block — flatten */
[data-testid="stMetric"] {
  background: transparent !important;
  border: none !important;
}
[data-testid="stMetricLabel"] {
  font-family: 'Stetica', sans-serif !important;
  font-size: 0.68rem !important;
  letter-spacing: 0.18em !important;
  text-transform: uppercase !important;
  color: var(--ink-mute) !important;
}
[data-testid="stMetricValue"] {
  font-family: 'NLEdSerif', Georgia, serif !important;
  font-weight: 700 !important;
  font-size: 2.4rem !important;
  color: var(--ink) !important;
}

/* Tables */
[data-testid="stDataFrame"] { border: 1px solid var(--rule); }

/* Expanders */
.streamlit-expanderHeader {
  font-family: 'Stetica', sans-serif !important;
  font-size: 0.78rem !important;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink) !important;
}

/* Sample card — wraps a button + difficulty kicker */
.nl-sample {
  display: block;
}
.nl-sample-kicker {
  font-family: 'Stetica', sans-serif;
  font-size: 0.62rem;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin: 0 0 0.4rem 0.05rem;
}

/* Chat message bubbles — strip default round chrome */
[data-testid="stChatMessage"] {
  background: transparent !important;
  border: 0 !important;
  padding: 0.4rem 0 1.4rem 0 !important;
}
[data-testid="stChatMessage"]:not(:first-child) {
  border-top: 1px solid var(--hairline) !important;
  padding-top: 1.4rem !important;
}

/* Remove the avatar/icon circle Streamlit injects — covers every variant */
[data-testid="stChatMessage"] > div:first-child,
[data-testid="chatAvatarIcon-user"],
[data-testid="chatAvatarIcon-assistant"],
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessage"] [class*="Avatar"],
[data-testid="stChatMessage"] svg {
  display: none !important;
}

/* The chat message body lives in second child after the avatar; pull it left */
[data-testid="stChatMessage"] > div:nth-child(2) {
  margin-left: 0 !important;
  padding-left: 0 !important;
  width: 100% !important;
}
</style>
"""


CHART_PALETTE = ["#111111", "#4A4A4A", "#7A7A75", "#A8A29E", "#1A1A1A"]


def inject_chrome() -> None:
    st.markdown(FONT_CSS, unsafe_allow_html=True)


def style_fig(fig: Any) -> Any:
    fig.update_layout(
        font_family="Stetica, system-ui, sans-serif",
        font_color="#111111",
        paper_bgcolor="#FAFAF7",
        plot_bgcolor="#FAFAF7",
        colorway=CHART_PALETTE,
        margin=dict(l=10, r=10, t=20, b=10),
    )
    fig.update_xaxes(gridcolor="#DCD8CE", zerolinecolor="#1A1A1A", tickcolor="#1A1A1A")
    fig.update_yaxes(gridcolor="#DCD8CE", zerolinecolor="#1A1A1A", tickcolor="#1A1A1A")
    return fig
