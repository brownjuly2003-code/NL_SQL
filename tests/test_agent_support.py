"""Unit tests for `nl_sql.agent.nodes._support`.

Covers JSON parsing edge cases — markdown fences, single-quote artefacts,
free-form recovery — plus schema/fewshot block rendering. Keeping the
tolerance behaviour pinned here means a model regression that emits weird
JSON shows up as a parsing-test failure, not as a downstream graph crash.
"""

from __future__ import annotations

from nl_sql.agent.nodes._support import (
    parse_generate_sql_output,
    render_fewshot_block,
    render_schema_block,
)
from nl_sql.schema_index.indexer import FewShotHit, SchemaQueryHit
from nl_sql.schema_index.retriever import ContextBundle


def test_parse_clean_json() -> None:
    text = """{
        "sql": "SELECT 1",
        "rationale": "test",
        "tables_used": ["t1"],
        "confidence": 0.9
    }"""
    out = parse_generate_sql_output(text)
    assert out.sql == "SELECT 1"
    assert out.rationale == "test"
    assert out.tables_used == ("t1",)
    assert out.confidence == 0.9


def test_parse_strips_markdown_fence() -> None:
    text = '```json\n{"sql": "SELECT 1", "confidence": 0.5}\n```'
    out = parse_generate_sql_output(text)
    assert out.sql == "SELECT 1"
    assert out.confidence == 0.5


def test_parse_strips_trailing_semicolon() -> None:
    text = '{"sql": "SELECT 1;", "confidence": 1}'
    out = parse_generate_sql_output(text)
    assert out.sql == "SELECT 1"


def test_parse_clamps_confidence_to_unit() -> None:
    high = parse_generate_sql_output('{"sql": "SELECT 1", "confidence": 1.7}')
    low = parse_generate_sql_output('{"sql": "SELECT 1", "confidence": -0.3}')
    assert high.confidence == 1.0
    assert low.confidence == 0.0


def test_parse_falls_back_when_json_broken() -> None:
    text = "Sure, here's the SQL: SELECT count(*) FROM customers;"
    out = parse_generate_sql_output(text)
    assert out.sql.upper().startswith("SELECT")
    assert out.confidence == 0.0
    assert "raw" not in out.sql.lower()


def test_parse_empty_response_yields_empty_sql_zero_confidence() -> None:
    out = parse_generate_sql_output("")
    assert out.sql == ""
    assert out.confidence == 0.0


def test_parse_handles_extra_prose_around_json() -> None:
    text = 'Here is the answer:\n{"sql": "SELECT 1", "confidence": 0.42}\nThanks!'
    out = parse_generate_sql_output(text)
    assert out.sql == "SELECT 1"
    assert out.confidence == 0.42


def test_render_schema_block_handles_empty_bundle() -> None:
    assert render_schema_block(None) == "(no schema context)"
    bundle = ContextBundle(db_id="d", question="q", schema_hits=[], fk_neighbours=[], fewshots=[])
    assert render_schema_block(bundle) == "(no tables matched)"


def test_render_schema_block_orders_seeds_then_neighbours() -> None:
    bundle = ContextBundle(
        db_id="d",
        question="q",
        schema_hits=[
            _hit("Album", "Album block"),
            _hit("Artist", "Artist block"),
        ],
        fk_neighbours=[_hit("Track", "Track block")],
        fewshots=[],
    )
    text = render_schema_block(bundle)
    assert text.index("Album block") < text.index("Artist block") < text.index("Track block")
    assert "# FK-related tables" in text


def test_render_fewshot_block_empty() -> None:
    assert render_fewshot_block(None) == "(none)"


def test_render_fewshot_block_includes_qsql() -> None:
    bundle = ContextBundle(
        db_id="d",
        question="q",
        schema_hits=[],
        fk_neighbours=[],
        fewshots=[
            FewShotHit(
                example_id="e1",
                db_id="d",
                question="how many albums",
                sql="SELECT COUNT(*) FROM Album",
                distance=0.2,
                metadata={},
            )
        ],
    )
    text = render_fewshot_block(bundle)
    assert "Q: how many albums" in text
    assert "SQL: SELECT COUNT(*) FROM Album" in text


def _hit(table: str, body: str) -> SchemaQueryHit:
    return SchemaQueryHit(
        chunk_id=f"d::{table}",
        table_name=table,
        db_id="d",
        text=body,
        distance=0.1,
        metadata={"db_id": "d", "table_name": table},
    )
