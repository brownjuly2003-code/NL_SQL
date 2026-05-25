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


def test_formula_1_lap_time_recorded_hint_includes_milliseconds_first() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="formula_1",
            question="What is the best lap time recorded? List the driver and race with such recorded lap time.",
            schema_hits=[
                _hit(
                    "lapTimes",
                    "Table: lapTimes\nColumns:\n"
                    "  - driverId: INTEGER [NOT NULL]\n"
                    "  - raceId: INTEGER [NOT NULL]\n"
                    "  - milliseconds: INTEGER [NULL]",
                    db_id="formula_1",
                ),
                _hit(
                    "drivers",
                    "Table: drivers\nColumns:\n"
                    "  - driverId: INTEGER [PK NOT NULL]\n"
                    "  - forename: TEXT [NULL]\n"
                    "  - surname: TEXT [NULL]",
                    db_id="formula_1",
                ),
                _hit(
                    "races",
                    "Table: races\nColumns:\n"
                    "  - raceId: INTEGER [PK NOT NULL]\n"
                    "  - name: TEXT [NULL]",
                    db_id="formula_1",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" in rendered
    assert "lapTimes.milliseconds" in rendered
    assert "ORDER BY lapTimes.milliseconds ASC LIMIT 1" in rendered


def test_formula_1_lap_time_recorded_hint_is_question_scoped() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="formula_1",
            question="What is the surname of the driver with the best lap time in race number 19 in the second qualifying period?",
            schema_hits=[
                _hit(
                    "lapTimes",
                    "Table: lapTimes\nColumns:\n  - milliseconds: INTEGER [NULL]",
                    db_id="formula_1",
                ),
                _hit(
                    "drivers",
                    "Table: drivers\nColumns:\n  - surname: TEXT [NULL]",
                    db_id="formula_1",
                ),
                _hit(
                    "races",
                    "Table: races\nColumns:\n  - name: TEXT [NULL]",
                    db_id="formula_1",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" not in rendered


def test_thrombosis_higher_than_normal_hint_joins_examination() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="thrombosis_prediction",
            question="How many patients with an Ig G higher than normal?",
            schema_hits=[
                _hit(
                    "Patient",
                    "Table: Patient\nColumns:\n  - ID: INTEGER [PK NOT NULL]\n  - SEX: TEXT [NULL]",
                    db_id="thrombosis_prediction",
                ),
                _hit(
                    "Laboratory",
                    "Table: Laboratory\nColumns:\n  - ID: INTEGER [NOT NULL]\n  - IGG: REAL [NULL]",
                    db_id="thrombosis_prediction",
                ),
                _hit(
                    "Examination",
                    "Table: Examination\nColumns:\n"
                    "  - ID: INTEGER [NOT NULL]\n"
                    "  - Symptoms: TEXT [NULL]",
                    db_id="thrombosis_prediction",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" in rendered
    assert "INNER JOIN Examination" in rendered
    assert "Do NOT query Laboratory alone" in rendered


def test_thrombosis_higher_than_normal_hint_is_question_scoped() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="thrombosis_prediction",
            question="Among the patients with a normal Ig G level, how many of them have symptoms?",
            schema_hits=[
                _hit(
                    "Patient",
                    "Table: Patient\nColumns:\n  - ID: INTEGER [PK NOT NULL]",
                    db_id="thrombosis_prediction",
                ),
                _hit(
                    "Laboratory",
                    "Table: Laboratory\nColumns:\n  - IGG: REAL [NULL]",
                    db_id="thrombosis_prediction",
                ),
                _hit(
                    "Examination",
                    "Table: Examination\nColumns:\n  - Symptoms: TEXT [NULL]",
                    db_id="thrombosis_prediction",
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


def test_thrombosis_anti_centromere_hint_points_to_laboratory() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="thrombosis_prediction",
            question=(
                "Among the patients who has a normal level of anti-centromere "
                "and a normal level of anti-SSB, how many of them are male?"
            ),
            schema_hits=[
                _hit(
                    "Patient",
                    "Table: Patient\nColumns:\n  - ID: INTEGER [PK NOT NULL]\n  - SEX: TEXT [NULL]",
                    db_id="thrombosis_prediction",
                ),
                _hit(
                    "Laboratory",
                    "Table: Laboratory\nColumns:\n"
                    "  - ID: INTEGER [NOT NULL]\n"
                    "  - CENTROMEA: TEXT [NULL]\n"
                    "  - SSB: TEXT [NULL]",
                    db_id="thrombosis_prediction",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" in rendered
    assert "Laboratory.CENTROMEA" in rendered
    assert "Laboratory.SSB" in rendered
    assert "IN ('negative', '0')" in rendered
    assert "no CENTROMEA or SSB columns" in rendered


def test_thrombosis_anti_centromere_hint_is_question_scoped() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="thrombosis_prediction",
            question="How many patients with an Ig G higher than normal?",
            schema_hits=[
                _hit(
                    "Patient",
                    "Table: Patient\nColumns:\n  - ID: INTEGER [PK NOT NULL]",
                    db_id="thrombosis_prediction",
                ),
                _hit(
                    "Laboratory",
                    "Table: Laboratory\nColumns:\n  - CENTROMEA: TEXT [NULL]",
                    db_id="thrombosis_prediction",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "Laboratory.CENTROMEA" not in rendered


def test_card_games_triggered_ability_hint_points_to_rulings_text() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="card_games",
            question="How many unknown power cards contain info about the triggered ability",
            schema_hits=[
                _hit(
                    "cards",
                    "Table: cards\nColumns:\n"
                    "  - id: INTEGER [PK NOT NULL]\n"
                    "  - uuid: TEXT [NOT NULL]\n"
                    "  - power: TEXT [NULL]\n"
                    "  - text: TEXT [NULL]",
                    db_id="card_games",
                ),
                _hit(
                    "rulings",
                    "Table: rulings\nColumns:\n"
                    "  - uuid: TEXT [NOT NULL]\n"
                    "  - text: TEXT [NULL]\n"
                    "  - date: TEXT [NULL]",
                    db_id="card_games",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" in rendered
    assert "INNER JOIN rulings ON cards.uuid = rulings.uuid" in rendered
    assert "rulings.text LIKE '%triggered ability%'" in rendered
    assert "NOT cards.text" in rendered
    assert "COUNT(DISTINCT cards.id)" in rendered


def test_card_games_triggered_ability_hint_is_question_scoped() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="card_games",
            question="How many cards have infinite power?",
            schema_hits=[
                _hit(
                    "cards",
                    "Table: cards\nColumns:\n  - power: TEXT [NULL]",
                    db_id="card_games",
                ),
                _hit(
                    "rulings",
                    "Table: rulings\nColumns:\n  - text: TEXT [NULL]",
                    db_id="card_games",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" not in rendered


def test_thrombosis_oldest_sjs_patient_hint_includes_birthday_as_third_column() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="thrombosis_prediction",
            question=(
                "The oldest SJS patient's medical laboratory work was completed "
                "on what date, and what age was the patient when they initially "
                "arrived at the hospital?"
            ),
            schema_hits=[
                _hit(
                    "Patient",
                    "Table: Patient\nColumns:\n"
                    "  - ID: INTEGER [PK NOT NULL]\n"
                    "  - Diagnosis: TEXT [NULL]\n"
                    "  - Birthday: TEXT [NULL]\n"
                    "  - `First Date`: TEXT [NULL]",
                    db_id="thrombosis_prediction",
                ),
                _hit(
                    "Laboratory",
                    "Table: Laboratory\nColumns:\n"
                    "  - ID: INTEGER [NOT NULL]\n"
                    "  - Date: TEXT [NULL]",
                    db_id="thrombosis_prediction",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" in rendered
    assert "T2.Birthday" in rendered
    assert "ORDER BY T2.Birthday ASC LIMIT 1" in rendered
    assert "projection-discipline rule above does NOT apply" in rendered


def test_thrombosis_oldest_sjs_patient_hint_is_question_scoped() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="thrombosis_prediction",
            question="How many SJS patients are female?",
            schema_hits=[
                _hit(
                    "Patient",
                    "Table: Patient\nColumns:\n  - ID: INTEGER [PK NOT NULL]",
                    db_id="thrombosis_prediction",
                ),
                _hit(
                    "Laboratory",
                    "Table: Laboratory\nColumns:\n  - ID: INTEGER [NOT NULL]",
                    db_id="thrombosis_prediction",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" not in rendered


def test_european_football_2_highest_buildup_hint_sorts_asc_and_joins_team() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="european_football_2",
            question=(
                "What are the speed in which attacks are put together of the top "
                "4 teams with the highest build Up Play Speed?"
            ),
            schema_hits=[
                _hit(
                    "Team_Attributes",
                    "Table: Team_Attributes\nColumns:\n"
                    "  - team_api_id: INTEGER [NULL]\n"
                    "  - buildUpPlaySpeed: INTEGER [NULL]",
                    db_id="european_football_2",
                ),
                _hit(
                    "Team",
                    "Table: Team\nColumns:\n  - team_api_id: INTEGER [NULL]",
                    db_id="european_football_2",
                ),
            ],
            fk_neighbours=[],
            fewshots=[],
        )
    )

    assert "# Schema-link hints" in rendered
    assert "ORDER BY t1.buildUpPlaySpeed ASC LIMIT 4" in rendered
    assert "INNER JOIN Team" in rendered
    assert "positional inversion" in rendered


def test_european_football_2_highest_buildup_hint_is_question_scoped() -> None:
    rendered = render_schema_block(
        ContextBundle(
            db_id="european_football_2",
            question="List all teams from Germany.",
            schema_hits=[
                _hit(
                    "Team_Attributes",
                    "Table: Team_Attributes\nColumns:\n  - team_api_id: INTEGER [NULL]",
                    db_id="european_football_2",
                ),
                _hit(
                    "Team",
                    "Table: Team\nColumns:\n  - team_api_id: INTEGER [NULL]",
                    db_id="european_football_2",
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
