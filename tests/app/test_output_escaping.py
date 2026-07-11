"""Security test: the Sentence renderer must escape untrusted text.

`app/components/output.py` renders `Sentence.text` inside `st.markdown(...,
unsafe_allow_html=True)`. Sentence text can carry model-generated SQL or parser
error strings, so a `<script>`/`<img onerror>` payload must be HTML-escaped
before it reaches the markup — otherwise it is a stored-XSS vector in the demo.

The app package imports `streamlit`, `i18n`, and `theme` at module load; none are
available (or wanted) in the unit-test process, so we stub them in sys.modules
and put `app/` on the path before importing the component.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"


class _RecordingStreamlit(types.ModuleType):
    """Minimal `streamlit` stand-in that records markdown payloads."""

    def __init__(self) -> None:
        super().__init__("streamlit")
        self.markdown_calls: list[str] = []

    def markdown(self, body: str, **_: Any) -> None:
        self.markdown_calls.append(body)

    def json(self, *_: Any, **__: Any) -> None:
        pass

    def caption(self, *_: Any, **__: Any) -> None:
        pass

    def metric(self, *_: Any, **__: Any) -> None:
        pass

    def warning(self, *_: Any, **__: Any) -> None:
        pass


@pytest.fixture
def output_module(monkeypatch: pytest.MonkeyPatch) -> Any:
    fake_st = _RecordingStreamlit()
    fake_i18n = types.ModuleType("i18n")
    fake_i18n.t = lambda key: key  # type: ignore[attr-defined]
    fake_theme = types.ModuleType("theme")
    fake_theme.style_fig = lambda fig: fig  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    monkeypatch.setitem(sys.modules, "i18n", fake_i18n)
    monkeypatch.setitem(sys.modules, "theme", fake_theme)
    monkeypatch.syspath_prepend(str(APP_DIR))
    # Drop the whole `components` namespace so the module re-imports and rebinds
    # the freshly stubbed `streamlit` (a cached submodule would keep the old st).
    for name in [m for m in sys.modules if m == "components" or m.startswith("components.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    from components import output as output_mod  # type: ignore[import-not-found]

    return output_mod, fake_st


def test_sentence_html_is_escaped(output_module: Any) -> None:
    output_mod, fake_st = output_module
    from nl_sql.render.formats import Sentence

    payload = "<script>alert('xss')</script> & <img src=x onerror=alert(1)>"
    output_mod.render_output(Sentence(text=payload), caption="")

    rendered = "\n".join(fake_st.markdown_calls)
    assert "<script>" not in rendered
    assert "onerror=alert(1)>" not in rendered
    # The escaped form must be present instead.
    assert "&lt;script&gt;" in rendered
    assert "&amp;" in rendered


def test_benign_sentence_text_survives(output_module: Any) -> None:
    output_mod, fake_st = output_module
    from nl_sql.render.formats import Sentence

    output_mod.render_output(Sentence(text="There are 4 albums."), caption="")

    rendered = "\n".join(fake_st.markdown_calls)
    assert "There are 4 albums." in rendered
