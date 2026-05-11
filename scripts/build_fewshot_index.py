"""Build the `fewshot_qsql` Chroma collection from BIRD train.

Source: `data/bird_train.parquet`, downloaded from
``huggingface.co/datasets/xu3kev/BIRD-SQL-data-train`` (9 428 rows over
69 dbs, none of which overlap with BIRD Mini-Dev's 11 dev dbs — verified
by construction).

Usage::

    uv run python scripts/build_fewshot_index.py
    uv run python scripts/build_fewshot_index.py --limit 1000  # sanity slice
    uv run python scripts/build_fewshot_index.py --persist chroma_data/

The script embeds each question via Mistral `mistral-embed` and upserts
into the `fewshot_qsql` collection. Embeddings are cached, so re-running
is free after the first pass. The schema chunks live in the same Chroma
client but in a different collection, so this script is safe to run on
top of an existing index.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import chromadb
import pyarrow.parquet as pq

from nl_sql.config import get_settings
from nl_sql.eval.dataset import load_bird_mini_dev
from nl_sql.llm.cache import CachingEmbeddingProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.indexer import FewShotExample, SchemaIndex


def _load_train_examples(
    parquet_path: Path,
    *,
    limit: int | None = None,
) -> list[FewShotExample]:
    table = pq.read_table(parquet_path)
    df = table.to_pandas()
    if limit:
        df = df.head(limit)
    examples: list[FewShotExample] = []
    for idx, row in df.iterrows():
        examples.append(
            FewShotExample(
                example_id=f"bird_train_{idx}",
                db_id=str(row["db_id"]),
                question=str(row["question"]),
                sql=str(row["SQL"]),
                intent="",
            )
        )
    return examples


def _assert_no_dev_leakage(
    examples: Sequence[FewShotExample],
    *,
    bird_root: Path,
) -> None:
    """Hard guard against leakage even though train/dev partition by db_id."""
    dev = load_bird_mini_dev(bird_root)
    dev_questions = {e.question.strip().lower() for e in dev}
    overlap = [
        e
        for e in examples
        if e.question.strip().lower() in dev_questions
    ]
    if overlap:
        msg = (
            f"FATAL: {len(overlap)} fewshot examples overlap with BIRD Mini-Dev. "
            "First: " + overlap[0].question[:120]
        )
        raise SystemExit(msg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--parquet",
        type=Path,
        default=Path("data/bird_train.parquet"),
        help="path to BIRD train parquet (default: data/bird_train.parquet)",
    )
    parser.add_argument(
        "--bird-root",
        type=Path,
        default=Path("data/bird_mini_dev/MINIDEV"),
        help="BIRD Mini-Dev root for the leakage check",
    )
    parser.add_argument(
        "--persist",
        type=Path,
        default=Path("chroma_data"),
        help="Chroma persist dir (must match build_index.py)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap on rows (default: full 9 428)",
    )
    parser.add_argument(
        "--embed-batch",
        type=int,
        default=16,
        help="batch size for embedding requests (default: 16)",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.mistral_api_key:
        print("[error] MISTRAL_API_KEY not set in .env", file=sys.stderr)
        return 2

    if not args.parquet.is_file():
        print(
            f"[error] parquet not found: {args.parquet}. Download from "
            "https://huggingface.co/datasets/xu3kev/BIRD-SQL-data-train",
            file=sys.stderr,
        )
        return 3

    examples = _load_train_examples(args.parquet, limit=args.limit)
    print(f"[info] loaded {len(examples)} fewshot examples from {args.parquet}")
    _assert_no_dev_leakage(examples, bird_root=args.bird_root)
    print("[info] leakage check passed (zero dev-question overlap)")

    embedder: CachingEmbeddingProvider = CachingEmbeddingProvider(
        MistralProvider(
            api_key=settings.mistral_api_key,
            gen_model=settings.mistral_gen_model,
            embed_model=settings.mistral_embed_model,
            base_url=settings.mistral_base_url,
        ),
        cache_dir=settings.llm_cache_dir,
        size_limit_gb=settings.llm_cache_size_limit_gb,
    )

    args.persist.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(args.persist))
    index = SchemaIndex(
        persist_dir=args.persist,
        embedder=embedder,
        client=client,
        embed_batch=args.embed_batch,
    )

    started = time.perf_counter()
    indexed = index.index_fewshots(examples)
    elapsed = time.perf_counter() - started
    print(f"[done] indexed {indexed} fewshot examples in {elapsed:.1f}s")
    print(f"[info] persist dir: {args.persist}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
