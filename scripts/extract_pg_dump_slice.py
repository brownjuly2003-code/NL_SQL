"""Cut one BIRD Mini-Dev database out of the official PostgreSQL dump.

BIRD ships `MINIDEV_postgresql/BIRD_dev.sql`: a ~955 MB `pg_dump` plain file
that loads **all eleven** Mini-Dev databases into a single `public` schema.
Restoring it whole would put 75 unrelated tables (Formula-1 circuits, card
games, hospital labs …) in front of the schema-retrieval step — a different,
much noisier task than the single-database one the product actually serves.

So we slice. Table names are globally unique across the eleven databases
(verified against `dev_tables.json`), which makes a by-table-name slice
unambiguous.

Why not `scripts/load_postgres.py` (SQLite → pandas → Postgres)? Because BIRD's
own Postgres gold SQL is written against **this** dump's schema: identifiers are
folded to lower case (`displayname`, `posthistory`) and dates are real
`timestamptz`, whereas a pandas load reproduces SQLite's CamelCase and text
dates. Gold like `SELECT DisplayName FROM users` resolves to `displayname` in
Postgres and would fail against a pandas-built table. Loading the official dump
is what makes the Postgres eval an apples-to-apples BIRD run rather than a
lookalike. `load_postgres.py` remains the right tool for Chinook and for ad-hoc
SQLite slices where no Postgres gold exists.

Usage:
    # what would be extracted (no output file written)
    python scripts/extract_pg_dump_slice.py --db codebase_community --list

    # write the slice
    python scripts/extract_pg_dump_slice.py --db codebase_community \
        --out .tmp/codebase_community_pg.sql
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from nl_sql.paths import under_root

DEFAULT_DUMP = under_root("data/bird_mini_dev/MINIDEV_postgresql/BIRD_dev.sql")
DEFAULT_TABLES_JSON = under_root("data/bird_mini_dev/MINIDEV/dev_tables.json")

# pg_dump attaches a comment block to every object:
#     --
#     -- Name: badges badges_pkey; Type: CONSTRAINT; Schema: public; Owner: …
#     --
# and for data:
#     -- Data for Name: badges; Type: TABLE DATA; Schema: public; Owner: …
_NAME_PREFIX = "-- Name: "
_DATA_PREFIX = "-- Data for Name: "

# Object types whose `Name:` field starts with the table they belong to.
_TABLE_SCOPED = {
    "TABLE",
    "TABLE DATA",
    "CONSTRAINT",
    "FK CONSTRAINT",
    "INDEX",
    "DEFAULT",
    "TRIGGER",
}


@dataclass(frozen=True, slots=True)
class Section:
    """One pg_dump object: its `-- Name:` header plus the SQL that follows."""

    name: str
    type: str
    lines: list[str] = field(repr=False)

    @property
    def table(self) -> str:
        """Table this object belongs to, lower-cased. Empty when not table-scoped."""
        if self.type in _TABLE_SCOPED:
            return self.name.split()[0].lower()
        return ""


def bird_tables(db_id: str, tables_json: Path = DEFAULT_TABLES_JSON) -> set[str]:
    """Lower-cased table names of one BIRD database, read from dev_tables.json."""
    entries = json.loads(tables_json.read_text(encoding="utf-8"))
    for entry in entries:
        if entry["db_id"] == db_id:
            return {t.lower() for t in entry["table_names_original"]}
    known = sorted(e["db_id"] for e in entries)
    raise KeyError(f"unknown BIRD db_id {db_id!r}. Known: {known}")


def _parse_header(line: str) -> tuple[str, str] | None:
    """Return (name, type) from a pg_dump `-- Name:` comment, else None."""
    if line.startswith(_DATA_PREFIX):
        rest = line[len(_DATA_PREFIX) :]
    elif line.startswith(_NAME_PREFIX):
        rest = line[len(_NAME_PREFIX) :]
    else:
        return None
    name, _, tail = rest.partition("; Type: ")
    if not tail:
        return None
    obj_type, _, _ = tail.partition(";")
    return name.strip(), obj_type.strip()


def iter_sections(fh: TextIO) -> Iterator[Section]:
    """Stream the dump as objects. The leading SET-block is yielded as PREAMBLE.

    Data lines inside `COPY … FROM stdin;` are never scanned for headers — a
    StackExchange post body legitimately contains lines starting with `--`, and
    treating one as an object boundary would truncate the table mid-load.
    """
    current = Section(name="", type="PREAMBLE", lines=[])
    in_copy = False

    for line in fh:
        if in_copy:
            current.lines.append(line)
            if line.rstrip("\n") == r"\.":
                in_copy = False
            continue

        header = _parse_header(line)
        if header is not None:
            # The bare `--` line above the header already landed in the previous
            # section; harmless (pg_dump ignores stray comments), so leave it.
            yield current
            current = Section(name=header[0], type=header[1], lines=[line])
            continue

        current.lines.append(line)
        if line.startswith("COPY ") and line.rstrip("\n").endswith("FROM stdin;"):
            in_copy = True

    yield current


def extract(
    dump: Path,
    tables: set[str],
    out: TextIO | None,
) -> list[Section]:
    """Copy the preamble + every object owned by `tables` from `dump` to `out`."""
    kept: list[Section] = []
    with dump.open("r", encoding="utf-8", newline="") as fh:
        for section in iter_sections(fh):
            keep = section.type == "PREAMBLE" or section.table in tables
            if not keep:
                continue
            kept.append(section)
            if out is not None:
                out.writelines(section.lines)
    return kept


def _verify(kept: list[Section], tables: set[str]) -> list[str]:
    """Structural checks — a silently short slice is worse than a loud failure."""
    problems: list[str] = []
    created = {s.table for s in kept if s.type == "TABLE"}
    loaded = {s.table for s in kept if s.type == "TABLE DATA"}
    if created != tables:
        problems.append(f"CREATE TABLE missing for: {sorted(tables - created)}")
    if loaded != tables:
        problems.append(f"COPY data missing for: {sorted(tables - loaded)}")
    # An FK pointing outside the slice cannot restore — it would reference a
    # table we deliberately left behind.
    for section in kept:
        if section.type == "FK CONSTRAINT":
            body = "".join(section.lines)
            _, _, ref = body.partition("REFERENCES public.")
            target = ref.split("(")[0].strip().lower()
            if target and target not in tables:
                problems.append(f"FK {section.name!r} references {target!r}, outside the slice")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="codebase_community", help="BIRD db_id to extract")
    parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP, help="path to BIRD_dev.sql")
    parser.add_argument("--out", type=Path, default=None, help="output .sql (omit with --list)")
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="print the objects that would be extracted and exit",
    )
    args = parser.parse_args(argv)

    if not args.dump.is_file():
        print(f"[error] dump not found: {args.dump}", file=sys.stderr)
        return 2
    if not args.list_only and args.out is None:
        print("[error] pass --out PATH (or --list to preview)", file=sys.stderr)
        return 3

    tables = bird_tables(args.db)
    print(f"[info] {args.db}: {len(tables)} tables → {sorted(tables)}")

    if args.list_only:
        kept = extract(args.dump, tables, out=None)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="") as out_fh:
            kept = extract(args.dump, tables, out=out_fh)

    by_type: dict[str, list[str]] = {}
    for section in kept:
        if section.type == "PREAMBLE":
            continue
        by_type.setdefault(section.type, []).append(section.name)
    for obj_type in sorted(by_type):
        print(f"  {obj_type}: {', '.join(sorted(by_type[obj_type]))}")

    problems = _verify(kept, tables)
    if problems:
        for problem in problems:
            print(f"[error] {problem}", file=sys.stderr)
        return 4

    if args.out is not None:
        size_mb = args.out.stat().st_size / 1e6
        print(f"[ok] wrote {args.out} ({size_mb:.0f} MB)")
    else:
        print("[ok] slice is structurally complete (use --out to write it)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
