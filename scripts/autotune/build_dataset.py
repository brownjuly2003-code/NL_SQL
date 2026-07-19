"""Build the QLoRA train/val set for plan_autotune S1.

Renders each BIRD-train row through the SAME template the product pipeline
uses (`generate_sql.txt` via `load_prompt`), with the few-shot block rendered
exactly as config E renders it at `--fewshot-top-k 0` — the literal string
"(none)". The completion is the strict JSON contract the pipeline parses
(`parse_generate_sql_output`), not bare SQL: a student trained on bare SQL
would fail the product parser on every question.

Known train/inference gap (accepted for v1, see plan_autotune.md S6): here
`schema_block` is the raw DDL shipped in `bird_train.parquet`, while at eval
time config E renders retrieval-selected table cards with sampled values.
Closing that gap needs the 33GB BIRD train databases — gated.

Usage (from repo root):
    .venv/Scripts/python.exe scripts/autotune/build_dataset.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pandas as pd
import sqlglot
from sqlglot import expressions as sqlglot_exp

from nl_sql.agent.prompts import load_prompt

ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "data" / "bird_train.parquet"
OUT_DIR = ROOT / "data" / "autotune"
DEV_DB_DIR = ROOT / "data" / "bird_mini_dev" / "MINIDEV" / "dev_databases"

VAL_SIZE = 500
SEED = 0
MAX_EXAMPLE_CHARS = 32_000
DIALECT = "sqlite"
# The pipeline never scores rationale/confidence; fixed filler keeps the
# completion shaped like the contract without inventing per-row prose.
FIXED_CONFIDENCE = 0.9


def compose_question(question: str, evidence: str) -> str:
    """Mirror eval.runner's evidence embedding: `<question>\\n\\nHint: <evidence>`."""
    if not evidence or not evidence.strip():
        return question
    return f"{question}\n\nHint: {evidence}"


def extract_tables(sql: str) -> list[str]:
    """Distinct table names in order of appearance; [] when unparseable."""
    try:
        tree = sqlglot.parse_one(sql, dialect=DIALECT)
    except sqlglot.errors.ParseError:
        return []
    seen: list[str] = []
    for table in tree.find_all(sqlglot_exp.Table):
        name = table.name
        if name and name not in seen:
            seen.append(name)
    return seen


def build_example(row: Any) -> dict[str, str]:
    question = compose_question(str(row.question), str(row.evidence or ""))
    prompt = load_prompt(
        "generate_sql",
        dialect=DIALECT,
        schema_block=str(row.schema),
        fewshot_block="(none)",  # exact render of an empty few-shot context
        question=question,
    )
    sql = str(row.SQL).strip().rstrip(";").strip()
    tables = extract_tables(sql)
    completion = json.dumps(
        {
            "sql": sql,
            "rationale": f"Uses {', '.join(tables)}." if tables else "Direct query.",
            "tables_used": tables,
            "confidence": FIXED_CONFIDENCE,
        },
        ensure_ascii=False,
    )
    return {
        "db_id": str(row.db_id),
        "question": str(row.question),
        "prompt": prompt,
        "completion": completion,
    }


def sql_parses(sql: str) -> bool:
    try:
        sqlglot.parse_one(sql, dialect=DIALECT)
    except sqlglot.errors.ParseError:
        return False
    return True


def write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    df = pd.read_parquet(PARQUET)
    total = len(df)

    train_db_ids = {str(x) for x in df["db_id"].unique()}
    dev_db_ids = {p.name for p in DEV_DB_DIR.iterdir() if p.is_dir()}
    overlap = train_db_ids & dev_db_ids
    assert not overlap, f"train/dev db_id leakage: {sorted(overlap)}"
    print(f"leakage check: {len(train_db_ids)} train dbs vs {len(dev_db_ids)} dev dbs — disjoint")

    indices = list(range(total))
    random.Random(SEED).shuffle(indices)
    val_idx = set(indices[:VAL_SIZE])

    val_rows: list[dict[str, str]] = []
    train_rows: list[dict[str, str]] = []
    dropped_parse = 0
    dropped_dupe = 0
    dropped_long = 0
    seen_pairs: set[tuple[str, str]] = set()

    for pos, row in enumerate(df.itertuples(index=False)):
        example = build_example(row)
        if pos in val_idx:  # cut BEFORE filters, per plan
            val_rows.append(example)
            continue
        sql = str(row.SQL)
        if not sql_parses(sql):
            dropped_parse += 1
            continue
        pair = (str(row.question), sql)
        if pair in seen_pairs:
            dropped_dupe += 1
            continue
        seen_pairs.add(pair)
        if len(example["prompt"]) + len(example["completion"]) > MAX_EXAMPLE_CHARS:
            dropped_long += 1
            continue
        train_rows.append(example)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT_DIR / "train.jsonl", train_rows)
    write_jsonl(OUT_DIR / "val.jsonl", val_rows)

    print(f"total rows:      {total}")
    print(f"val (pre-filter): {len(val_rows)}")
    print(f"train kept:      {len(train_rows)}")
    print(f"dropped parse:   {dropped_parse}")
    print(f"dropped dupes:   {dropped_dupe}")
    print(f"dropped >chars:  {dropped_long}  (cap {MAX_EXAMPLE_CHARS})")

    sample = random.Random(SEED).sample(train_rows, 3)
    for i, ex in enumerate(sample):
        print(f"\n--- sample {i} [{ex['db_id']}] prompt head ---")
        print(ex["prompt"][:400])
        print(f"--- sample {i} completion ---")
        print(ex["completion"][:400])


if __name__ == "__main__":
    main()
