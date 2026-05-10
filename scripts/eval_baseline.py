"""Live eval-baseline: configuration A on a small BIRD slice.

Runs the `full_schema` baseline through the codestral-latest provider against
N BIRD Mini-Dev examples (default 50), prints per-question status, and writes
both JSON and HTML artefacts to `eval/reports/<date>/`.

This is the first end-to-end harness call — its purpose is "the harness
works on real data", not "the EA number is good". The number is reported
as-is per `docs/03_eval_methodology.md` §10.

Usage:
    uv run python scripts/eval_baseline.py
    uv run python scripts/eval_baseline.py --n 50 --seed 0
    uv run python scripts/eval_baseline.py --n 5 --db bird_california_schools
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from nl_sql.config import get_settings
from nl_sql.db.registry import get_default_registry
from nl_sql.eval import (
    Configuration,
    EvalRecord,
    dev_split,
    load_bird_mini_dev,
    run_config_a,
    write_html_report,
    write_json_report,
)
from nl_sql.eval.dataset import DEFAULT_BIRD_ROOT
from nl_sql.llm.providers.mistral import MistralProvider


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
        choices=["A"],
        default="A",
        help="ablation configuration (only A implemented in stage 6 milestone 1)",
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
    run = run_config_a(
        sample,
        sql_provider=sql_provider,
        registry=registry,
        progress=_on_progress,
    )
    elapsed = time.perf_counter() - started

    print()
    print("=" * 78)
    print(f"Configuration: {Configuration.A_FULL_SCHEMA.value}")
    print(f"Model:         {run.sql_model}")
    print(f"Examples:      {run.overall.n}")
    print(f"EA:            {run.overall.ea * 100:.1f}%")
    print(f"  simple:      {run.per_difficulty['simple'].ea * 100:.1f}% (n={run.per_difficulty['simple'].n})")
    print(f"  moderate:    {run.per_difficulty['moderate'].ea * 100:.1f}% (n={run.per_difficulty['moderate'].n})")
    print(f"  challenging: {run.per_difficulty['challenging'].ea * 100:.1f}% (n={run.per_difficulty['challenging'].n})")
    print(f"Validity:      {run.overall.validity_rate * 100:.1f}%")
    print(f"Schema rec@k:  {run.overall.schema_recall_at_k * 100:.1f}%  (k = full schema, so recall ≈ 100% expected)")
    print(f"Empty result:  {run.overall.empty_result_rate * 100:.1f}%")
    print(f"Latency P50:   {run.overall.latency_p50_ms:.0f} ms")
    print(f"Latency P95:   {run.overall.latency_p95_ms:.0f} ms")
    print(f"Tokens P50:    {run.overall.tokens_p50:.0f}")
    print(f"Tokens P95:    {run.overall.tokens_p95:.0f}")
    print(f"Wall time:     {elapsed:.1f}s")

    json_path = write_json_report(run, root=args.reports)
    html_path = write_html_report([run], root=args.reports)
    print()
    print(f"[json] {json_path}")
    print(f"[html] {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
