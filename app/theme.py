"""Editorial-warm light theme: typography, chrome CSS, chart styling.

Design read: a portfolio-grade NL→SQL product demo for technical
recruiters and data peers — calm, precise, editorial-warm (deliberately
*not* the blue/indigo SaaS default). Native Streamlit CSS, self-hosted
Manrope (UI + tabular figures, full Cyrillic) and JetBrains Mono (SQL).

Dials for this surface (it is a working tool, not a marketing page):
VARIANCE 4 · MOTION 2 (feedback-only transitions) · DENSITY 5.

System locks (taste pre-flight):
- Theme lock: light only.
- Colour lock: ONE accent — terracotta. No second hue anywhere.
- Shape lock: containers/cards/expanders 12px · inputs/buttons 8px ·
  chips + language pills full-pill.
- Shadows tinted to the warm ink, never pure black.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

FONT_CSS = """
<style>
/* Self-hosted variable fonts (served via enableStaticServing). */
@font-face {
  font-family: 'Manrope';
  src: url('/app/static/fonts/manrope-latin.woff2') format('woff2');
  font-weight: 200 800; font-style: normal; font-display: swap;
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+2000-206F, U+2074,
    U+20AC, U+2122, U+2190-2193, U+2212, U+2215;
}
@font-face {
  font-family: 'Manrope';
  src: url('/app/static/fonts/manrope-cyrillic.woff2') format('woff2');
  font-weight: 200 800; font-style: normal; font-display: swap;
  unicode-range: U+0301, U+0400-04FF, U+0500-052F, U+2116;
}
@font-face {
  font-family: 'JetBrains Mono';
  src: url('/app/static/fonts/jbmono-latin.woff2') format('woff2');
  font-weight: 400 600; font-style: normal; font-display: swap;
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+2000-206F, U+2074,
    U+20AC, U+2122, U+2212, U+2215;
}
@font-face {
  font-family: 'JetBrains Mono';
  src: url('/app/static/fonts/jbmono-cyrillic.woff2') format('woff2');
  font-weight: 400 600; font-style: normal; font-display: swap;
  unicode-range: U+0301, U+0400-04FF, U+0500-052F, U+2116;
}

:root {
  --bg:            #FCFBF9;
  --surface:       #FFFFFF;
  --panel:         #F5F3EF;
  --panel-2:       #EDE9E1;
  --border:        #E7E3DB;
  --border-strong: #D8D2C6;
  --text:          #1C1A17;
  --text-soft:     #423D35;
  --text-mute:     #6F6A61;
  --accent:        #C2541B;   /* terracotta — fills, icons, key marks */
  --accent-hover:  #9E3F12;
  --accent-ink:    #9A3D11;   /* accent TEXT on paper (AA-safe) */
  --accent-soft:   #F7ECE3;
  --accent-ring:   rgba(194, 84, 27, 0.24);
  --radius:        12px;
  --radius-sm:     8px;
  --radius-pill:   999px;
  --shadow-sm:     0 1px 2px rgba(28, 26, 23, 0.05), 0 1px 3px rgba(28, 26, 23, 0.05);
  --shadow-md:     0 6px 18px rgba(28, 26, 23, 0.09);
  --font:          'Manrope', system-ui, -apple-system, sans-serif;
  --mono:          'JetBrains Mono', ui-monospace, 'SFMono-Regular', monospace;

  /* legacy aliases */
  --ink: var(--text); --ink-soft: var(--text-soft); --ink-mute: var(--text-mute);
  --paper: var(--bg); --paper-warm: var(--panel); --rule: var(--border-strong);
  --hairline: var(--border);
}

html, body, .stApp, [data-testid="stAppViewContainer"],
.stMarkdown, .stMarkdown *, [data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] *,
.stChatMessage, [class*="css"], input, textarea, button, select,
[data-baseweb="select"] *, [data-baseweb="popover"] * {
  font-family: var(--font) !important;
}
.stApp, [data-testid="stAppViewContainer"] {
  background: var(--bg);
  color: var(--text);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
.tabular, .nl-metric-value, [data-testid="stMetricValue"] {
  font-variant-numeric: tabular-nums;
}

.block-container, [data-testid="stMainBlockContainer"] {
  padding-top: 2.6rem;
  padding-bottom: 4rem;
  max-width: 1140px;
}

/* Hide Streamlit chrome we don't want */
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {
  visibility: hidden;
}
/* Transparent fixed header still overlays the top bar — pass pointer
   events through to our controls, keep its own buttons live. */
[data-testid="stHeader"] { background: transparent !important; pointer-events: none; }
[data-testid="stHeader"] * { pointer-events: auto; }

/* Keyboard focus ring — accessibility, every interactive element */
a:focus-visible, button:focus-visible, [role="button"]:focus-visible,
input:focus-visible, textarea:focus-visible, summary:focus-visible {
  outline: 2px solid var(--accent) !important;
  outline-offset: 2px !important;
  border-radius: var(--radius-sm);
}

/* ---------- Sticky top bar ---------- */
.st-key-nl_topbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  padding: 0.45rem 0 0.55rem 0;
  margin-bottom: 0.9rem;
}
.nl-wordmark {
  font-weight: 700;
  font-size: 1.25rem;
  letter-spacing: -0.03em;
  color: var(--text);
  line-height: 1.1;
  white-space: nowrap;
}
.nl-wordmark .arrow, .nl-display .arrow { color: var(--accent); margin: 0 0.04em; }
.nl-context {
  font-size: 0.8rem;
  color: var(--text-mute);
  margin: 0 0 1.6rem 0;
}
.nl-context a { color: var(--accent-ink); text-decoration: none; border-bottom: 1px solid transparent; }
.nl-context a:hover { border-bottom-color: var(--accent-ink); }
.nl-context code {
  font-family: var(--mono) !important;
  background: var(--panel-2) !important;
  border: 0 !important;
  padding: 0.06rem 0.36rem !important;
  border-radius: 5px !important;
  font-size: 0.76rem !important;
  color: var(--text-soft) !important;
}

/* ---------- Hero ---------- */
.nl-display {
  font-weight: 800;
  font-size: clamp(2rem, 3.6vw, 2.8rem);
  letter-spacing: -0.035em;
  line-height: 1.04;
  color: var(--text);
  text-wrap: balance;
  margin: 0.5rem 0 0.5rem 0;
}
.nl-tagline {
  font-size: 1.05rem;
  font-weight: 400;
  line-height: 1.55;
  color: var(--text-soft);
  max-width: 60ch;
  text-wrap: pretty;
  margin: 0 0 1.9rem 0;
}

/* ---------- Stat cards ---------- */
.nl-kicker {
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-mute);
  margin-bottom: 0.55rem;
}
.nl-metric {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  padding: 1.15rem 1.3rem 1.35rem;
  height: 100%;
}
.nl-metric-row { display: flex; align-items: baseline; gap: 0.6rem; margin-bottom: 0.5rem; }
.nl-metric-value {
  font-weight: 800;
  font-size: 2rem;
  letter-spacing: -0.02em;
  color: var(--text);
  line-height: 1;
}
.nl-metric-aside {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--accent-ink);
  background: var(--accent-soft);
  border-radius: var(--radius-pill);
  padding: 0.14rem 0.6rem;
}
.nl-metric-cap { font-size: 0.86rem; color: var(--text-soft); line-height: 1.55; }

/* ---------- Methodology body (inside expander) ---------- */
.nl-method-body { font-size: 0.85rem; color: var(--text-soft); line-height: 1.62; }
.nl-term { border-bottom: 1px dotted var(--text-mute); cursor: help; color: inherit; }
.nl-term:hover { border-bottom-color: var(--accent); color: var(--accent-ink); }

/* ---------- Section label ---------- */
.nl-section-label {
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-mute);
  margin: 2.2rem 0 0.9rem 0;
}

/* ---------- Sample difficulty chip ---------- */
.nl-sample-kicker {
  display: inline-block;
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--accent-ink);
  background: var(--accent-soft);
  border-radius: var(--radius-pill);
  padding: 0.1rem 0.55rem;
  margin: 0 0 0.45rem 0.1rem;
}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] { background: var(--panel) !important; border-right: 1px solid var(--border); }
[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
[data-testid="stSidebar"] .nl-side-h {
  font-weight: 700; font-size: 1.05rem; letter-spacing: -0.02em; margin: 0.2rem 0 1rem 0;
}
[data-testid="stSidebar"] .nl-side-h .arrow { color: var(--accent); }
[data-testid="stSidebar"] .nl-side-sub {
  font-size: 0.7rem; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--text-mute); margin: 1.1rem 0 0.4rem 0;
}

/* ---------- Buttons (sample cards + generic) ---------- */
.stButton > button {
  background: var(--surface) !important;
  color: var(--text) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
  box-shadow: var(--shadow-sm);
  font-weight: 500 !important;
  font-size: 0.9rem !important;
  text-align: left !important;
  padding: 0.6rem 0.8rem !important;
  line-height: 1.4 !important;
  white-space: normal !important;
  height: auto !important;
  min-height: 0 !important;
  transition: border-color .14s, background .14s, box-shadow .14s, transform .14s;
}
.stButton > button:hover {
  border-color: var(--accent) !important;
  background: var(--accent-soft) !important;
  color: var(--accent-ink) !important;
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}
.stButton > button:active { transform: translateY(0) scale(0.992); box-shadow: var(--shadow-sm); }
.stButton > button p { color: inherit !important; font-weight: 500 !important; }

/* Primary button (active language) — accent fill, AA white text */
.stButton > button[data-testid="stBaseButton-primary"] {
  background: var(--accent) !important; color: #fff !important;
  border-color: var(--accent) !important; box-shadow: none !important;
}
.stButton > button[data-testid="stBaseButton-primary"]:hover {
  background: var(--accent-hover) !important; color: #fff !important;
  border-color: var(--accent-hover) !important; transform: none !important;
}

/* Language pills (EN · RU) — compact, centred */
.st-key-lang_en_btn .stButton > button,
.st-key-lang_ru_btn .stButton > button {
  text-align: center !important;
  padding: 0.56rem 0.2rem !important;
  font-size: 0.76rem !important; font-weight: 600 !important; letter-spacing: 0.08em !important;
  box-shadow: none !important; transform: none !important;
}
.st-key-lang_en_btn .stButton > button:hover,
.st-key-lang_ru_btn .stButton > button:hover { transform: none !important; }

/* Clear-chat — quiet full-width action */
.st-key-clear_chat_btn .stButton > button {
  text-align: center !important; color: var(--text-soft) !important;
  box-shadow: none !important; font-weight: 500 !important;
}

/* ---------- Selectbox ---------- */
[data-baseweb="select"] > div {
  background: var(--surface) !important;
  border-radius: var(--radius-sm) !important;
  border-color: var(--border) !important;
  box-shadow: var(--shadow-sm);
  min-height: 2.5rem;
}
[data-baseweb="select"] > div:hover { border-color: var(--border-strong) !important; }
[data-baseweb="select"] > div:focus-within {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px var(--accent-ring) !important;
}
[data-baseweb="menu"] [role="option"]:hover { background: var(--accent-soft) !important; }

/* Sliders / checkboxes accent */
[data-testid="stSlider"] [role="slider"] { background: var(--accent) !important; }
[data-baseweb="checkbox"] [data-checked="true"] { background: var(--accent) !important; border-color: var(--accent) !important; }

/* ---------- Chat input ---------- */
[data-testid="stChatInput"] {
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  box-shadow: var(--shadow-sm);
  background: var(--surface) !important;
}
[data-testid="stChatInput"]:focus-within {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px var(--accent-ring) !important;
}
[data-testid="stChatInput"] textarea { font-size: 1rem !important; color: var(--text) !important; background: transparent !important; }
[data-testid="stChatInput"] textarea::placeholder { color: var(--text-mute) !important; }
[data-testid="stChatInput"] button { background: var(--accent) !important; border-radius: var(--radius-sm) !important; color: #fff !important; }
[data-testid="stChatInput"] button:hover { background: var(--accent-hover) !important; }

/* ---------- Code ---------- */
pre, code, .stMarkdown code, .stMarkdown pre,
[data-testid="stCode"], [data-testid="stCode"] * { font-family: var(--mono) !important; }
[data-testid="stCode"], pre {
  background: var(--panel) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
}

/* ---------- Metric (scalar answer) ---------- */
[data-testid="stMetric"] {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  box-shadow: var(--shadow-sm);
  padding: 1rem 1.2rem !important;
}
[data-testid="stMetricLabel"] {
  font-size: 0.7rem !important; font-weight: 600 !important; letter-spacing: 0.1em !important;
  text-transform: uppercase !important; color: var(--text-mute) !important;
}
[data-testid="stMetricValue"] { font-weight: 800 !important; font-size: 2.2rem !important; color: var(--text) !important; }

/* ---------- Tables ---------- */
[data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; }

/* ---------- Expanders ---------- */
[data-testid="stExpander"] {
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  background: var(--surface) !important;
  box-shadow: var(--shadow-sm);
}
[data-testid="stExpander"] summary, .streamlit-expanderHeader {
  font-size: 0.82rem !important; font-weight: 600 !important; color: var(--text) !important;
}
[data-testid="stExpander"] summary:hover { color: var(--accent-ink) !important; }

/* ---------- Chat messages ---------- */
[data-testid="stChatMessage"] { background: transparent !important; border: 0 !important; padding: 0.4rem 0 1.4rem 0 !important; }
[data-testid="stChatMessage"]:not(:first-child) { border-top: 1px solid var(--border) !important; padding-top: 1.4rem !important; }
[data-testid="stChatMessage"] > div:first-child,
[data-testid="chatAvatarIcon-user"], [data-testid="chatAvatarIcon-assistant"],
[data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessage"] [class*="Avatar"] { display: none !important; }
[data-testid="stChatMessage"] > div:nth-child(2) { margin-left: 0 !important; padding-left: 0 !important; width: 100% !important; }

/* ---------- Scrollbar ---------- */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: var(--radius-pill); border: 2px solid var(--bg); }
::-webkit-scrollbar-thumb:hover { background: var(--text-mute); }
</style>
"""


CHART_PALETTE = ["#C2541B", "#1C1A17", "#9E3F12", "#6F6A61", "#D8862E"]


def inject_chrome() -> None:
    st.markdown(FONT_CSS, unsafe_allow_html=True)


def style_fig(fig: Any) -> Any:
    fig.update_layout(
        font_family="Manrope, system-ui, sans-serif",
        font_color="#1C1A17",
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        colorway=CHART_PALETTE,
        margin=dict(l=10, r=10, t=20, b=10),
    )
    fig.update_xaxes(gridcolor="#EDE9E1", zerolinecolor="#D8D2C6", tickcolor="#D8D2C6")
    fig.update_yaxes(gridcolor="#EDE9E1", zerolinecolor="#D8D2C6", tickcolor="#D8D2C6")
    return fig
