"""Unit tests for instance-aware synthetic few-shots (A3, CHASE-SQL)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from nl_sql.agent.nodes import context_builder as cb_module
from nl_sql.agent.nodes.context_builder import make_context_builder_node
from nl_sql.agent.nodes.fewshot_synthesis import (
    MAX_SYNTHETIC_FEWSHOTS,
    parse_synthetic_pairs,
    synthesize_fewshots,
)
from nl_sql.llm.providers.base import GenerateRequest, GenerateResponse
from nl_sql.schema_index.indexer import FewShotHit, SchemaQueryHit
from nl_sql.schema_index.retriever import ContextBundle

_PAIRS_JSON = json.dumps(
    [
        {"question": "How many schools are in Fresno?", "sql": "SELECT COUNT(*) FROM schools"},
        {"question": "List all districts", "sql": "SELECT DISTINCT district FROM schools"},
    ]
)


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, text: str = _PAIRS_JSON, *, raises: Exception | None = None) -> None:
        self.text = text
        self.raises = raises
        self.requests: list[GenerateRequest] = []

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        self.requests.append(req)
        if self.raises is not None:
            raise self.raises
        return GenerateResponse(text=self.text, model=self.model)


def _bundle(fewshots: list[FewShotHit] | None = None) -> ContextBundle:
    hit = SchemaQueryHit(
        chunk_id="c1",
        table_name="schools",
        db_id="california_schools",
        text="Table: schools (rows=10)\nColumns:\n  - district: TEXT [NULL]\n",
        distance=0.1,
        metadata={},
    )
    return ContextBundle(
        db_id="california_schools",
        question="How many schools are there?",
        schema_hits=[hit],
        fk_neighbours=[],
        fewshots=fewshots
        or [
            FewShotHit(
                example_id="train-1",
                db_id="other_db",
                question="retrieved q",
                sql="SELECT 1",
                distance=0.2,
                metadata={},
            )
        ],
    )


# --- parse_synthetic_pairs ---


def test_parse_happy_path_with_fence() -> None:
    text = f"```json\n{_PAIRS_JSON}\n```"
    pairs = parse_synthetic_pairs(text)
    assert len(pairs) == 2
    assert pairs[0] == (
        "How many schools are in Fresno?",
        "SELECT COUNT(*) FROM schools",
    )


def test_parse_drops_junk_entries() -> None:
    text = json.dumps(
        [
            {"question": "ok", "sql": "SELECT 1"},
            {"question": "", "sql": "SELECT 2"},  # empty question
            {"question": "no sql", "sql": ""},  # empty sql
            {"question": "prose", "sql": "the answer is 4"},  # no SELECT
            "not a dict",
            {"question": 5, "sql": None},
        ]
    )
    assert parse_synthetic_pairs(text) == [("ok", "SELECT 1")]


def test_parse_non_list_and_garbage_yield_empty() -> None:
    assert parse_synthetic_pairs("") == []
    assert parse_synthetic_pairs("no json here") == []
    assert parse_synthetic_pairs(json.dumps({"question": "q", "sql": "SELECT 1"})) == []


def test_parse_caps_at_max() -> None:
    many = json.dumps(
        [{"question": f"q{i}", "sql": f"SELECT {i}"} for i in range(MAX_SYNTHETIC_FEWSHOTS + 3)]
    )
    assert len(parse_synthetic_pairs(many)) == MAX_SYNTHETIC_FEWSHOTS


# --- synthesize_fewshots ---


def test_synthesize_builds_hits_and_prompt() -> None:
    provider = FakeProvider()
    hits = synthesize_fewshots(
        provider,
        question="How many schools are there?",
        db_id="california_schools",
        dialect="sqlite",
        schema_text="Table: schools",
        num_examples=3,
    )
    assert [h.example_id for h in hits] == ["synthetic-1", "synthetic-2"]
    assert all(h.db_id == "california_schools" for h in hits)
    assert all(h.metadata == {"source": "synthetic"} for h in hits)
    prompt = provider.requests[0].prompt
    assert "Table: schools" in prompt
    assert "How many schools are there?" in prompt
    assert "3" in prompt
    assert "sqlite" in prompt
    # Deterministic call: temperature pinned to 0 for cache replay.
    assert provider.requests[0].temperature == 0.0


# --- context_builder wiring ---


def _run_node(
    monkeypatch: pytest.MonkeyPatch,
    *,
    selection: str,
    provider: FakeProvider | None,
) -> dict[str, Any]:
    monkeypatch.setattr(cb_module, "retrieve_context", lambda *a, **kw: _bundle())
    node = make_context_builder_node(
        object(),  # type: ignore[arg-type] — retrieve_context is patched out
        fewshot_selection=selection,
        fewshot_synthesis_provider=provider,
    )
    return dict(
        node({"question": "How many schools are there?", "db_id": "california_schools"})  # type: ignore[arg-type]
    )


def test_node_synthetic_replaces_retrieved_shots(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeProvider()
    out = _run_node(monkeypatch, selection="synthetic", provider=provider)
    bundle = out["context"]
    assert [f.example_id for f in bundle.fewshots] == ["synthetic-1", "synthetic-2"]
    assert any("fewshot_selection=synthetic" in n for n in bundle.notes)
    step = out["trace"][-1]
    assert step["fewshots"] == 2
    assert "fewshot_synthesis" not in step
    # The synthesis prompt must carry the rendered schema of the bundle.
    assert "Table: schools" in provider.requests[0].prompt


def test_node_synthetic_falls_back_on_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeProvider(raises=RuntimeError("boom"))
    out = _run_node(monkeypatch, selection="synthetic", provider=provider)
    bundle = out["context"]
    assert [f.example_id for f in bundle.fewshots] == ["train-1"]
    step = out["trace"][-1]
    assert "fewshot_synthesis failed" in str(step["fewshot_synthesis"])


def test_node_synthetic_falls_back_on_empty_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeProvider(text="no json")
    out = _run_node(monkeypatch, selection="synthetic", provider=provider)
    bundle = out["context"]
    assert [f.example_id for f in bundle.fewshots] == ["train-1"]
    step = out["trace"][-1]
    assert "no pairs" in str(step["fewshot_synthesis"])


def test_node_synthetic_without_provider_is_dense(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _run_node(monkeypatch, selection="synthetic", provider=None)
    bundle = out["context"]
    assert [f.example_id for f in bundle.fewshots] == ["train-1"]
    assert "fewshot_synthesis" not in out["trace"][-1]


def test_node_dense_never_calls_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeProvider()
    out = _run_node(monkeypatch, selection="dense", provider=provider)
    assert provider.requests == []
    assert [f.example_id for f in out["context"].fewshots] == ["train-1"]
