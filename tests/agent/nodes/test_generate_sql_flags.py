"""Unit tests for `make_generate_sql_node` PipelineConfig flag plumbing.

Closes Kimi audit 2026-05-25 P1.5: NLSQL_M_SCHEMA / NLSQL_DAC moved off
`os.environ` reads inside the node into typed `PipelineConfig` fields. The
tests assert the node respects the flags directly instead of monkey-patching
the environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from nl_sql.agent.nodes.generate_sql import make_generate_sql_node
from nl_sql.agent.state import PipelineState
from nl_sql.llm.providers.base import GenerateRequest, GenerateResponse
from nl_sql.schema_index.indexer import SchemaQueryHit
from nl_sql.schema_index.retriever import ContextBundle


@dataclass(slots=True)
class _RecordingProvider:
    name: str = "fake"
    model: str = "fake-1"
    prompts: list[str] = field(default_factory=list)
    response: str = '{"sql": "SELECT 1", "rationale": "stub", "confidence": 0.9, "tables_used": []}'

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        self.prompts.append(req.prompt)
        return GenerateResponse(text=self.response, model=self.model)


def _stub_context() -> ContextBundle:
    hit = SchemaQueryHit(
        chunk_id="customers-overview",
        table_name="customers",
        db_id="demo",
        text="Table customers(id INTEGER, name TEXT)",
        distance=0.1,
        metadata={
            "table_name": "customers",
            "columns": "id,name",
            "primary_key": "id",
            "samples": "[{'id': 1, 'name': 'Alice'}]",
        },
    )
    return ContextBundle(
        db_id="demo",
        question="How many customers?",
        schema_hits=[hit],
        fk_neighbours=[],
        fewshots=[],
    )


def _state(question: str = "How many customers?") -> PipelineState:
    return {
        "question": question,
        "dialect": "sqlite",
        "context": _stub_context(),
        "plan": "",
        "trace": [],
    }


def _run_with_flags(use_m_schema: bool, use_dac_prompt: bool) -> str:
    provider = _RecordingProvider()
    node = make_generate_sql_node(
        provider, use_m_schema=use_m_schema, use_dac_prompt=use_dac_prompt
    )
    node(_state())
    return provider.prompts[0]


def test_default_uses_plain_template_and_default_schema_render() -> None:
    prompt = _run_with_flags(use_m_schema=False, use_dac_prompt=False)
    # Default `generate_sql.txt` is plain — DAC variant injects a Decompose
    # / sub-question instruction. Verify default does not have it.
    assert "Decompose" not in prompt
    assert "sub-question" not in prompt.lower()


def test_use_dac_prompt_switches_template() -> None:
    prompt = _run_with_flags(use_m_schema=False, use_dac_prompt=True)
    # `generate_sql_dac.txt` instructs the model to decompose multi-clause
    # questions before composing SQL — at least one of these keywords must
    # be present in the DAC variant but absent in the default.
    assert "Decompose" in prompt or "sub-question" in prompt.lower(), (
        f"Expected DAC prompt markers in selected template, got: {prompt[:400]}"
    )


def test_use_m_schema_changes_schema_rendering() -> None:
    default_prompt = _run_with_flags(use_m_schema=False, use_dac_prompt=False)
    mschema_prompt = _run_with_flags(use_m_schema=True, use_dac_prompt=False)
    # M-Schema renderer emits a `# Columns` / `# Foreign keys` block; the
    # default verbose renderer dumps raw `hit.text`. We only need to assert
    # the rendered schema portion of the prompt differs between flags, since
    # the prompt template / question / fewshot are identical.
    assert default_prompt != mschema_prompt, (
        "use_m_schema=True must change the rendered schema block in the prompt"
    )


@pytest.mark.parametrize(
    ("use_m_schema", "use_dac_prompt"),
    [(True, True), (True, False), (False, True), (False, False)],
)
def test_flags_do_not_leak_across_node_factory_calls(
    use_m_schema: bool,
    use_dac_prompt: bool,
) -> None:
    """Regression guard: each `make_generate_sql_node` call captures its own
    flags; flipping flags on a later call must not retroactively affect a
    previously-built node (catches accidental shared mutable default).
    """
    provider_a = _RecordingProvider()
    node_a = make_generate_sql_node(
        provider_a, use_m_schema=use_m_schema, use_dac_prompt=use_dac_prompt
    )
    provider_b = _RecordingProvider()
    _ = make_generate_sql_node(
        provider_b, use_m_schema=not use_m_schema, use_dac_prompt=not use_dac_prompt
    )
    node_a(_state())
    prompt = provider_a.prompts[0]
    expected_dac = "Decompose" in prompt or "sub-question" in prompt.lower()
    assert expected_dac is use_dac_prompt
