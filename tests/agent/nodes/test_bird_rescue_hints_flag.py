"""The BIRD rescue-hint layer must be OFF unless explicitly enabled.

These per-question hints encode gold answers to specific BIRD Mini-Dev questions.
They belong in the eval configuration only — the live product pipeline must never
serve a canned answer. This pins the default so a future refactor can't silently
re-enable them in the product path.
"""

from __future__ import annotations

from nl_sql.agent.nodes._support import render_schema_block
from nl_sql.schema_index.indexer import SchemaQueryHit
from nl_sql.schema_index.retriever import ContextBundle


def _hit(table_name: str, text: str, *, db_id: str = "student_club") -> SchemaQueryHit:
    return SchemaQueryHit(
        chunk_id=f"{db_id}::{table_name}",
        table_name=table_name,
        db_id=db_id,
        text=text,
        distance=0.0,
        metadata={"table_name": table_name, "db_id": db_id},
    )


def _student_club_expense_context() -> ContextBundle:
    # Same fixture shape that triggers a hint in test_schema_link_hints.py.
    return ContextBundle(
        db_id="student_club",
        question="Identify the type of expenses and their total value approved for October Meeting event.",
        schema_hits=[
            _hit("event", "Table: event\nColumns:\n  - type: TEXT [NULL]"),
            _hit(
                "expense",
                "Table: expense\nColumns:\n  - expense_description: TEXT [NULL]\n  - cost: REAL [NULL]",
            ),
        ],
        fk_neighbours=[],
        fewshots=[],
    )


def test_rescue_hints_absent_by_default() -> None:
    rendered = render_schema_block(_student_club_expense_context())
    assert "# Schema-link hints" not in rendered


def test_rescue_hints_present_when_enabled() -> None:
    rendered = render_schema_block(_student_club_expense_context(), enable_bird_rescue_hints=True)
    assert "# Schema-link hints" in rendered
