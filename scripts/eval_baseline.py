"""Live eval-baseline: configurations A or C on a BIRD Mini-Dev slice.

Runs an ablation configuration through the codestral-latest provider against
N BIRD examples (default 50), prints per-question status, and writes both
JSON and HTML artefacts to `eval/reports/<date>/`. Configurations B/D/E are
not yet implemented; they will join the same CLI shape when they ship.

Usage:
    uv run python scripts/eval_baseline.py --config A --n 50 --seed 0
    uv run python scripts/eval_baseline.py --config C --n 50 --seed 0
    uv run python scripts/eval_baseline.py --n 5 --db bird_california_schools
    uv run python scripts/eval_baseline.py --config C --only-qids 1399,1205
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import chromadb

from nl_sql.config import Settings, get_settings
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

# Which Settings field carries the generation model for each provider, so
# `--sql-model` can retarget one without editing .env.
_MODEL_FIELD: dict[str, str] = {
    "mistral": "mistral_gen_model",
    "groq": "groq_model",
    "github_models": "github_models_model",
    "ollama": "ollama_gen_model",
    "openrouter": "openrouter_model",
    "perplexity": "perplexity_browser_model",
    "gracekelly": "gracekelly_model",
    "zen": "zen_model",
    "grok_cli": "grok_cli_model",
    "claude_cli": "claude_cli_model",
}

# Only the two agent-CLI providers expose a reasoning-effort dial.
_EFFORT_FIELD: dict[str, str] = {
    "grok_cli": "grok_cli_effort",
    "claude_cli": "claude_cli_effort",
}


def _build_provider_with_model(
    name: str,
    settings: Settings,
    model_override: str | None,
    effort_override: str | None = None,
) -> LLMProvider:
    if model_override:
        settings = settings.model_copy(update={_MODEL_FIELD[name]: model_override})
    if effort_override:
        if name not in _EFFORT_FIELD:
            raise SystemExit(
                f"--sql-effort is not supported by provider {name!r} "
                f"(only: {', '.join(sorted(_EFFORT_FIELD))})"
            )
        settings = settings.model_copy(update={_EFFORT_FIELD[name]: effort_override})
    return build_provider(name, settings=settings)


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
        "--only-qids",
        default="",
        help=(
            "comma-separated BIRD question IDs to run exactly, preserving "
            "argument order and bypassing --n/--seed sampling"
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
        "--bird-rescue-hints",
        action="store_true",
        help=(
            "inject the per-question BIRD schema-link rescue hints (the "
            "annotation-quirk adaptation layer). On the reproducible single-run this "
            "takes EA from 58.0%% to 62.5%%. Eval-only and OFF by default — the product "
            "pipeline never serves these."
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
        "--dac",
        action="store_true",
        help=(
            "config E: use the CHASE-SQL divide-and-conquer prompt "
            "(generate_sql_dac.txt) — decomposes a multi-clause question into "
            "sub-questions before composing SQL. Was reachable only from the API's "
            "env toggle, so it had never been measured against the product config."
        ),
    )
    parser.add_argument(
        "--m-schema",
        action="store_true",
        help="config E: render the schema block in M-Schema form (same story as --dac)",
    )
    parser.add_argument(
        "--compact-prompt",
        action="store_true",
        help=(
            "config E: use generate_sql_compact.txt — evidence-first like the "
            "default, but without the coaching the default accumulated for "
            "codestral (Chinook-taught DISTINCT rule, projection drilling, "
            "per-database disambiguation). Intended for frontier models, where "
            "that coaching is noise and prompt length is latency."
        ),
    )
    parser.add_argument(
        "--critique",
        action="store_true",
        help=(
            "config E: enable the post-execute grounded-critique node "
            "(PipelineConfig.enable_grounded_critique) — a cheap row-count-shape "
            "heuristic (NOT an LLM call) that compares the executed row count "
            "against a shape inferred from the question text and routes a "
            "mismatch to repair_once. The only lever that can send a 'valid SQL, "
            "wrong rows' result (error_kind=None) into repair. Default off."
        ),
    )
    parser.add_argument(
        "--retry-on-empty",
        action="store_true",
        help=(
            "config E: route an EMPTY_RESULT outcome to repair_once "
            "(PipelineConfig.verify_retry_on_empty) — the same lever config G "
            "hardcodes on, exposed here so it can be measured on top of E in "
            "isolation from G's other defaults (fewshot/sort/cross-db). "
            "Default off."
        ),
    )
    parser.add_argument(
        "--value-retrieval",
        action="store_true",
        help=(
            "config E: CHESS-style question-driven value retrieval "
            "(PipelineConfig.enable_value_retrieval) — scan text columns of "
            "schema-RAG tables for cell values matching question tokens and "
            "inject short grounding lines next to the question. Default off."
        ),
    )
    parser.add_argument(
        "--fewshot-selection",
        choices=["dense", "dail", "synthetic"],
        default="dense",
        help=(
            "config E: how to pick few-shot Q→SQL pairs "
            "(PipelineConfig.fewshot_selection). 'dense' (default) embeds the "
            "raw question; 'dail' embeds a schema-masked question (DAIL-SQL 2a) "
            "so shots prefer intent over shared table/column names; 'synthetic' "
            "(A3, CHASE-SQL) spends one extra mistral call per question writing "
            "fresh Q→SQL pairs against the target schema, replacing the "
            "retrieved shots. Default dense."
        ),
    )
    parser.add_argument(
        "--column-descriptions",
        choices=["off", "targeted"],
        default="off",
        help=(
            "config E: A8 targeted column descriptions "
            "(PipelineConfig.description_embedder). 'targeted' ranks the BIRD "
            "description lines of the retrieved tables by embedding similarity "
            "to the question and appends the top-5 to the schema block. The "
            "whole-schema variant cost -1.5 EA in prompt rent; this pays only "
            "for likely-relevant lines. Default off."
        ),
    )
    parser.add_argument(
        "--enrich-question",
        action="store_true",
        help=(
            "config E: A4 question enrichment (E-SQL 2409.16751, "
            "PipelineConfig.enrichment_provider) — one extra mistral call per "
            "question rewrites it into an explicit restatement (schema names, "
            "conditions, steps) rendered NEXT TO the original question in the "
            "generate prompt. Default off."
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
        "--dialect",
        choices=["sqlite", "postgresql"],
        default="sqlite",
        help=(
            "SQL dialect of the run. 'postgresql' loads BIRD's Postgres gold "
            "(mini_dev_postgresql.json — 312/500 golds are rewritten for PG, e.g. "
            "STRFTIME → TO_CHAR) and prompts the model for Postgres SQL. Requires "
            "--pg-dsn, and every sampled example must resolve to a Postgres-backed "
            "database (default: sqlite)."
        ),
    )
    parser.add_argument(
        "--pg-dsn",
        default="",
        help=(
            "Postgres DSN serving --pg-db-id (owner or read-only role). Load it "
            "first: scripts/extract_pg_dump_slice.py + psql, see docs/03_eval_methodology.md §14."
        ),
    )
    parser.add_argument(
        "--pg-db-id",
        default="bird_codebase_community",
        help="registry id served by --pg-dsn (default: bird_codebase_community)",
    )
    parser.add_argument(
        "--provider",
        choices=[
            "mistral",
            "groq",
            "github_models",
            "ollama",
            "perplexity",
            "openrouter",
            "gracekelly",
            "zen",
            "grok_cli",
            "claude_cli",
        ],
        default="mistral",
        help=(
            "LLM provider for generation (embedding stays mistral — only "
            "Mistral implements EmbeddingProvider). Used for the "
            "architecture §1 provider bakeoff."
        ),
    )
    parser.add_argument(
        "--sql-model",
        default=None,
        help=(
            "override the generation model for --provider (e.g. gpt-5-6-terra, "
            "gemini-3-1-pro, claude-sonnet-5 for gracekelly). Default: the "
            "provider's configured model."
        ),
    )
    parser.add_argument(
        "--sql-effort",
        default=None,
        choices=["low", "medium", "high", "xhigh", "max"],
        help=(
            "reasoning effort for the generation model. Only grok_cli and "
            "claude_cli support it; the spawned CLI does not inherit the effort "
            "of the calling session, so an effort ablation needs this flag. "
            "Cached separately from the same model's default-effort answers."
        ),
    )
    parser.add_argument(
        "--explain-provider",
        default=None,
        help=(
            "provider for the explain_trace caption (default: same as --provider). "
            "The caption never enters the EA comparison, so on a slow/metered "
            "generation provider (gracekelly drives a browser: ~56s and one "
            "Perplexity quota unit per call) point this at `mistral` to halve "
            "both wall-clock and quota without touching the measured number."
        ),
    )
    args = parser.parse_args(argv)

    # Validate CLI input before the (filesystem-dependent) dataset load, so a
    # typo fails fast with exit 3 instead of a FileNotFoundError on hosts
    # without the BIRD dump.
    try:
        only_qids = [int(x) for x in args.only_qids.split(",") if x.strip()]
    except ValueError:
        print("[error] invalid --only-qids: expected comma-separated integers", file=sys.stderr)
        return 3

    if args.dialect == "postgresql" and not args.pg_dsn:
        print("[error] --dialect postgresql requires --pg-dsn", file=sys.stderr)
        return 3

    examples = load_bird_mini_dev(Path(args.bird_root), dialect=args.dialect)
    if args.db:
        examples = [e for e in examples if e.registry_db_id == args.db]
        if not examples:
            print(f"[error] no examples for db {args.db!r}", file=sys.stderr)
            return 3

    if only_qids:
        examples_by_qid = {e.question_id: e for e in examples}
        sample = [examples_by_qid[qid] for qid in only_qids if qid in examples_by_qid]
        missing_qids = [qid for qid in only_qids if qid not in examples_by_qid]
        if missing_qids:
            print(f"[error] qids not found after filters: {missing_qids}", file=sys.stderr)
            return 3
    else:
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

    registry = get_default_registry(pg_dsn=args.pg_dsn, pg_db_id=args.pg_db_id)
    missing = sorted({e.registry_db_id for e in sample} - set(registry.ids()))
    if missing:
        print(
            f"[error] sampled examples reference unregistered DBs: {missing}\n"
            f"  registered: {registry.ids()}",
            file=sys.stderr,
        )
        return 4

    # Gold SQL is dialect-specific: BIRD's Postgres gold uses TO_CHAR/CAST where
    # the SQLite gold uses STRFTIME. Executing it against a SQLite engine would
    # not error out loudly enough — it would just fail the query and score a
    # miss, quietly reporting a bogus EA. Refuse the run instead.
    wrong_engine = sorted(
        {e.registry_db_id for e in sample if registry.get(e.registry_db_id).dialect != args.dialect}
    )
    if wrong_engine:
        print(
            f"[error] --dialect {args.dialect} but these DBs are not backed by "
            f"{args.dialect}: {wrong_engine}\n"
            f"  load one first (scripts/extract_pg_dump_slice.py) and pass "
            f"--pg-dsn/--pg-db-id, or narrow the run with --db {args.pg_db_id}",
            file=sys.stderr,
        )
        return 4

    settings = get_settings()
    if not settings.mistral_api_key:
        print("[error] MISTRAL_API_KEY not set in .env", file=sys.stderr)
        return 2

    raw_sql_provider = _build_provider_with_model(
        args.provider, settings, args.sql_model, args.sql_effort
    )
    _effort = getattr(raw_sql_provider, "effort", None)
    print(
        f"[info] provider: {args.provider} (model={raw_sql_provider.model}"
        f"{f', effort={_effort}' if _effort else ''})"
    )

    def _wrap_cache(provider: LLMProvider) -> LLMProvider:
        if args.no_cache:
            return provider
        return CachingLLMProvider(
            provider,
            cache_dir=settings.llm_cache_dir,
            size_limit_gb=settings.llm_cache_size_limit_gb,
        )

    sql_provider: LLMProvider = _wrap_cache(raw_sql_provider)
    if args.no_cache:
        print("[info] cache: DISABLED (--no-cache)")
    else:
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
        # The caption never enters the EA comparison. Keeping it on the same
        # provider is fine for codestral, but on a browser-driven provider it
        # would double both wall-clock and Perplexity quota for zero effect on
        # the measured number — so allow pinning it elsewhere.
        explain_provider: LLMProvider = sql_provider
        if args.explain_provider and args.explain_provider != args.provider:
            explain_provider = _wrap_cache(
                _build_provider_with_model(args.explain_provider, settings, None)
            )
            print(f"[info] explain provider: {args.explain_provider} (caption only, not scored)")
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
                enable_bird_rescue_hints=args.bird_rescue_hints,
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
                enable_bird_rescue_hints=args.bird_rescue_hints,
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
                enable_bird_rescue_hints=args.bird_rescue_hints,
                primary_sample_size=args.primary_sample_size,
                extended_sample_size=args.extended_sample_size,
                progress=_on_progress,
            )
        else:
            runner = run_config_c if args.config == "C" else run_config_e
            # A3: synthesis rides the free Mistral tier regardless of who the
            # SQL generator is — a metered generator (zen/grok/claude) must not
            # pay for the extra per-question call.
            fewshot_synthesis_provider: LLMProvider | None = None
            if args.config != "C" and args.fewshot_selection == "synthetic":
                fewshot_synthesis_provider = _wrap_cache(
                    _build_provider_with_model("mistral", settings, None)
                )
                print("[info] fewshot synthesis provider: mistral (A3 synthetic few-shots)")
            # A4: same free-Mistral rule as A3 — the auxiliary call must not
            # ride a metered generator.
            enrichment_provider: LLMProvider | None = None
            if args.config != "C" and args.enrich_question:
                enrichment_provider = _wrap_cache(
                    _build_provider_with_model("mistral", settings, None)
                )
                print("[info] question enrichment provider: mistral (A4 E-SQL)")
            if args.config != "C" and args.column_descriptions == "targeted":
                print("[info] column descriptions: targeted top-5 (A8)")
            # Only E takes a few-shot pool: C is the no-repair, no-fewshot ablation
            # and must stay that way to remain comparable with its own history.
            extra: dict[str, Any] = (
                {}
                if args.config == "C"
                else {
                    "fewshot_top_k": args.fewshot_top_k,
                    "use_dac_prompt": args.dac,
                    "use_m_schema": args.m_schema,
                    "use_compact_prompt": args.compact_prompt,
                    "enable_grounded_critique": args.critique,
                    "verify_retry_on_empty": args.retry_on_empty,
                    "enable_value_retrieval": args.value_retrieval,
                    "fewshot_selection": args.fewshot_selection,
                    "fewshot_synthesis_provider": fewshot_synthesis_provider,
                    "enrichment_provider": enrichment_provider,
                    "description_embedder": (
                        embedder if args.column_descriptions == "targeted" else None
                    ),
                }
            )
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
                enable_bird_rescue_hints=args.bird_rescue_hints,
                primary_sample_size=args.primary_sample_size,
                extended_sample_size=args.extended_sample_size,
                progress=_on_progress,
                **extra,
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

    # A question that never reached the model is not a question the model got wrong,
    # but execution accuracy cannot tell the two apart — a pipeline_exception scores
    # exactly like a bad query. On 2026-07-14 that silently understated three separate
    # runs: a truncated CLI preamble, cached empty completions, and 24 dropped process
    # spawns, each of which read as "this generator is worse". So say it out loud.
    broken = [r for r in run.records if r.error_kind == "pipeline_exception"]
    if broken:
        ceiling = (run.overall.ea * len(run.records) + len(broken)) / len(run.records)
        print()
        print(f"🔴 {len(broken)}/{len(run.records)} questions never reached the model")
        print("   (pipeline_exception — transport, not the answer). EA below is a FLOOR:")
        print(f"   with those {len(broken)} fixed it could be up to {ceiling * 100:.1f}%.")
        print("   Do NOT report this number. Fix the transport and re-run — the LLM cache")
        print("   replays every question that succeeded, so only the broken ones cost anything.")
        kinds = Counter((r.error_message or "?").split(":")[0][:60] for r in broken)
        for kind, count in kinds.most_common(3):
            print(f"     {count:>3}x {kind}")

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
        except (KeyError, TypeError, ValueError) as exc:
            print(f"[warn] skipped {other.name}: {exc}", file=sys.stderr)
    html_path = write_html_report([*prior_runs, run], root=args.reports)
    print()
    print(f"[json] {json_path}")
    print(f"[html] {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
