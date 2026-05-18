"""OpenRouter voting on baseline failures.

OpenAI-compatible /v1 endpoint at openrouter.ai/api/v1. Mirror of
run_groq_voting.py but routes through OpenRouter — обходит Groq RU-geoblock и
открывает 24+ free-tier reasoning/code models (gpt-oss, qwen3-coder,
deepseek-v4-flash, nvidia/nemotron, glm-4.5-air etc).

Usage:
    uv run python scripts/run_openrouter_voting.py \\
        --baseline eval/reports/2026-05-18/v16-helallao-dac-reasoning.json \\
        --provider-model openai/gpt-oss-120b:free \\
        --out eval/reports/2026-05-18b/gpt-oss-or-on-v16-residue.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from nl_sql.agent.graph import PipelineConfig, build_pipeline, run_pipeline
from nl_sql.config import get_settings
from nl_sql.db.registry import get_default_registry
from nl_sql.eval.dataset import load_bird_mini_dev
from nl_sql.eval.metrics.execution_accuracy import compare_results
from nl_sql.eval.runner import _compose_question, _execute_gold
from nl_sql.execution.runner import execute_validated
from nl_sql.llm.cache import CachingEmbeddingProvider
from nl_sql.llm.providers.base import GenerateRequest, GenerateResponse
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.indexer import SchemaIndex


def _read_openrouter_key() -> str:
    env = os.environ.get("OPENROUTER_API_KEY")
    if env:
        return env
    txt = Path("D:/TXT/Free API Keys.txt")
    if txt.exists():
        for line in txt.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("sk-or-v1-"):
                return line
    raise RuntimeError("OpenRouter key not found in OPENROUTER_API_KEY or D:/TXT/Free API Keys.txt")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--provider-model", required=True, help="OpenRouter model id, e.g. openai/gpt-oss-120b:free")
    p.add_argument("--bird-root", type=Path, default=Path("data/bird_mini_dev/MINIDEV"))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-cases", type=int, default=200)
    p.add_argument("--skip-qids", default="")
    p.add_argument("--sleep-between", type=float, default=2.0)
    args = p.parse_args()

    settings = get_settings()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    fails = [r for r in baseline["records"] if not r.get("match")]
    skip = {int(x) for x in args.skip_qids.split(",") if x.strip()}
    fails = [r for r in fails if r["question_id"] not in skip][: args.max_cases]
    print(f"[info] {len(fails)} failures to retry with openrouter+{args.provider_model}", file=sys.stderr)

    examples = {e.question_id: e for e in load_bird_mini_dev(args.bird_root)}
    registry = get_default_registry()
    api_key = _read_openrouter_key()
    raw = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    class _ORAlt:
        name = "openrouter_alt"
        model = args.provider_model

        def generate(self, req: GenerateRequest) -> GenerateResponse:
            t0 = time.perf_counter()
            try:
                completion = raw.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": req.prompt}],
                    temperature=req.temperature,
                    max_tokens=req.max_tokens,
                    extra_headers={
                        "HTTP-Referer": "https://github.com/brownjuly2003-code/NL_SQL",
                        "X-Title": "NL_SQL BIRD eval",
                    },
                )
            except Exception as exc:
                raise RuntimeError(f"openrouter {self.model}: {exc}") from exc
            lat = (time.perf_counter() - t0) * 1000.0
            choice = completion.choices[0] if completion.choices else None
            text = (choice.message.content if choice and choice.message else "") or ""
            return GenerateResponse(
                text=text,
                model=completion.model or self.model,
                input_tokens=(completion.usage.prompt_tokens if completion.usage else 0),
                output_tokens=(completion.usage.completion_tokens if completion.usage else 0),
                latency_ms=lat,
            )

    alt = _ORAlt()
    emb = CachingEmbeddingProvider(
        MistralProvider(api_key=settings.mistral_api_key), cache_dir=settings.llm_cache_dir
    )
    idx = SchemaIndex(persist_dir="chroma_data", embedder=emb)

    cfg = PipelineConfig(
        sql_provider=alt,  # type: ignore[arg-type]
        explain_provider=alt,  # type: ignore[arg-type]
        schema_index=idx,
        registry=registry,
        fewshot_top_k=3,
        sort_schema_block=True,
        cross_db_fewshot=True,
        verify_retry_on_empty=False,
        enable_grounded_critique=False,
    )
    pipeline = build_pipeline(cfg)

    records: list[dict[str, Any]] = []
    rescued = 0
    regressed = 0
    same = 0
    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    for i, br in enumerate(fails, 1):
        qid = br["question_id"]
        ex = examples.get(qid)
        if ex is None:
            continue
        spec = registry.get(ex.registry_db_id)
        engine = spec.make_engine()
        try:
            t0 = time.perf_counter()
            try:
                alt_res = run_pipeline(
                    pipeline,
                    question=_compose_question(ex),
                    db_id=ex.registry_db_id,
                    dialect="sqlite",
                )
            except Exception as exc:
                print(f"[{i:3d}/{len(fails)}] qid={qid} EXC: {str(exc)[:180]}", file=sys.stderr)
                time.sleep(args.sleep_between)
                continue
            elapsed = (time.perf_counter() - t0) * 1000.0

            alt_sql = alt_res.sql or ""
            alt_rows: list[Any] = []
            try:
                outcome = execute_validated(
                    engine, alt_sql, dialect="sqlite",
                    statement_timeout_ms=30_000, row_cap=10_000,
                )
                if outcome.result:
                    alt_rows = list(outcome.result.rows)
            except Exception:
                pass
            try:
                gold_rows, _ = _execute_gold(
                    engine, ex.sql, statement_timeout_ms=30_000, row_cap=10_000
                )
            except Exception:
                gold_rows = []
            alt_cmp = compare_results(gold_rows, alt_rows, gold_sql=ex.sql)
            alt_match = bool(alt_cmp.match)

            if alt_match and not br.get("match"):
                rescued += 1
                tag = "RESCUE"
            elif br.get("match") and not alt_match:
                regressed += 1
                tag = "regression"
            else:
                same += 1
                tag = "same"

            records.append({
                "question_id": qid,
                "db_id": ex.db_id,
                "difficulty": ex.difficulty,
                "question": ex.question,
                "gold_sql": ex.sql,
                "baseline_pred": br["pred_sql"],
                "alt_pred": alt_sql,
                "alt_confidence": getattr(alt_res, "confidence", None),
                "baseline_match": bool(br.get("match")),
                "alt_match": alt_match,
                "vote_match": alt_match,
                "vote_source": f"openrouter:{args.provider_model}",
                "elapsed_ms": elapsed,
            })
            print(
                f"[{i:3d}/{len(fails)}] qid={qid} {ex.difficulty:11s} {tag} ({elapsed / 1000:.1f}s)",
                file=sys.stderr,
            )

            out_path.write_text(json.dumps({
                "alt_model": f"openrouter:{args.provider_model}",
                "summary": {"voted_better": rescued, "voted_worse": regressed, "voted_same": same},
                "records": records,
            }, indent=2), encoding="utf-8")
        finally:
            engine.dispose()
        time.sleep(args.sleep_between)

    print("\n=== openrouter voting summary ===", file=sys.stderr)
    print(f"  model: {args.provider_model}", file=sys.stderr)
    print(f"  cases: {len(records)}", file=sys.stderr)
    print(f"  rescued: {rescued}", file=sys.stderr)
    print(f"  regressed: {regressed}", file=sys.stderr)
    print(f"  same: {same}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
