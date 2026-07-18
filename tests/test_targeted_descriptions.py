"""Unit tests for targeted column descriptions (A8)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nl_sql.agent.nodes import context_builder as cb_module
from nl_sql.agent.nodes.context_builder import make_context_builder_node
from nl_sql.agent.nodes.generate_sql import make_generate_sql_node
from nl_sql.llm.providers.base import EmbedRequest, EmbedResponse, GenerateRequest, GenerateResponse
from nl_sql.schema_index.indexer import SchemaQueryHit
from nl_sql.schema_index.retriever import ContextBundle
from nl_sql.schema_index.targeted_descriptions import (
    render_column_notes,
    select_targeted_descriptions,
)


class KeywordEmbedder:
    """Deterministic embedder: vector = keyword-presence flags."""

    name = "fake-embed"
    embed_model = "fake-embed-model"
    keywords = ("charter", "school", "score")

    def __init__(self) -> None:
        self.requests: list[EmbedRequest] = []

    def embed(self, req: EmbedRequest) -> EmbedResponse:
        self.requests.append(req)
        vectors = [
            [1.0 if kw in text.lower() else 0.0 for kw in self.keywords] for text in req.texts
        ]
        return EmbedResponse(vectors=vectors, model=self.embed_model)


def _write_descriptions(db_dir: Path, table: str, rows: str) -> None:
    desc_dir = db_dir / "database_description"
    desc_dir.mkdir(exist_ok=True)
    header = "original_column_name,column_name,column_description,data_format,value_description\n"
    (desc_dir / f"{table}.csv").write_text(header + rows, encoding="utf-8")


def _db(tmp_path: Path) -> str:
    _write_descriptions(
        tmp_path,
        "satscores",
        "charter,,identifies a charter school,integer,\n"
        "AvgScrMath,,average math score,integer,\n"
        "enroll12,,enrollment of grade 12,integer,\n",
    )
    _write_descriptions(tmp_path, "frpm", "mealtype,,free meal category,text,\n")
    return str(tmp_path / "db.sqlite")


def test_select_ranks_by_similarity_and_filters_tables(tmp_path: Path) -> None:
    db_url = _db(tmp_path)
    lines = select_targeted_descriptions(
        KeywordEmbedder(),
        question="How many charter schools are there?",
        db_url=db_url,
        tables=["satscores"],
        top_k=2,
    )
    assert len(lines) == 2
    # The charter line matches two keywords — it must rank first.
    assert lines[0] == "satscores.charter: identifies a charter school"
    # frpm was not retrieved → its line never appears.
    assert not any(line.startswith("frpm.") for line in lines)


def test_select_empty_without_descriptions_or_tables(tmp_path: Path) -> None:
    embedder = KeywordEmbedder()
    no_desc = str(tmp_path / "chinook.sqlite")
    assert select_targeted_descriptions(embedder, question="q", db_url=no_desc, tables=["a"]) == []
    db_url = _db(tmp_path)
    assert select_targeted_descriptions(embedder, question="q", db_url=db_url, tables=[]) == []
    assert (
        select_targeted_descriptions(embedder, question="q", db_url=db_url, tables=["nosuch"]) == []
    )
    # No embed call is spent when there is nothing to rank.
    assert embedder.requests == []


def test_render_column_notes() -> None:
    assert render_column_notes([]) == ""
    block = render_column_notes(["t.a: x", "t.b: y"])
    assert block.startswith("Column notes")
    assert "- t.a: x" in block
    assert "- t.b: y" in block


# --- context_builder wiring ---


def _bundle() -> ContextBundle:
    hit = SchemaQueryHit(
        chunk_id="c1",
        table_name="satscores",
        db_id="california_schools",
        text="Table: satscores\n",
        distance=0.1,
        metadata={},
    )
    return ContextBundle(
        db_id="california_schools",
        question="q",
        schema_hits=[hit],
        fk_neighbours=[],
        fewshots=[],
    )


class FakeRegistry:
    def __init__(self, url: str) -> None:
        self._url = url

    def get(self, db_id: str) -> Any:
        class Spec:
            url = self._url

        return Spec()


def _run_node(monkeypatch: pytest.MonkeyPatch, *, registry: Any, embedder: Any) -> dict[str, Any]:
    monkeypatch.setattr(cb_module, "retrieve_context", lambda *a, **kw: _bundle())
    node = make_context_builder_node(
        object(),  # type: ignore[arg-type] — retrieve_context is patched out
        registry=registry,
        description_embedder=embedder,
    )
    return dict(node({"question": "How many charter schools?", "db_id": "california_schools"}))  # type: ignore[arg-type]


def test_node_column_notes_land_in_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_url = _db(tmp_path)
    out = _run_node(monkeypatch, registry=FakeRegistry(db_url), embedder=KeywordEmbedder())
    assert "satscores.charter" in out["column_notes"]
    assert out["trace"][-1]["column_notes"] == 3
    assert "targeted_descriptions" not in out["trace"][-1]


def test_node_soft_fails_on_embedder_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class BoomEmbedder(KeywordEmbedder):
        def embed(self, req: EmbedRequest) -> EmbedResponse:
            raise RuntimeError("boom")

    db_url = _db(tmp_path)
    out = _run_node(monkeypatch, registry=FakeRegistry(db_url), embedder=BoomEmbedder())
    assert out["column_notes"] == ""
    assert "targeted_descriptions failed" in str(out["trace"][-1]["targeted_descriptions"])


def test_node_off_no_embedder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = _run_node(monkeypatch, registry=FakeRegistry(_db(tmp_path)), embedder=None)
    assert out["column_notes"] == ""
    assert "column_notes" not in out["trace"][-1]


# --- generate_sql rendering ---


class CaptureProvider:
    name = "cap"
    model = "cap-model"

    def __init__(self) -> None:
        self.requests: list[GenerateRequest] = []

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        self.requests.append(req)
        return GenerateResponse(text='{"sql": "SELECT 1"}', model=self.model)


def _generate_prompt(column_notes: str) -> str:
    provider = CaptureProvider()
    node = make_generate_sql_node(provider)
    state: dict[str, Any] = {
        "question": "q",
        "dialect": "sqlite",
        "context": _bundle(),
        "column_notes": column_notes,
    }
    node(state)  # type: ignore[arg-type]
    return provider.requests[0].prompt


def test_generate_appends_notes_to_schema() -> None:
    block = render_column_notes(["satscores.charter: identifies a charter school"])
    prompt = _generate_prompt(block)
    assert "Column notes" in prompt
    assert "satscores.charter" in prompt


def test_generate_prompt_unchanged_when_off() -> None:
    assert "Column notes" not in _generate_prompt("")
    assert _generate_prompt("") == _generate_prompt("  ")
