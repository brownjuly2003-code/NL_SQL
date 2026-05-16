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
    run_config_d,
    run_config_e,
    run_config_f,
    run_config_g,
    write_html_report,
    write_json_report,
)
from nl_sql.eval.dataset import DEFAULT_BIRD_ROOT
from nl_sql.llm.cache import CachingEmbeddingProvider, CachingLLMProvider
from nl_sql.llm.providers import build_provider
from nl_sql.llm.providers.base import EmbeddingProvider, LLMProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.indexer import SchemaIndex


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=50, help="number of BIRD examples (default: 50)")
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
        "--difficulty",
        choices=["simple", "moderate", "challenging"],
        default=None,
        help=(
            "optional difficulty filter; useful for tier-specific runs "
            "(e.g. --difficulty challenging to run config F only on the "
            "hard tier and merge with G for the rest — see "
            "docs/SESSION_HANDOFF.md for the hybrid recipe)."
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
        choices=["A", "C", "D", "E", "F", "G"],
        default="A",
        help=(
            "ablation configuration "
            "(A=full_schema, C=dense+FK no repair, "
            "E=dense+FK+repair_once, F=dense+FK+self-consistency)"
        ),
    )
    parser.add_argument(
        "--sql-candidate-temperatures",
        default="0.2,0.4,0.6,0.8",
        help=(
            "comma-separated sampling temperatures for config F "
            "(self-consistency). One pipeline pass per temperature; "
            "default 4 candidates at 0.2/0.4/0.6/0.8."
        ),
    )
    parser.add_argument(
        "--persist",
        default="chroma_data",
        help="chroma persist directory (config C only; default: chroma_data/)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help=(
            "disable diskcache wrappers around the LLM/embedding providers. "
            "Default is cached — re-running the same examples is then $0 + "
            "deterministic, so ablations compare apples to apples."
        ),
    )
    parser.add_argument(
        "--schema-top-k",
        type=int,
        default=5,
        help="dense schema retrieval top-k (configs C/E; default: 5)",
    )
    parser.add_argument(
        "--fk-hops",
        type=int,
        default=1,
        help="FK graph expansion hops (configs C/E; default: 1)",
    )
    parser.add_argument(
        "--table-budget",
        type=int,
        default=12,
        help="max tables in the schema block (configs C/E; default: 12)",
    )
    parser.add_argument(
        "--report-suffix",
        default="",
        help=(
            "extra string appended to <config>.json so knob-bump runs don't "
            "overwrite the baseline (e.g. '--report-suffix=topk8' → "
            "C_dense_cards-topk8.json)"
        ),
    )
    parser.add_argument(
        "--sort-schema-block",
        action="store_true",
        help=(
            "render schema_block in alphabetical-by-table-name order "
            "(configs C/E only; default: retrieval-distance + FK BFS order). "
            "Tests the hypothesis that codestral is order-sensitive on "
            "moderate-tier BIRD questions."
        ),
    )
    parser.add_argument(
        "--primary-sample-size",
        type=int,
        default=3,
        help=(
            "sample density baked into the chunks stored in Chroma "
            "(must match the --sample-size used at build_index time; "
            "default: 3)"
        ),
    )
    parser.add_argument(
        "--fewshot-top-k",
        type=int,
        default=3,
        help=(
            "number of fewshot Q→SQL pairs to retrieve from the "
            "fewshot_qsql collection (configs D/G/F-with-fewshot; "
            "default: 3). Higher values give the LLM more templates "
            "but inflate prompt token count and risk distracting the "
            "generator with off-topic examples."
        ),
    )
    parser.add_argument(
        "--with-fewshot",
        action="store_true",
        help=(
            "enable cross-db fewshot retrieval for config F "
            "(self-consistency). D and G have fewshot ON by default; "
            "for F it's opt-in so old F runs stay comparable."
        ),
    )
    parser.add_argument(
        "--extended-sample-size",
        type=int,
        default=0,
        help=(
            "per-difficulty sample mixture (configs C/E only; default: 0 "
            "= disabled). When > primary_sample_size, the schema_block "
            "appendix lists samples primary..extended per column for "
            "retrieved tables, so the model has both densities in one "
            "prompt. Re-introspects the live DB at runtime — no chroma "
            "rebuild needed. Recommended value: 5."
        ),
    )
    parser.add_argument(
        "--provider",
        choices=["mistral", "groq", "github_models", "ollama", "perplexity"],
        default="mistral",
        help=(
            "LLM provider for generation (embedding stays mistral — only "
            "Mistral implements EmbeddingProvider). Used for the "
            "architecture §1 provider bakeoff."
        ),
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
    if args.difficulty:
        # Apply AFTER dev_split so the same shuffle-prefix examples appear
        # as in unfiltered runs — needed for hybrid merging (e.g., F on
        # challenging tier blended with G on the rest).
        sample = [e for e in sample if e.difficulty == args.difficulty]
        if not sample:
            print(
                f"[error] no examples for difficulty {args.difficulty!r} "
                f"within the n={args.n} prefix",
                file=sys.stderr,
            )
            return 3
    print(f"[info] loaded {len(examples)} examples → sampled {len(sample)} (seed={args.seed})")
    missing = sorted({e.registry_db_id for e in sample} - set(registry.ids()))
    if missing:
        print(
            f"[error] sampled examples reference unregistered DBs: {missing}\n"
            f"  registered: {registry.ids()}",
            file=sys.stderr,
        )
        return 4

    raw_sql_provider = build_provider(args.provider, settings=settings)
    print(f"[info] provider: {args.provider} (model={raw_sql_provider.model})")
    sql_provider: LLMProvider
    if args.no_cache:
        sql_provider = raw_sql_provider
        print("[info] cache: DISABLED (--no-cache)")
    else:
        sql_provider = CachingLLMProvider(
            raw_sql_provider,
            cache_dir=settings.llm_cache_dir,
            size_limit_gb=settings.llm_cache_size_limit_gb,
        )
        print(f"[info] cache: ENABLED at {settings.llm_cache_dir}/")

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
    else:  # "C", "E", or "F" — all need the Chroma index
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
        raw_embedder = MistralProvider(
            api_key=settings.mistral_api_key,
            gen_model=settings.mistral_gen_model,
            embed_model=settings.mistral_embed_model,
            base_url=settings.mistral_base_url,
        )
        embedder: EmbeddingProvider = (
            raw_embedder
            if args.no_cache
            else CachingEmbeddingProvider(
                raw_embedder,
                cache_dir=settings.llm_cache_dir,
                size_limit_gb=settings.llm_cache_size_limit_gb,
            )
        )
        index = SchemaIndex(persist_dir=persist_dir, embedder=embedder, client=chroma_client)
        explain_provider = sql_provider  # codestral works for caption too in eval
        if args.config == "F":
            temps = tuple(float(x) for x in args.sql_candidate_temperatures.split(",") if x.strip())
            print(f"[info] self-consistency: {len(temps)} candidates @ {temps}")
            run = run_config_f(
                sample,
                sql_provider=sql_provider,
                explain_provider=explain_provider,
                schema_index=index,
                registry=registry,
                schema_top_k=args.schema_top_k,
                fewshot_top_k=args.fewshot_top_k if args.with_fewshot else 0,
                fk_hops=args.fk_hops,
                table_budget=args.table_budget,
                sort_schema_block=args.sort_schema_block,
                primary_sample_size=args.primary_sample_size,
                extended_sample_size=args.extended_sample_size,
                sql_candidate_temperatures=temps,
                cross_db_fewshot=args.with_fewshot,
                progress=_on_progress,
            )
        elif args.config == "D":
            run = run_config_d(
                sample,
                sql_provider=sql_provider,
                explain_provider=explain_provider,
                schema_index=index,
                registry=registry,
                schema_top_k=args.schema_top_k,
                fewshot_top_k=args.fewshot_top_k,
                fk_hops=args.fk_hops,
                table_budget=args.table_budget,
                sort_schema_block=args.sort_schema_block,
                primary_sample_size=args.primary_sample_size,
                extended_sample_size=args.extended_sample_size,
                progress=_on_progress,
            )
        elif args.config == "G":
            run = run_config_g(
                sample,
                sql_provider=sql_provider,
                explain_provider=explain_provider,
                schema_index=index,
                registry=registry,
                schema_top_k=args.schema_top_k,
                fewshot_top_k=args.fewshot_top_k,
                fk_hops=args.fk_hops,
                table_budget=args.table_budget,
                sort_schema_block=args.sort_schema_block,
                primary_sample_size=args.primary_sample_size,
                extended_sample_size=args.extended_sample_size,
                progress=_on_progress,
            )
        else:
            runner = run_config_c if args.config == "C" else run_config_e
            run = runner(
                sample,
                sql_provider=sql_provider,
                explain_provider=explain_provider,
                schema_index=index,
                registry=registry,
                schema_top_k=args.schema_top_k,
                fk_hops=args.fk_hops,
                table_budget=args.table_budget,
                sort_schema_block=args.sort_schema_block,
                primary_sample_size=args.primary_sample_size,
                extended_sample_size=args.extended_sample_size,
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
    print(
        f"  simple:      {run.per_difficulty['simple'].ea * 100:.1f}% (n={run.per_difficulty['simple'].n})"
    )
    print(
        f"  moderate:    {run.per_difficulty['moderate'].ea * 100:.1f}% (n={run.per_difficulty['moderate'].n})"
    )
    print(
        f"  challenging: {run.per_difficulty['challenging'].ea * 100:.1f}% (n={run.per_difficulty['challenging'].n})"
    )
    print(f"Validity:      {run.overall.validity_rate * 100:.1f}%")
    print(
        f"Repair fired:  {sum(1 for r in run.records if r.repair_attempted)}/{run.overall.n}; success rate {run.overall.repair_success_rate * 100:.1f}%"
    )
    print(
        f"Schema rec@k:  {run.overall.schema_recall_at_k * 100:.1f}%  (k = full schema, so recall ≈ 100% expected)"
    )
    print(f"Empty result:  {run.overall.empty_result_rate * 100:.1f}%")
    print(f"Latency P50:   {run.overall.latency_p50_ms:.0f} ms")
    print(f"Latency P95:   {run.overall.latency_p95_ms:.0f} ms")
    print(f"Tokens P50:    {run.overall.tokens_p50:.0f}")
    print(f"Tokens P95:    {run.overall.tokens_p95:.0f}")
    print(f"Wall time:     {elapsed:.1f}s")

    json_path = write_json_report(run, root=args.reports, name_suffix=args.report_suffix)

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
