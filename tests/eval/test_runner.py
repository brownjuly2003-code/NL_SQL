"""Smoke tests for `eval.runner.run_config_a` + `run_config_c` with fake LLMs.

We script the LLM to return three responses:
- question 1: correct SQL → match=True
- question 2: invalid SQL (DELETE) → caught by guard, match=False
- question 3: wrong SQL (different aggregate) → executes but mismatch

That covers the three EA outcomes we report on.
"""

from __future__ import annotations

import gc
import hashlib
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import chromadb
import pytest

from nl_sql.db.connection import DatabaseSpec, sqlite_url_readonly
from nl_sql.db.registry import DatabaseRegistry
from nl_sql.eval.dataset import BirdExample
from nl_sql.eval.report import write_html_report, write_json_report
from nl_sql.eval.runner import (
    Configuration,
    run_config_a,
    run_config_b,
    run_config_c,
    run_config_d,
    run_config_e,
)
from nl_sql.execution.errors import ExecutionErrorKind
from nl_sql.llm.providers.base import (
    EmbedRequest,
    EmbedResponse,
    GenerateRequest,
    GenerateResponse,
)
from nl_sql.schema_index.chunker import to_chunks
from nl_sql.schema_index.indexer import SchemaIndex
from nl_sql.schema_index.introspector import introspect


class ScriptedLLM:
    name = "scripted"
    model = "scripted-1"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        self.call_count += 1
        return GenerateResponse(
            text=self._responses.pop(0),
            model=self.model,
            input_tokens=10,
            output_tokens=20,
        )


@pytest.fixture
def chinook_registry(tmp_path: Path) -> DatabaseRegistry:
    db_path = tmp_path / "chinook.sqlite"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE Artist (ArtistId INTEGER PRIMARY KEY, Name TEXT NOT NULL);
        CREATE TABLE Album (
            AlbumId INTEGER PRIMARY KEY,
            Title TEXT NOT NULL,
            ArtistId INTEGER NOT NULL,
            FOREIGN KEY (ArtistId) REFERENCES Artist(ArtistId)
        );
        INSERT INTO Artist VALUES (1, 'AC/DC'), (2, 'Aerosmith');
        INSERT INTO Album VALUES (10, 'Back in Black', 1), (11, 'Highway to Hell', 1), (12, 'Pump', 2);
        """
    )
    raw.commit()
    raw.close()

    spec = DatabaseSpec(id="bird_chinook", dialect="sqlite", url=sqlite_url_readonly(db_path))
    registry = DatabaseRegistry()
    registry.register(spec)
    return registry


def _example(qid: int, q: str, sql: str, difficulty: str = "simple") -> BirdExample:
    return BirdExample(
        question_id=qid,
        db_id="chinook",
        question=q,
        evidence="",
        sql=sql,
        difficulty=difficulty,  # type: ignore[arg-type]
    )


def test_run_config_a_correct_match(chinook_registry: DatabaseRegistry) -> None:
    sql_response = json.dumps(
        {
            "sql": "SELECT COUNT(*) FROM Album",
            "tables_used": ["Album"],
            "confidence": 0.9,
        }
    )
    llm = ScriptedLLM([sql_response])
    examples = [_example(1, "how many albums?", "SELECT COUNT(*) FROM Album")]
    run = run_config_a(examples, sql_provider=llm, registry=chinook_registry)

    assert run.configuration == Configuration.A_FULL_SCHEMA
    assert run.overall.n == 1
    assert run.overall.ea == 1.0
    assert run.records[0].match
    assert run.records[0].schema_recall is True
    assert run.records[0].error_kind is None
    assert run.records[0].input_tokens == 10
    assert run.records[0].output_tokens == 20


def test_run_config_a_invalid_sql_counts_as_miss(
    chinook_registry: DatabaseRegistry,
) -> None:
    bad = json.dumps({"sql": "DELETE FROM Album", "confidence": 0.1})
    llm = ScriptedLLM([bad])
    examples = [_example(2, "danger", "SELECT COUNT(*) FROM Album")]
    run = run_config_a(examples, sql_provider=llm, registry=chinook_registry)

    rec = run.records[0]
    assert rec.match is False
    assert rec.error_kind == ExecutionErrorKind.INVALID_SQL.value
    assert run.overall.validity_rate == 0.0


def test_run_config_a_wrong_value_counts_as_miss(
    chinook_registry: DatabaseRegistry,
) -> None:
    wrong = json.dumps(
        {"sql": "SELECT COUNT(*) FROM Artist", "tables_used": ["Artist"], "confidence": 0.5}
    )
    llm = ScriptedLLM([wrong])
    examples = [_example(3, "albums?", "SELECT COUNT(*) FROM Album")]
    run = run_config_a(examples, sql_provider=llm, registry=chinook_registry)

    rec = run.records[0]
    assert rec.match is False
    assert rec.error_kind is None  # SQL ran fine, just wrong answer
    assert rec.gold_row_count == 1
    assert rec.pred_row_count == 1


def test_run_config_a_per_difficulty_slices(chinook_registry: DatabaseRegistry) -> None:
    correct = json.dumps({"sql": "SELECT COUNT(*) FROM Album"})
    wrong = json.dumps({"sql": "SELECT COUNT(*) FROM Artist"})
    llm = ScriptedLLM([correct, wrong, correct])
    examples = [
        _example(1, "q1", "SELECT COUNT(*) FROM Album", "simple"),
        _example(2, "q2", "SELECT COUNT(*) FROM Album", "moderate"),
        _example(3, "q3", "SELECT COUNT(*) FROM Album", "challenging"),
    ]
    run = run_config_a(examples, sql_provider=llm, registry=chinook_registry)

    assert run.per_difficulty["simple"].ea == 1.0
    assert run.per_difficulty["moderate"].ea == 0.0
    assert run.per_difficulty["challenging"].ea == 1.0
    assert run.overall.ea == pytest.approx(2 / 3)


def test_progress_callback_invoked(chinook_registry: DatabaseRegistry) -> None:
    correct = json.dumps({"sql": "SELECT COUNT(*) FROM Album"})
    llm = ScriptedLLM([correct, correct])
    examples = [
        _example(1, "q1", "SELECT COUNT(*) FROM Album"),
        _example(2, "q2", "SELECT COUNT(*) FROM Album"),
    ]
    seen: list[tuple[int, int]] = []
    run_config_a(
        examples,
        sql_provider=llm,
        registry=chinook_registry,
        progress=lambda i, total, _r: seen.append((i, total)),
    )
    assert seen == [(1, 2), (2, 2)]


def test_other_configs_not_implemented_yet() -> None:
    # run_config_c and run_config_e now live — only B/D remain stubbed.
    for fn in (run_config_b, run_config_d):
        with pytest.raises(NotImplementedError):
            fn()


# ---------------------------------------------------------------------------
# Configuration C — dense retrieval, no fewshot, no repair.
# ---------------------------------------------------------------------------


class FakeEmbedder:
    """Deterministic byte-hash embeddings — no network, stable across runs."""

    def embed(self, req: EmbedRequest) -> EmbedResponse:
        return EmbedResponse(
            vectors=[
                [b / 255.0 for b in hashlib.sha1(t.encode("utf-8")).digest()[:8]]
                for t in req.texts
            ],
            model="fake",
        )


@pytest.fixture
def chinook_with_index(
    tmp_path: Path, chinook_registry: DatabaseRegistry
) -> Iterator[tuple[DatabaseRegistry, SchemaIndex]]:
    spec = chinook_registry.get("bird_chinook")
    intro_engine = spec.make_engine()
    try:
        client = chromadb.PersistentClient(path=str(tmp_path / "chroma_c"))
        index = SchemaIndex(
            persist_dir=tmp_path / "chroma_c", embedder=FakeEmbedder(), client=client
        )
        index.index_schema(
            to_chunks(
                introspect(intro_engine, sample_size=2),
                db_id="bird_chinook",
            )
        )
        yield chinook_registry, index
    finally:
        intro_engine.dispose()
        gc.collect()


def test_run_config_c_correct_match(
    chinook_with_index: tuple[DatabaseRegistry, SchemaIndex],
) -> None:
    registry, index = chinook_with_index
    sql_response = json.dumps(
        {
            "sql": "SELECT COUNT(*) FROM Album",
            "tables_used": ["Album"],
            "confidence": 0.9,
        }
    )
    sql_llm = ScriptedLLM([sql_response])
    explain_llm = ScriptedLLM(["3 albums."])
    examples = [_example(1, "how many albums?", "SELECT COUNT(*) FROM Album")]
    run = run_config_c(
        examples,
        sql_provider=sql_llm,
        explain_provider=explain_llm,
        schema_index=index,
        registry=registry,
        schema_top_k=2,
        fk_hops=0,
    )

    assert run.configuration == Configuration.C_DENSE
    assert run.overall.n == 1
    assert run.overall.ea == 1.0
    rec = run.records[0]
    assert rec.match is True
    assert rec.error_kind is None
    assert "Album" in rec.retrieved_tables  # context_builder populated trace
    assert rec.input_tokens > 0  # tokens came from generate_sql trace
    assert rec.output_tokens > 0


def test_run_config_c_no_repair_on_invalid(
    chinook_with_index: tuple[DatabaseRegistry, SchemaIndex],
) -> None:
    """Config C disables repair → first invalid SQL is the final SQL."""
    registry, index = chinook_with_index
    bad_sql = json.dumps({"sql": "DELETE FROM Album", "confidence": 0.1})
    sql_llm = ScriptedLLM([bad_sql])
    explain_llm = ScriptedLLM(["error caption"])
    examples = [_example(2, "danger", "SELECT COUNT(*) FROM Album")]
    run = run_config_c(
        examples,
        sql_provider=sql_llm,
        explain_provider=explain_llm,
        schema_index=index,
        registry=registry,
        schema_top_k=2,
        fk_hops=0,
    )

    rec = run.records[0]
    assert rec.match is False
    assert rec.error_kind == ExecutionErrorKind.INVALID_SQL.value
    assert rec.repair_attempted is False
    assert sql_llm.call_count == 1  # exactly one generate, no repair pass


# ---------------------------------------------------------------------------
# Configuration E — config C + repair_once.
# ---------------------------------------------------------------------------


def test_run_config_e_repair_recovers_invalid_first_pass(
    chinook_with_index: tuple[DatabaseRegistry, SchemaIndex],
) -> None:
    """Config E: first generate is invalid, repair fixes it, EA = True but
    first_pass_match must be False to isolate the repair contribution."""
    registry, index = chinook_with_index
    bad = json.dumps({"sql": "DELETE FROM Album", "confidence": 0.1})
    good = json.dumps(
        {"sql": "SELECT COUNT(*) FROM Album", "tables_used": ["Album"], "confidence": 0.85}
    )
    sql_llm = ScriptedLLM([bad, good])
    explain_llm = ScriptedLLM(["captioned"])
    examples = [_example(1, "albums?", "SELECT COUNT(*) FROM Album")]
    run = run_config_e(
        examples,
        sql_provider=sql_llm,
        explain_provider=explain_llm,
        schema_index=index,
        registry=registry,
        schema_top_k=2,
        fk_hops=0,
    )

    assert run.configuration == Configuration.E_FINAL
    rec = run.records[0]
    assert rec.match is True            # final EA = True (repair fixed it)
    assert rec.first_pass_match is False  # without repair, EA would be False
    assert rec.repair_attempted is True
    assert sql_llm.call_count == 2      # exactly one repair pass
    # Per-config aggregates should reflect the split:
    assert run.overall.ea == 1.0
    assert run.overall.first_pass_ea == 0.0
    assert run.overall.repair_success_rate == 1.0


def test_run_config_e_no_repair_when_first_pass_succeeds(
    chinook_with_index: tuple[DatabaseRegistry, SchemaIndex],
) -> None:
    registry, index = chinook_with_index
    good = json.dumps({"sql": "SELECT COUNT(*) FROM Album", "confidence": 0.9})
    sql_llm = ScriptedLLM([good])
    explain_llm = ScriptedLLM(["captioned"])
    examples = [_example(1, "albums?", "SELECT COUNT(*) FROM Album")]
    run = run_config_e(
        examples,
        sql_provider=sql_llm,
        explain_provider=explain_llm,
        schema_index=index,
        registry=registry,
        schema_top_k=2,
        fk_hops=0,
    )

    rec = run.records[0]
    assert rec.match is True
    assert rec.first_pass_match is True
    assert rec.repair_attempted is False  # repair never fired
    assert run.overall.repair_success_rate == 0.0  # no denominator


def test_run_config_c_progress_callback(
    chinook_with_index: tuple[DatabaseRegistry, SchemaIndex],
) -> None:
    registry, index = chinook_with_index
    correct = json.dumps({"sql": "SELECT COUNT(*) FROM Album"})
    sql_llm = ScriptedLLM([correct, correct])
    explain_llm = ScriptedLLM(["a", "b"])
    examples = [
        _example(1, "q1", "SELECT COUNT(*) FROM Album"),
        _example(2, "q2", "SELECT COUNT(*) FROM Album"),
    ]
    seen: list[tuple[int, int]] = []
    run_config_c(
        examples,
        sql_provider=sql_llm,
        explain_provider=explain_llm,
        schema_index=index,
        registry=registry,
        schema_top_k=2,
        fk_hops=0,
        progress=lambda i, total, _r: seen.append((i, total)),
    )
    assert seen == [(1, 2), (2, 2)]


def test_report_writers_round_trip(
    chinook_registry: DatabaseRegistry, tmp_path: Path
) -> None:
    correct = json.dumps({"sql": "SELECT COUNT(*) FROM Album"})
    llm = ScriptedLLM([correct])
    examples = [_example(1, "q1", "SELECT COUNT(*) FROM Album")]
    run = run_config_a(examples, sql_provider=llm, registry=chinook_registry)

    json_path = write_json_report(run, root=tmp_path)
    assert json_path.is_file()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["configuration"] == "A_full_schema"
    assert len(payload["records"]) == 1
    assert payload["records"][0]["match"] is True

    html_path = write_html_report([run], root=tmp_path)
    assert html_path.is_file()
    html = html_path.read_text(encoding="utf-8")
    assert "<table>" in html
    assert "A_full_schema" in html
