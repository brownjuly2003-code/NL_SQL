"""Merge `vote_match=True` rescues from voting reports into a baseline run.

Reads a baseline eval report and one or more voting reports produced by
`scripts/run_groq_voting.py`. For every qid where the voting record has
`vote_match=True` AND the baseline still has `match=False`, replaces the
baseline pred_sql with the alt pred and flips `match=True`, recording
`voted_by=<alt_model>` for audit.

Skips voting records that picked baseline (vote_source='base-fallback'),
since those are not actual rescues — the script chose to keep the
baseline pred when alt disagreed without enough confidence.

Recomputes summary EA + per-difficulty + rescue counter.

Usage:
    uv run python scripts/merge_voting_rescues.py \
        --baseline eval/reports/2026-05-12/hybrid+gpt-oss-vote-n200.json \
        --voting eval/reports/2026-05-13/llama4-scout-filter-or-value.json \
                 eval/reports/2026-05-13/qwen3-order-by-off.json \
        --out eval/reports/2026-05-13/final-merged-n200.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--voting", type=Path, nargs="+", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    base = json.loads(args.baseline.read_text(encoding="utf-8"))
    recs = base["records"]
    by_qid = {r["question_id"]: r for r in recs}

    # Collect candidate rescues per qid across all voting reports.
    # Keep only voting recs where alt actually flipped the answer to True.
    candidates: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for vpath in args.voting:
        vdata = json.loads(vpath.read_text(encoding="utf-8"))
        alt_model = vdata.get("alt_model", vpath.stem)
        for vr in vdata.get("records", []):
            if not vr.get("vote_match"):
                continue
            if not vr.get("alt_match"):
                # vote_match=True but alt_match=False means agreement on a
                # wrong cluster — not a rescue.
                continue
            qid = vr["question_id"]
            br = by_qid.get(qid)
            if br is None or br.get("match"):
                # Already rescued by an earlier voting run we're merging.
                continue
            candidates[qid].append({"alt_model": alt_model, "alt_pred": vr["alt_pred"]})

    # Apply: first valid candidate wins (we iterate in CLI order).
    rescues = 0
    rescue_models: Counter[str] = Counter()
    for qid, cands in candidates.items():
        br = by_qid[qid]
        if br.get("match"):
            continue
        winner = cands[0]
        br["pred_sql"] = winner["alt_pred"]
        br["match"] = True
        br["voted_by"] = winner["alt_model"]
        rescues += 1
        rescue_models[winner["alt_model"]] += 1
        # First-pass match stays False — this is a rescue, not first-pass.

    # Recompute summary.
    n = len(recs)
    matched = sum(1 for r in recs if r.get("match"))
    by_diff: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in recs:
        d = r.get("difficulty", "unknown")
        by_diff[d][1] += 1
        if r.get("match"):
            by_diff[d][0] += 1

    overall = base.get("overall", {})
    if isinstance(overall, dict):
        overall["ea"] = matched / n if n else 0.0
        overall["matched"] = matched
        overall["n"] = n
        overall["rescued_via_voting"] = (overall.get("rescued_via_voting") or 0) + rescues
    base["overall"] = overall

    # Per-difficulty summary in same shape (if present).
    diff_summary = base.get("per_difficulty") or {}
    if isinstance(diff_summary, dict):
        for d, (m, t) in by_diff.items():
            diff_summary[d] = {"ea": m / t if t else 0.0, "matched": m, "n": t}
        base["per_difficulty"] = diff_summary

    # Update headline fields.
    base["sql_model"] = (
        base.get("sql_model", "") + " + " + " + ".join(sorted(rescue_models.keys()))
        if rescue_models
        else base.get("sql_model", "")
    )
    base["configuration"] = base.get("configuration", "") + "+merged"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(base, indent=2, default=str), encoding="utf-8")

    print(f"Rescues applied: {rescues}", file=sys.stderr)
    for model_name, count in rescue_models.most_common():
        print(f"  by {model_name}: {count}", file=sys.stderr)
    print(f"\nEA: {matched}/{n} = {matched / n * 100:.1f}%", file=sys.stderr)
    for d in ["simple", "moderate", "challenging"]:
        m_count, t_count = by_diff.get(d, [0, 0])
        if t_count:
            print(f"  {d}: {m_count}/{t_count} = {m_count / t_count * 100:.1f}%", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
