"""Merge a base eval report with a tier-specific override report.

Produces a hybrid report where chosen-tier records come from the override
file and the rest come from the base. Used for the codestral-default +
Sonnet-on-challenging recipe: codestral handles simple/moderate (where
both models tie) and Sonnet handles challenging (where it gains +3pp).

Usage::

    uv run python scripts/merge_hybrid_eval.py \\
        --base eval/reports/2026-05-11/G_dense_fewshot_verify_retry-verify-retry.json \\
        --override eval/reports/2026-05-11/G_dense_fewshot_verify_retry-sonnet-challenging.json \\
        --override-difficulty challenging \\
        --suffix hybrid-codestral-sonnet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nl_sql.eval.report import load_run_from_json, write_html_report, write_json_report
from nl_sql.eval.runner import EvalRecord, EvalRun, _summarise  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--override", type=Path, required=True)
    parser.add_argument(
        "--override-difficulty",
        choices=["simple", "moderate", "challenging"],
        required=True,
    )
    parser.add_argument("--suffix", default="hybrid")
    parser.add_argument("--reports", type=Path, default=Path("eval/reports"))
    args = parser.parse_args(argv)

    base = load_run_from_json(args.base)
    over = load_run_from_json(args.override)

    over_index = {r.question_id: r for r in over.records}
    swapped = 0
    merged: list[EvalRecord] = []
    for rec in base.records:
        if rec.difficulty == args.override_difficulty and rec.question_id in over_index:
            merged.append(over_index[rec.question_id])
            swapped += 1
        else:
            merged.append(rec)

    sql_models = sorted({base.sql_model, over.sql_model})
    hybrid = _summarise(
        configuration=base.configuration,
        sql_model=" + ".join(sql_models),
        records=merged,
    )

    print(f"[info] base records:     {len(base.records)} ({base.sql_model})")
    print(f"[info] override records: {len(over.records)} ({over.sql_model})")
    print(f"[info] swapped:          {swapped}  ({args.override_difficulty} tier)")
    print(f"[info] merged:           {len(merged)}")
    print()
    print(f"EA (final):    {hybrid.overall.ea * 100:.1f}%")
    for d in ("simple", "moderate", "challenging"):
        slice_ = hybrid.per_difficulty[d]
        print(f"  {d:12} {slice_.ea * 100:.1f}% (n={slice_.n})")

    json_path = write_json_report(hybrid, root=args.reports, name_suffix=args.suffix)

    today_dir = json_path.parent
    siblings: list[EvalRun] = []
    for other in sorted(today_dir.glob("*.json")):
        if other == json_path:
            continue
        try:
            siblings.append(load_run_from_json(other))
        except (KeyError, ValueError):
            continue
    html_path = write_html_report([*siblings, hybrid], root=args.reports)

    print()
    print(f"[json] {json_path}")
    print(f"[html] {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
