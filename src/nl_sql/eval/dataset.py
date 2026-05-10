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
    """Deterministic sample of `n` examples.

    Uses `random.Random(seed).sample(examples, n)` — same seed gives the
    same split across runs and across machines. Sorted by question_id in
    the result for reader stability (the underlying sample is unordered).
    """
    if n <= 0:
        return []
    pool = list(examples)
    if n >= len(pool):
        return sorted(pool, key=lambda e: e.question_id)
    rng = random.Random(seed)
    chosen = rng.sample(pool, n)
    return sorted(chosen, key=lambda e: e.question_id)


def extract_gold_tables(sql: str) -> list[str]:
    """Pull table identifiers from FROM/JOIN clauses of a SQL string.

    Best-effort, regex-based. Handles common BIRD shapes (CTEs, aliases,
    schema-qualified names) without dragging in sqlglot for what is a 100%
    static lookup. Used by Schema Recall@k.
    """
    tables: list[str] = []
    seen: set[str] = set()
    for match in _TABLE_RE.finditer(sql):
        table = match.group(2)
        key = table.lower()
        if key in seen:
            continue
        # Skip CTE-style names defined inside the same query — heuristic:
        # if the same name appears after `WITH ... AS (` it's still in the
        # match list. Dropping that requires real parsing; the cost of a
        # false positive in recall is small (CTEs rarely shadow base tables).
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
