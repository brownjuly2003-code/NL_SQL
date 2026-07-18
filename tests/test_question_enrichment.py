"""Unit tests for question enrichment (A4, E-SQL)."""

from __future__ import annotations

from typing import Any

import pytest

from nl_sql.agent.nodes import context_builder as cb_module
from nl_sql.agent.nodes.context_builder import make_context_builder_node
from nl_sql.agent.nodes.generate_sql import make_generate_sql_node
from nl_sql.agent.nodes.question_enrichment import clean_enriched_text, enrich_question
from nl_sql.llm.providers.base import GenerateRequest, GenerateResponse
from nl_sql.schema_index.indexer import FewShotHit, SchemaQueryHit
from nl_sql.schema_index.retriever import ContextBundle

_RESTATEMENT = "1. Filter schools where district is 'Fresno'.\n2. Count the remaining rows."


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, text: str = _RESTATEMENT, *, raises: Exception | None = None) -> None:
        self.text = text
        self.raises = raises
        self.requests: list[GenerateRequest] = []

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        self.requests.append(req)
        if self.raises is not None:
            raise self.raises
        return GenerateResponse(text=self.text, model=self.model)


def _bundle() -> ContextBundle:
    hit = SchemaQueryHit(
        chunk_id="c1",
        table_name="schools",
        db_id="california_schools",
        text="Table: schools (rows=10)\nColumns:\n  - district: TEXT [NULL]\n",
        distance=0.1,
        metadata={},
    )
    shot = FewShotHit(
        example_id="train-1",
        db_id="other_db",
        question="retrieved q",
        sql="SELECT 1",
        distance=0.2,
        metadata={},
    )
    return ContextBundle(
        db_id="california_schools",
        question="How many schools are in Fresno?",
        schema_hits=[hit],
        fk_neighbours=[],
        fewshots=[shot],
    )


# --- clean_enriched_text ---


def test_clean_strips_fences_and_whitespace() -> None:
    assert clean_enriched_text(f"```text\n{_RESTATEMENT}\n```") == _RESTATEMENT
    assert clean_enriched_text("  \n") == ""
    assert clean_enriched_text("") == ""


def test_clean_truncates_runaway_reply() -> None:
    long = "\n".join(f"{i}. step {'x' * 50}" for i in range(100))
    cleaned = clean_enriched_text(long)
    assert len(cleaned) <= 2000
    # Cut lands on a line boundary, not mid-word.
    assert cleaned.endswith(tuple("0123456789x."))
    assert "\n" in cleaned


# --- enrich_question ---


def test_enrich_question_builds_prompt() -> None:
    provider = FakeProvider()
    out = enrich_question(
        provider,
        question="How many schools are in Fresno?",
        schema_text="Table: schools",
    )
    assert out == _RESTATEMENT
    prompt = provider.requests[0].prompt
    assert "Table: schools" in prompt
    assert "How many schools are in Fresno?" in prompt
    assert provider.requests[0].temperature == 0.0


# --- context_builder wiring ---


def _run_node(
    monkeypatch: pytest.MonkeyPatch,
    *,
    provider: FakeProvider | None,
) -> dict[str, Any]:
    monkeypatch.setattr(cb_module, "retrieve_context", lambda *a, **kw: _bundle())
    node = make_context_builder_node(
        object(),  # type: ignore[arg-type] — retrieve_context is patched out
        enrichment_provider=provider,
    )
    return dict(
        node({"question": "How many schools are in Fresno?", "db_id": "california_schools"})  # type: ignore[arg-type]
    )


def test_node_enrichment_lands_in_state(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeProvider()
    out = _run_node(monkeypatch, provider=provider)
    assert out["enriched_question"] == _RESTATEMENT
    step = out["trace"][-1]
    assert step["question_enriched"] is True
    assert "question_enrichment" not in step
    # Prompt carried the rendered schema of the bundle.
    assert "Table: schools" in provider.requests[0].prompt
    # Few-shots untouched — enrichment is orthogonal to A3.
    assert [f.example_id for f in out["context"].fewshots] == ["train-1"]


def test_node_enrichment_failure_is_soft(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeProvider(raises=RuntimeError("boom"))
    out = _run_node(monkeypatch, provider=provider)
    assert out["enriched_question"] == ""
    step = out["trace"][-1]
    assert step["question_enriched"] is False
    assert "question_enrichment failed" in str(step["question_enrichment"])


def test_node_enrichment_empty_reply_noted(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeProvider(text="   ")
    out = _run_node(monkeypatch, provider=provider)
    assert out["enriched_question"] == ""
    assert "empty" in str(out["trace"][-1]["question_enrichment"])


def test_node_off_no_provider_no_state_noise(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _run_node(monkeypatch, provider=None)
    assert out["enriched_question"] == ""
    step = out["trace"][-1]
    assert "question_enriched" not in step
    assert "question_enrichment" not in step


# --- generate_sql rendering ---


class CaptureProvider:
    name = "cap"
    model = "cap-model"

    def __init__(self) -> None:
        self.requests: list[GenerateRequest] = []

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        self.requests.append(req)
        return GenerateResponse(text='{"sql": "SELECT 1"}', model=self.model)


def _generate_prompt(enriched: str) -> str:
    provider = CaptureProvider()
    node = make_generate_sql_node(provider)
    state: dict[str, Any] = {
        "question": "How many schools are in Fresno?",
        "dialect": "sqlite",
        "context": _bundle(),
        "enriched_question": enriched,
    }
    node(state)  # type: ignore[arg-type]
    return provider.requests[0].prompt


def test_generate_renders_enriched_next_to_question() -> None:
    prompt = _generate_prompt(_RESTATEMENT)
    assert "How many schools are in Fresno?" in prompt
    assert "Explicit restatement" in prompt
    assert _RESTATEMENT in prompt
    # Original question comes first — it stays authoritative.
    assert prompt.index("How many schools are in Fresno?") < prompt.index("Explicit restatement")


def test_generate_prompt_unchanged_when_off() -> None:
    assert _generate_prompt("") == _generate_prompt("   ")
    assert "Explicit restatement" not in _generate_prompt("")
