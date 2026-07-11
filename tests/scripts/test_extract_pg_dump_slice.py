"""Slicing one BIRD database out of the 955 MB all-databases Postgres dump.

The dump loads all eleven Mini-Dev databases into one `public` schema, so the
slice is what makes a single-database Postgres eval possible. Two failure modes
would be silent and would corrupt the eval rather than crash it, so both are
pinned here:

1. A StackExchange post body legitimately contains lines starting with `--`
   (markdown rules, C-style comments in code answers). Treating one as an object
   boundary truncates `posts` mid-COPY: the load still succeeds, just with fewer
   rows, and every downstream number is quietly wrong.
2. A short slice (missing CREATE TABLE / COPY / an FK pointing at a table left
   behind) must fail loudly, not restore a half-database.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from scripts.extract_pg_dump_slice import (
    DEFAULT_TABLES_JSON,
    Section,
    _verify,
    bird_tables,
    extract,
    iter_sections,
)

# A miniature pg_dump: two tables, one we want (`posts`) and one we don't
# (`circuits`, from the formula_1 database). The `posts` COPY payload contains a
# line that starts with `--` and another that mimics an object header.
DUMP = """\
--
-- PostgreSQL database dump
--

SET statement_timeout = 0;
SET client_encoding = 'UTF8';

--
-- Name: posts; Type: TABLE; Schema: public; Owner: xiaolongli
--

CREATE TABLE public.posts (
    id bigint NOT NULL,
    body text
);


--
-- Name: circuits; Type: TABLE; Schema: public; Owner: xiaolongli
--

CREATE TABLE public.circuits (
    circuitid bigint NOT NULL
);


--
-- Data for Name: posts; Type: TABLE DATA; Schema: public; Owner: xiaolongli
--

COPY public.posts (id, body) FROM stdin;
1\tplain answer
2\t-- this line starts a SQL comment inside a post body
3\t-- Name: circuits; Type: TABLE; Schema: public; Owner: xiaolongli
4\tlast row
\\.


--
-- Data for Name: circuits; Type: TABLE DATA; Schema: public; Owner: xiaolongli
--

COPY public.circuits (circuitid) FROM stdin;
7\t
\\.


--
-- Name: posts idx_1_posts_pkey; Type: CONSTRAINT; Schema: public; Owner: xiaolongli
--

ALTER TABLE ONLY public.posts
    ADD CONSTRAINT idx_1_posts_pkey PRIMARY KEY (id);


--
-- Name: posts posts_owneruserid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: xiaolongli
--

ALTER TABLE ONLY public.posts
    ADD CONSTRAINT posts_owneruserid_fkey FOREIGN KEY (owneruserid) REFERENCES public.users(id);
"""


def _slice(tables: set[str]) -> tuple[str, list[Section]]:
    out = io.StringIO()
    kept = extract_from_text(DUMP, tables, out)
    return out.getvalue(), kept


def extract_from_text(text: str, tables: set[str], out: io.StringIO) -> list[Section]:
    """`extract` against an in-memory dump (it takes a Path; tests take a string)."""
    kept: list[Section] = []
    for section in iter_sections(io.StringIO(text)):
        if section.type == "PREAMBLE" or section.table in tables:
            kept.append(section)
            out.writelines(section.lines)
    return kept


def test_copy_payload_is_not_scanned_for_object_headers() -> None:
    """A `-- Name: …` line inside a post body must not end the COPY block."""
    sql, kept = _slice({"posts"})

    # All four data rows survive — the fake header in row 3 did not split the table.
    assert "1\tplain answer" in sql
    assert "4\tlast row" in sql
    assert sql.count("COPY public.posts") == 1

    data = [s for s in kept if s.type == "TABLE DATA"]
    assert len(data) == 1
    body = "".join(data[0].lines)
    rows = [ln for ln in body.splitlines() if ln[:1].isdigit()]
    assert len(rows) == 4  # not 2 — the fake header did not terminate the block
    assert "\\." in body  # COPY terminator survived inside the section


def test_foreign_database_objects_are_dropped() -> None:
    sql, _ = _slice({"posts"})

    assert "CREATE TABLE public.posts" in sql
    assert "CREATE TABLE public.circuits" not in sql
    assert "COPY public.circuits" not in sql
    # …but the circuits COPY payload must not leak in either.
    assert "\n7\t\n" not in sql


def test_preamble_is_always_kept() -> None:
    sql, _ = _slice({"posts"})

    assert "SET statement_timeout = 0;" in sql
    assert "SET client_encoding = 'UTF8';" in sql


def test_verify_rejects_a_slice_missing_a_table() -> None:
    _, kept = _slice({"posts", "users"})  # `users` is not in this dump at all

    problems = _verify(kept, {"posts", "users"})

    assert any("CREATE TABLE missing" in p and "users" in p for p in problems)
    assert any("COPY data missing" in p and "users" in p for p in problems)


def test_verify_rejects_an_fk_pointing_outside_the_slice() -> None:
    """posts.owneruserid → users(id); slicing posts alone leaves a dangling FK."""
    _, kept = _slice({"posts"})

    problems = _verify(kept, {"posts"})

    assert any("references 'users'" in p and "outside the slice" in p for p in problems)


def test_verify_passes_on_a_complete_slice() -> None:
    _, kept = _slice({"posts", "circuits"})
    # Drop the dangling FK so the slice is self-contained.
    kept = [s for s in kept if s.type != "FK CONSTRAINT"]

    assert _verify(kept, {"posts", "circuits"}) == []


def test_bird_tables_parses_a_tables_json(tmp_path: Path) -> None:
    tables_json = tmp_path / "dev_tables.json"
    tables_json.write_text(
        json.dumps(
            [
                {"db_id": "formula_1", "table_names_original": ["circuits", "drivers"]},
                {"db_id": "codebase_community", "table_names_original": ["posts", "postHistory"]},
            ]
        ),
        encoding="utf-8",
    )

    assert bird_tables("codebase_community", tables_json) == {"posts", "posthistory"}


def test_bird_tables_rejects_an_unknown_db(tmp_path: Path) -> None:
    tables_json = tmp_path / "dev_tables.json"
    tables_json.write_text(
        json.dumps([{"db_id": "formula_1", "table_names_original": ["circuits"]}]), encoding="utf-8"
    )

    with pytest.raises(KeyError, match="unknown BIRD db_id"):
        bird_tables("not_a_bird_database", tables_json)


@pytest.mark.skipif(
    not DEFAULT_TABLES_JSON.is_file(),
    reason="BIRD Mini-Dev not downloaded (scripts/download_data.py bird-mini-dev)",
)
def test_bird_tables_reads_the_real_dev_tables_json() -> None:
    tables = bird_tables("codebase_community")

    assert tables == {
        "badges",
        "comments",
        "posthistory",
        "postlinks",
        "posts",
        "tags",
        "users",
        "votes",
    }


def test_extract_reads_from_a_real_file(tmp_path: Path) -> None:
    """End-to-end on a Path, since `extract` opens the dump itself."""
    dump = tmp_path / "dump.sql"
    dump.write_text(DUMP, encoding="utf-8", newline="")
    out_path = tmp_path / "slice.sql"

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        kept = extract(dump, {"posts"}, fh)

    written = out_path.read_text(encoding="utf-8")
    assert "CREATE TABLE public.posts" in written
    assert "CREATE TABLE public.circuits" not in written
    assert "COPY public.circuits" not in written
    assert {s.type for s in kept} == {
        "PREAMBLE",
        "TABLE",
        "TABLE DATA",
        "CONSTRAINT",
        "FK CONSTRAINT",
    }


@pytest.mark.skipif(
    not DEFAULT_TABLES_JSON.is_file(),
    reason="BIRD Mini-Dev not downloaded (scripts/download_data.py bird-mini-dev)",
)
def test_dev_tables_json_table_names_are_globally_unique() -> None:
    """The slice keys on table name alone — that is only sound if names don't collide.

    If BIRD ever ships two databases sharing a table name, the slice would silently
    pull in the other database's rows. Pin the property that makes it safe.

    Skipped when the dataset isn't downloaded (CI): this asserts a property of the
    BIRD data, not of our code, so there is nothing to check without the data.
    """
    entries = json.loads(DEFAULT_TABLES_JSON.read_text(encoding="utf-8"))
    seen: dict[str, str] = {}
    collisions: list[str] = []
    for entry in entries:
        for table in entry["table_names_original"]:
            key = table.lower()
            if key in seen and seen[key] != entry["db_id"]:
                collisions.append(f"{key}: {seen[key]} vs {entry['db_id']}")
            seen[key] = entry["db_id"]

    assert collisions == []
