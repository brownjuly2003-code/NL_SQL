"""Live-Postgres proof that the pipeline connection is genuinely READ ONLY.

These tests are skipped unless ``NL_SQL_PG_TEST_DSN`` points at a reachable
Postgres (the CI job sets it to the ``postgres:16`` service). They exist because
the read-only guarantee cannot be proved by reasoning alone — an earlier
implementation *looked* read-only (`SET default_transaction_read_only = on`) but
ran that statement inside an already-open transaction, where it is a no-op. The
only honest proof is: connect through the real read-only engine and watch a
write get rejected by a live server.

The read-only defence under test is the engine's ``postgresql_readonly``
execution option, which is enforced by Postgres at the transaction level and so
holds even for a superuser DSN — it does not depend on the ``nl_sql_ro`` role.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Engine, create_engine, text

from nl_sql.db.connection import (
    DatabaseSpec,
    _normalise_pg_driver,
    connect,
    execute_readonly,
)

PG_DSN = os.environ.get("NL_SQL_PG_TEST_DSN", "")

pytestmark = pytest.mark.skipif(
    not PG_DSN,
    reason="set NL_SQL_PG_TEST_DSN to a live Postgres to run the read-only proof",
)

_TABLE = "nl_sql_ro_probe"


@pytest.fixture
def privileged_engine() -> Engine:
    """A normal read-WRITE engine used only to seed the probe table."""
    engine = create_engine(_normalise_pg_driver(PG_DSN), future=True)
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {_TABLE}"))
        conn.execute(text(f"CREATE TABLE {_TABLE} (id integer PRIMARY KEY, v text)"))
        conn.execute(text(f"INSERT INTO {_TABLE} (id, v) VALUES (1, 'seed')"))
    yield engine
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {_TABLE}"))
    engine.dispose()


@pytest.fixture
def readonly_engine(privileged_engine: Engine) -> Engine:
    """The engine the pipeline actually uses — must be read-only."""
    spec = DatabaseSpec(id="pg_probe", dialect="postgresql", url=PG_DSN)
    engine = connect(spec)
    yield engine
    engine.dispose()


def test_readonly_engine_can_select(readonly_engine: Engine) -> None:
    with readonly_engine.connect() as conn:
        row = conn.execute(text(f"SELECT v FROM {_TABLE} WHERE id = 1")).fetchone()
    assert row is not None
    assert row[0] == "seed"


@pytest.mark.parametrize(
    "write_sql",
    [
        f"INSERT INTO {_TABLE} (id, v) VALUES (2, 'hacked')",
        f"UPDATE {_TABLE} SET v = 'hacked' WHERE id = 1",
        f"DELETE FROM {_TABLE} WHERE id = 1",
        f"CREATE TABLE {_TABLE}_evil (id integer)",
        f"SELECT id INTO {_TABLE}_leak FROM {_TABLE}",
    ],
)
def test_readonly_engine_rejects_writes(readonly_engine: Engine, write_sql: str) -> None:
    """Every write shape must be refused by the live server, not just the guard."""
    with (
        pytest.raises(Exception, match=r"read.?only"),
        readonly_engine.connect() as conn,
    ):
        conn.execute(text(write_sql))


def test_write_did_not_persist(privileged_engine: Engine, readonly_engine: Engine) -> None:
    """After all the rejected writes, the seed row is untouched and alone."""
    for bad in [
        f"INSERT INTO {_TABLE} (id, v) VALUES (2, 'hacked')",
        f"UPDATE {_TABLE} SET v = 'hacked' WHERE id = 1",
    ]:
        with (
            pytest.raises(Exception, match=r"read.?only"),
            readonly_engine.connect() as conn,
        ):
            conn.execute(text(bad))
    with privileged_engine.connect() as conn:
        rows = conn.execute(text(f"SELECT id, v FROM {_TABLE} ORDER BY id")).fetchall()
    assert rows == [(1, "seed")]


def test_execute_readonly_runs_a_real_select(readonly_engine: Engine) -> None:
    """The production read path (execute_readonly) works against live Postgres."""
    with execute_readonly(readonly_engine, f"SELECT id, v FROM {_TABLE}") as result:
        assert result.columns == ["id", "v"]
        assert result.rows == [(1, "seed")]
        assert result.truncated is False
