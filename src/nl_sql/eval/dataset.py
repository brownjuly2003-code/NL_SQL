"""BIRD Mini-Dev loader + deterministic dev sample.

Source layout (after `scripts/download_data.py bird-mini-dev`):

    data/bird_mini_dev/MINIDEV/
      mini_dev_sqlite.json       # 500 examples, schema documented below
      mini_dev_mysql.json        # 500 examples, MySQL dialect (same questions)
      mini_dev_postgresql.json   # 500 examples, PG dialect (same questions)
      dev_databases/<db>/<db>.sqlite

Each item:
    {
      "question_id": int,
      "db_id": str,
      "question": str,
      "evidence": str,           # BIRD calls this "external knowledge", a hint
      "SQL": str,                # gold SQL for the dialect
      "difficulty": "simple" | "moderate" | "challenging"
    }

Per docs/03_eval_methodology.md §5: this loader is *evaluation-only*. The
few-shot pool MUST come from a separate train split — never the dev file.
A leakage-check helper (`is_in_dev_split`) is exposed for tests that guard
the few-shot index.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import sqlglot
from sqlglot import expressions as exp

Difficulty = Literal["simple", "moderate", "challenging"]
Dialect = Literal["sqlite", "mysql", "postgresql"]

DEFAULT_BIRD_ROOT = Path("data") / "bird_mini_dev" / "MINIDEV"

_DIALECT_TO_FILE = {
    "sqlite": "mini_dev_sqlite.json",
    "mysql": "mini_dev_mysql.json",
    "postgresql": "mini_dev_postgresql.json",
}

# A tolerant table-name extractor used by `extract_gold_tables`. Matches
# `FROM <name>`, `JOIN <name>` (with optional schema prefix `db.`), and
# stops on whitespace or a comma. Aliases are dropped by design — gold tables
# are what we score, not aliases.
_TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(?:[A-Za-z_][\w]*\.)?([\"`']?)([A-Za-z_][\w]*)\1",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class BirdExample:
    """One BIRD Mini-Dev question + gold SQL + difficulty + db_id."""

    question_id: int
    db_id: str           # raw bird key, e.g. "debit_card_specializing"
    question: str
    evidence: str
    sql: str
    difficulty: Difficulty
    dialect: Dialect = "sqlite"

    @property
    def registry_db_id(self) -> str:
        """Registry id used by `nl_sql.db.registry` — `bird_<db_id>`."""
        return f"bird_{self.db_id}"


def load_bird_mini_dev(
    root: Path | str = DEFAULT_BIRD_ROOT,
    *,
    dialect: Dialect = "sqlite",
) -> list[BirdExample]:
    """Read the Mini-Dev json for one dialect, return all 500 examples."""
    path = Path(root) / _DIALECT_TO_FILE[dialect]
    if not path.is_file():
        raise FileNotFoundError(
            f"BIRD Mini-Dev file not found: {path}. "
            f"Run `python scripts/download_data.py bird-mini-dev` first."
        )
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return [_to_example(item, dialect=dialect) for item in raw]


def dev_split(
    examples: Sequence[BirdExample],
    *,
    n: int,
    seed: int = 0,
) -> list[BirdExample]:
    """Deterministic sample of `n` examples with stable-prefix property.

    Implementation: shuffle the pool once with `random.Random(seed)` and
    take the first `n`. This guarantees that for the same seed,
    `dev_split(..., n=k1)` is a prefix of `dev_split(..., n=k2)` whenever
    `k1 <= k2` — so growing the eval slice (50 → 100 → 200) re-uses every
    cached prompt from the smaller run instead of re-rolling.

    Result is sorted by question_id for reader stability (the underlying
    shuffle is unordered, but eval reports want stable IDs).
    """
    if n <= 0:
        return []
    pool = list(examples)
    if n >= len(pool):
        return sorted(pool, key=lambda e: e.question_id)
    rng = random.Random(seed)
    shuffled = pool[:]
    rng.shuffle(shuffled)
    chosen = shuffled[:n]
    return sorted(chosen, key=lambda e: e.question_id)


def extract_gold_tables(sql: str) -> list[str]:
    """Walk the SQL AST and collect every base-table reference.

    Used by Schema Recall@k. Captures tables referenced anywhere in the
    query — FROM, JOIN, correlated subqueries inside WHERE / SELECT,
    IN-list subqueries, set operations, etc. CTE names defined via
    ``WITH ... AS (...)`` are excluded because they shadow base tables
    in scope and would inflate recall against the schema_chunks index.

    Falls back to the FROM/JOIN regex if sqlglot can't parse the SQL —
    BIRD ships a small fraction of dialect-specific quirks that even
    the lenient parser may reject; better to under-count than crash.
    """
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except sqlglot.errors.ParseError:
        return _extract_via_regex(sql)
    if tree is None:
        return _extract_via_regex(sql)

    # CTE names live in a WITH block above the body — collect them so we
    # can drop matches that point at a CTE alias rather than a base table.
    cte_names: set[str] = {
        cte.alias_or_name.lower()
        for cte in tree.find_all(exp.CTE)
        if cte.alias_or_name
    }

    tables: list[str] = []
    seen: set[str] = set()
    for node in tree.find_all(exp.Table):
        # Walk up to detect tables that are themselves the alias side of
        # a CTE definition (the body of WITH x AS (...) — sqlglot models
        # the inner SELECT's tables here, which we still want; only skip
        # references whose .name matches a CTE alias).
        name = node.name
        if not name:
            continue
        key = name.lower()
        if key in cte_names:
            continue
        if key in seen:
            continue
        seen.add(key)
        tables.append(name)
    if not tables:
        return _extract_via_regex(sql)
    return tables


def _extract_via_regex(sql: str) -> list[str]:
    """Legacy regex-based fallback for the ~1% of SQLs sqlglot can't parse."""
    tables: list[str] = []
    seen: set[str] = set()
    for match in _TABLE_RE.finditer(sql):
        table = match.group(2)
        key = table.lower()
        if key in seen:
            continue
        seen.add(key)
        tables.append(table)
    return tables


def is_in_dev_split(question: str, dev_examples: Iterable[BirdExample]) -> bool:
    """Helper for the leakage-check CI test (`test_no_dev_in_fewshot`).

    Returns True iff `question` text exactly matches any dev example. Exact
    match is strict on purpose — paraphrases are NOT considered leakage,
    only verbatim copies (which is the actual risk when curating a few-shot
    pool from public sources).
    """
    needle = question.strip().lower()
    return any(ex.question.strip().lower() == needle for ex in dev_examples)


def _to_example(item: dict[str, Any], *, dialect: Dialect) -> BirdExample:
    difficulty = str(item.get("difficulty", "moderate"))
    if difficulty not in ("simple", "moderate", "challenging"):
        difficulty = "moderate"
    return BirdExample(
        question_id=int(item["question_id"]),
        db_id=str(item["db_id"]),
        question=str(item["question"]),
        evidence=str(item.get("evidence", "")),
        sql=str(item["SQL"]),
        difficulty=difficulty,  # type: ignore[arg-type]
        dialect=dialect,
    )
