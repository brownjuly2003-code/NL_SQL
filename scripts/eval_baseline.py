"""Live eval-baseline: configurations A or C on a BIRD Mini-Dev slice.

Runs an ablation configuration through the codestral-latest provider against
N BIRD examples (default 50), prints per-question status, and writes both
JSON and HTML artefacts to `eval/reports/<date>/`. Configurations B/D/E are
not yet implemented; they will join the same CLI shape when they ship.

Usage:
    uv run python scripts/eval_baseline.py --config A --n 50 --seed 0
    uv run python scripts/eval_baseline.py --config C --n 50 --seed 0
    uv run python scripts/eval_baseline.py --n 5 --db bird_california_schools
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import chromadb

from nl_sql.config import get_settings
from nl_sql.db.registry import get_default_registry
from nl_sql.eval import (
    EvalRecord,
    EvalRun,
    dev_split,
    load_bird_mini_dev,
    load_run_from_json,
    run_config_a,
    run_config_c,
    run_config_e,
    write_html_report,
    write_json_report,
)
from nl_sql.eval.dataset import DEFAULT_BIRD_ROOT
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.indexer import SchemaIndex


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n", type=int, default=50, help="number of BIRD examples (default: 50)"
    )
    parser.add_argument("--seed", type=int, default=0, help="dev_split seed")
    parser.add_argument(
        "--db",
        default=None,
        help=(
            "optional registry-id filter (e.g. bird_california_schools); "
            "if set, only examples for that DB are kept"
        ),
    )
    parser.add_argument(
        "--bird-root",
        default=str(DEFAULT_BIRD_ROOT),
        help=f"path to MINIDEV/ root (default: {DEFAULT_BIRD_ROOT})",
    )
    parser.add_argument("--reports", default="eval/reports", help="output root")
    parser.add_argument(
        "--config",
        choices=["A", "C", "E"],
        default="A",
        help=(
            "ablation configuration "
            "(A=full_schema, C=dense+FK no repair, E=dense+FK+repair_once)"
        ),
    )
    parser.add_argument(
        "--persist",
        default="chroma_data",
        help="chroma persist directory (config C only; default: chroma_data/)",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.mistral_api_key:
        print("[error] MISTRAL_API_KEY not set in .env", file=sys.stderr)
        return 2

    registry = get_default_registry()
    examples = load_bird_mini_dev(Path(args.bird_root))
    if args.db:
        examples = [e for e in examples if e.registry_db_id == args.db]
        if not examples:
            print(f"[error] no examples for db {args.db!r}", file=sys.stderr)
            return 3

    sample = dev_split(examples, n=args.n, seed=args.seed)
    print(
        f"[info] loaded {len(examples)} examples → "
        f"sampled {len(sample)} (seed={args.seed})"
    )
    missing = sorted({e.registry_db_id for e in sample} - set(registry.ids()))
    if missing:
        print(
            f"[error] sampled examples reference unregistered DBs: {missing}\n"
            f"  registered: {registry.ids()}",
            file=sys.stderr,
        )
        return 4

    sql_provider = MistralProvider(
        api_key=settings.mistral_api_key,
        gen_model=settings.mistral_gen_model,
        embed_model=settings.mistral_embed_model,
        base_url=settings.mistral_base_url,
    )

    started = time.perf_counter()

    def _on_progress(idx: int, total: int, rec: EvalRecord) -> None:
        flag = "OK " if rec.match else "MISS"
        err = f" [{rec.error_kind}]" if rec.error_kind else ""
        recall = "rec✓" if rec.schema_recall else "rec✗"
        print(
            f"  [{idx:>3}/{total}] {flag} {recall} ({rec.latency_ms:6.0f}ms) "
            f"{rec.db_id}/{rec.difficulty}{err} — {rec.question[:80]}"
        )

    print(f"[info] running configuration {args.config} on {len(sample)} examples …")
    run: EvalRun
    if args.config == "A":
        run = run_config_a(
            sample,
            sql_provider=sql_provider,
            registry=registry,
            progress=_on_progress,
        )
    else:  # "C" or "E" — both need the Chroma index
        persist_dir = Path(args.persist)
        if not persist_dir.is_dir():
            print(
                f"[error] chroma persist dir not found: {persist_dir}. "
                f"Run `python scripts/build_index.py --db all` first.",
                file=sys.stderr,
            )
            return 5
        chroma_client = chromadb.PersistentClient(path=str(persist_dir))
        # Embedding provider also Mistral — same key, same `mistral-embed`.
        embedder = MistralProvider(
            api_key=settings.mistral_api_key,
            gen_model=settings.mistral_gen_model,
            embed_model=settings.mistral_embed_model,
            base_url=settings.mistral_base_url,
        )
        index = SchemaIndex(
            persist_dir=persist_dir, embedder=embedder, client=chroma_client
        )
        explain_provider = sql_provider  # codestral works for caption too in eval
        runner = run_config_c if args.config == "C" else run_config_e
        run = runner(
            sample,
            sql_provider=sql_provider,
            explain_provider=explain_provider,
            schema_index=index,
            registry=registry,
            progress=_on_progress,
        )
    elapsed = time.perf_counter() - started

    print()
    print("=" * 78)
    print(f"Configuration: {run.configuration.value}")
    print(f"Model:         {run.sql_model}")
    print(f"Examples:      {run.overall.n}")
    print(f"EA (final):    {run.overall.ea * 100:.1f}%")
    print(f"EA (1st pass): {run.overall.first_pass_ea * 100:.1f}%")
    print(f"  simple:      {run.per_difficulty['simple'].ea * 100:.1f}% (n={run.per_difficulty['simple'].n})")
    print(f"  moderate:    {run.per_difficulty['moderate'].ea * 100:.1f}% (n={run.per_difficulty['moderate'].n})")
    print(f"  challenging: {run.per_difficulty['challenging'].ea * 100:.1f}% (n={run.per_difficulty['challenging'].n})")
    print(f"Validity:      {run.overall.validity_rate * 100:.1f}%")
    print(f"Repair fired:  {sum(1 for r in run.records if r.repair_attempted)}/{run.overall.n}; success rate {run.overall.repair_success_rate * 100:.1f}%")
    print(f"Schema rec@k:  {run.overall.schema_recall_at_k * 100:.1f}%  (k = full schema, so recall ≈ 100% expected)")
    print(f"Empty result:  {run.overall.empty_result_rate * 100:.1f}%")
    print(f"Latency P50:   {run.overall.latency_p50_ms:.0f} ms")
    print(f"Latency P95:   {run.overall.latency_p95_ms:.0f} ms")
    print(f"Tokens P50:    {run.overall.tokens_p50:.0f}")
    print(f"Tokens P95:    {run.overall.tokens_p95:.0f}")
    print(f"Wall time:     {elapsed:.1f}s")

    json_path = write_json_report(run, root=args.reports)

    # Combine today's run with any other configurations that finished earlier
    # so the HTML index keeps a single side-by-side ablation table per day.
    today_dir = json_path.parent
    prior_runs: list[EvalRun] = []
    for other in sorted(today_dir.glob("*.json")):
        if other == json_path:
            continue
        try:
            prior_runs.append(load_run_from_json(other))
        except (KeyError, ValueError) as exc:
            print(f"[warn] skipped {other.name}: {exc}", file=sys.stderr)
    html_path = write_html_report([*prior_runs, run], root=args.reports)
    print()
    print(f"[json] {json_path}")
    print(f"[html] {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
