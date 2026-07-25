from __future__ import annotations

import sys
import types
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pyarrow as pa
import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"


class _RecordingStreamlit(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("streamlit")
        self.dataframes: list[Any] = []
        self.dataframe_kwargs: list[dict[str, Any]] = []

    def expander(self, *_: Any, **__: Any) -> Any:
        return nullcontext()

    def columns(self, count: int) -> list[Any]:
        return [nullcontext() for _ in range(count)]

    def dataframe(self, frame: Any, **kwargs: Any) -> None:
        self.dataframes.append(frame)
        self.dataframe_kwargs.append(kwargs)

    def markdown(self, *_: Any, **__: Any) -> None:
        pass

    def write(self, *_: Any, **__: Any) -> None:
        pass

    def error(self, *_: Any, **__: Any) -> None:
        pass


@pytest.fixture
def show_working_module(monkeypatch: pytest.MonkeyPatch) -> Any:
    fake_st = _RecordingStreamlit()
    fake_i18n = types.ModuleType("i18n")
    fake_i18n.t = lambda key: key  # type: ignore[attr-defined]
    fake_output = types.ModuleType("components.output")
    fake_output.confidence_label = lambda confidence: str(confidence)  # type: ignore[attr-defined]

    for name in [
        module_name
        for module_name in sys.modules
        if module_name == "components" or module_name.startswith("components.")
    ]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    monkeypatch.setitem(sys.modules, "i18n", fake_i18n)
    monkeypatch.setitem(sys.modules, "components.output", fake_output)
    monkeypatch.syspath_prepend(str(APP_DIR))

    from components import show_working as show_working_mod  # type: ignore[import-not-found]

    return show_working_mod, fake_st


def _result_with_mixed_trace_tokens() -> SimpleNamespace:
    return SimpleNamespace(
        trace=[
            {"node": "retrieve_context"},
            {
                "node": "generate_sql",
                "model": "codestral-latest",
                "input_tokens": 3376,
                "output_tokens": 62,
                "confidence": 1.0,
            },
            {
                "node": "explain_trace",
                "model": "codestral-latest",
                "input_tokens": 169,
                "output_tokens": 12,
            },
        ],
        confidence=1.0,
        repair_attempted=False,
        db_id="chinook",
        outcome=None,
        rationale="",
        error_kind=None,
    )


def test_trace_dataframe_is_arrow_serializable(show_working_module: Any) -> None:
    show_working_mod, fake_st = show_working_module

    show_working_mod.render_show_working(_result_with_mixed_trace_tokens())

    assert len(fake_st.dataframes) == 1
    pa.Table.from_pandas(fake_st.dataframes[0], preserve_index=False)


def test_trace_dataframe_uses_current_streamlit_width_api(
    show_working_module: Any,
) -> None:
    show_working_mod, fake_st = show_working_module

    show_working_mod.render_show_working(_result_with_mixed_trace_tokens())

    assert fake_st.dataframe_kwargs == [{"width": "stretch", "hide_index": True}]
