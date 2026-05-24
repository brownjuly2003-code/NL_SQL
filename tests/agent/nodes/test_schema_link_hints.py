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


def test_formula_1_track_number_hint_points_to_driverstandings() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="formula_1",
            question="Which race was Alex Yoong in when he was in track number less than 20?",
            schema_hits=[
                _hit(
                    "driverStandings",
                    "Table: driverStandings\nColumns:\n"
                    "  - driverId: INTEGER [NOT NULL]\n"
                    "  - raceId: INTEGER [NOT NULL]\n"
                    "  - position: INTEGER [NULL]",
                    db_id="formula_1",
                ),
                _hit(
                    "results",
                    "Table: results\nColumns:\n"
                    "  - position: INTEGER [NULL]\n"
                    "  - positionOrder: INTEGER [NULL]",
                    db_id="formula_1",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" in rendered
    assert "driverStandings.position" in rendered
    assert "track number" in rendered


def test_formula_1_track_number_hint_is_question_scoped() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="formula_1",
            question="Which race did Lewis Hamilton finish first in?",
            schema_hits=[
                _hit(
                    "driverStandings",
                    "Table: driverStandings\nColumns:\n  - position: INTEGER [NULL]",
                    db_id="formula_1",
                ),
                _hit(
                    "results",
                    "Table: results\nColumns:\n  - position: INTEGER [NULL]",
                    db_id="formula_1",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" not in rendered


def test_debit_card_top_spending_hint_points_to_yearmonth_consumption() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="debit_card_specializing",
            question=(
                "Who is the top spending customer and how much is the average "
                "price per single item purchased by this customer? What "
                "currency was being used?"
            ),
            schema_hits=[
                _hit(
                    "yearmonth",
                    "Table: yearmonth\nColumns:\n"
                    "  - CustomerID: INTEGER [NOT NULL]\n"
                    "  - Consumption: REAL [NULL]",
                    db_id="debit_card_specializing",
                ),
                _hit(
                    "transactions_1k",
                    "Table: transactions_1k\nColumns:\n"
                    "  - CustomerID: INTEGER [NOT NULL]\n"
                    "  - Price: REAL [NULL]\n"
                    "  - Amount: INTEGER [NULL]",
                    db_id="debit_card_specializing",
                ),
                _hit(
                    "customers",
                    "Table: customers\nColumns:\n"
                    "  - CustomerID: INTEGER [PK NOT NULL]\n"
                    "  - Currency: TEXT [NULL]",
                    db_id="debit_card_specializing",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" in rendered
    assert "yearmonth.Consumption" in rendered
    assert "SUM(T2.Price / T2.Amount)" in rendered
    assert "NOT SUM(transactions_1k.Price)" in rendered


def test_debit_card_top_spending_hint_is_question_scoped() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="debit_card_specializing",
            question="Which year recorded the most consumption of gas paid in CZK?",
            schema_hits=[
                _hit(
                    "yearmonth",
                    "Table: yearmonth\nColumns:\n  - Consumption: REAL [NULL]",
                    db_id="debit_card_specializing",
                ),
                _hit(
                    "transactions_1k",
                    "Table: transactions_1k\nColumns:\n  - Price: REAL [NULL]",
                    db_id="debit_card_specializing",
                ),
                _hit(
                    "customers",
                    "Table: customers\nColumns:\n  - Currency: TEXT [NULL]",
                    db_id="debit_card_specializing",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" not in rendered


def _hit(table_name: str, text: str, *, db_id: str = "student_club") -> SchemaQueryHit:
    return SchemaQueryHit(
        chunk_id=f"{db_id}::{table_name}",
        table_name=table_name,
        db_id=db_id,
        text=text,
        distance=0.0,
        metadata={"table_name": table_name, "db_id": db_id},
    )
