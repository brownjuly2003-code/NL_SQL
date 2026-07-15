"""Value grounding lands in the generate_sql prompt when matches exist."""

from __future__ import annotations

from dataclasses import dataclass, field

from nl_sql.agent.nodes.generate_sql import make_generate_sql_node
from nl_sql.agent.state import PipelineState
from nl_sql.llm.providers.base import GenerateRequest, GenerateResponse
from nl_sql.schema_index.indexer import SchemaQueryHit
from nl_sql.schema_index.retriever import ContextBundle
from nl_sql.schema_index.value_retrieval import ValueMatch


@dataclass(slots=True)
class _RecordingProvider:
    name: str = "fake"
    model: str = "fake-1"
    prompts: list[str] = field(default_factory=list)
    response: str = '{"sql": "SELECT 1", "rationale": "stub", "confidence": 0.9, "tables_used": []}'

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        self.prompts.append(req.prompt)
        return GenerateResponse(text=self.response, model=self.model)


def _bundle(*, with_match: bool) -> ContextBundle:
    hit = SchemaQueryHit(
        chunk_id="comics-overview",
        table_name="comics",
        db_id="demo",
        text="Table comics(id INTEGER, publisher TEXT)",
        distance=0.1,
        metadata={
            "table_name": "comics",
            "columns": "id,publisher",
            "primary_key": "id",
            "samples": "[]",
        },
    )
    matches = (
        [ValueMatch(value="Marvel Comics", table="comics", column="publisher", score=1.0)]
        if with_match
        else []
    )
    return ContextBundle(
        db_id="demo",
        question="List titles from Marvel Comics",
        schema_hits=[hit],
        fk_neighbours=[],
        fewshots=[],
        value_matches=matches,
    )


def test_value_matches_injected_into_prompt() -> None:
    provider = _RecordingProvider()
    node = make_generate_sql_node(provider)
    state: PipelineState = {
        "question": "List titles from Marvel Comics",
        "dialect": "sqlite",
        "context": _bundle(with_match=True),
        "plan": "",
        "trace": [],
    }
    node(state)
    prompt = provider.prompts[0]
    assert "Value grounding" in prompt
    assert "Marvel Comics" in prompt
    assert "comics.publisher" in prompt


def test_no_value_block_when_matches_empty() -> None:
    provider = _RecordingProvider()
    node = make_generate_sql_node(provider)
    state: PipelineState = {
        "question": "List titles from Marvel Comics",
        "dialect": "sqlite",
        "context": _bundle(with_match=False),
        "plan": "",
        "trace": [],
    }
    node(state)
    assert "Value grounding" not in provider.prompts[0]
