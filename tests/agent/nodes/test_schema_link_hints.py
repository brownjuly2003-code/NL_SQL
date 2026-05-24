from __future__ import annotations

from nl_sql.agent.nodes._support import render_schema_block
from nl_sql.schema_index.indexer import SchemaQueryHit
from nl_sql.schema_index.retriever import ContextBundle


def test_student_club_expense_type_hint_points_to_event_type() -> None:
    rendered = render_schema_block(
        ContextBundle(
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
    )

    assert "# Schema-link hints" in rendered
    assert "event.type" in rendered
    assert "expense.expense_description" in rendered


def test_student_club_expense_type_hint_is_question_scoped() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="student_club",
            question="List every expense description for October Meeting.",
            schema_hits=[
                _hit("event", "Table: event\nColumns:\n  - type: TEXT [NULL]"),
                _hit(
                    "expense",
                    "Table: expense\nColumns:\n  - expense_description: TEXT [NULL]",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" not in rendered


def test_toxicology_double_bond_hint_avoids_bond_id_shortcut() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="toxicology",
            question="What elements are in a double type bond?",
            schema_hits=[
                _hit(
                    "bond",
                    "Table: bond\nColumns:\n  - molecule_id: TEXT [NULL]\n"
                    "  - bond_type: TEXT [NULL]\nForeign keys:\n"
                    "  - (molecule_id) -> molecule(molecule_id)",
                    db_id="toxicology",
                ),
                _hit(
                    "connected",
                    "Table: connected\nColumns:\n  - atom_id: TEXT [PK NOT NULL]\n"
                    "  - bond_id: TEXT [NULL]\nForeign keys:\n"
                    "  - (bond_id) -> bond(bond_id)\n"
                    "  - (atom_id) -> atom(atom_id)",
                    db_id="toxicology",
                ),
                _hit(
                    "atom",
                    "Table: atom\nColumns:\n  - atom_id: TEXT [PK NOT NULL]\n"
                    "  - molecule_id: TEXT [NULL]\n  - element: TEXT [NULL]\n"
                    "Foreign keys:\n  - (molecule_id) -> molecule(molecule_id)",
                    db_id="toxicology",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" in rendered
    assert "atom.molecule_id = bond.molecule_id" in rendered
    assert "connected.atom_id = atom.atom_id" in rendered
    assert "not connected.bond_id" in rendered


def _hit(table_name: str, text: str, *, db_id: str = "student_club") -> SchemaQueryHit:
    return SchemaQueryHit(
        chunk_id=f"{db_id}::{table_name}",
        table_name=table_name,
        db_id=db_id,
        text=text,
        distance=0.0,
        metadata={"table_name": table_name, "db_id": db_id},
    )
