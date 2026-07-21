"""Run the autotune cycle end to end: dataset → train → eval → markdown report.

plan_autotune S7. The four steps existed as four hand-typed commands plus a
pile of ad-hoc scoring in `.tmp/`; every re-run risked a different `--n`, a
forgotten `--fewshot-top-k 0` (train/inference mismatch) or a reused
`--report-suffix` silently overwriting the previous run's report. One config
file makes a cycle reproducible and diffable.

Honest about the parts that are not local:

- `train` normally runs on Kaggle/Colab, not here. `mode = "remote"` prints the
  runbook pointer and moves on instead of pretending to train;
- the report never quotes raw EA alone. A run with transport holes scores 37%
  raw on 153 real answers — a number this project has already been burned by.
  Each target reports answered/exceptions alongside EA, and two targets get a
  paired comparison over the questions BOTH answered, which is the only figure
  the S5 verdict may be read from.

    .venv/Scripts/python.exe scripts/autotune/run_cycle.py --dry-run
    .venv/Scripts/python.exe scripts/autotune/run_cycle.py --only eval,report
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "autotune" / "cycle.toml"
STAGES = ("dataset", "train", "eval", "report")
TRAIN_MODES = ("local", "remote", "skip")
EXCEPTION_KIND = "pipeline_exception"


@dataclass(frozen=True, slots=True)
class EvalTarget:
    label: str
    model: str
    suffix: str


@dataclass(frozen=True, slots=True)
class CycleConfig:
    name: str
    dataset_enabled: bool
    train_mode: str
    train_adapter: str
    train_runbook: str
    train_args: tuple[str, ...]
    eval_config: str
    eval_n: int
    eval_seed: int
    provider: str
    fewshot_top_k: int
    explain_provider: str
    reports_root: Path
    targets: tuple[EvalTarget, ...]
    report_out: Path
    anchors: Mapping[str, float]


class ConfigError(ValueError):
    """Config is unusable — raised with the field that is wrong."""


def load_config(path: Path) -> CycleConfig:
    with path.open("rb") as handle:
        raw: dict[str, Any] = tomllib.load(handle)

    dataset = _section(raw, "dataset")
    train = _section(raw, "train")
    evaluation = _section(raw, "eval")
    report = _section(raw, "report")

    mode = str(train.get("mode", "remote"))
    if mode not in TRAIN_MODES:
        raise ConfigError(f"train.mode must be one of {TRAIN_MODES}, got {mode!r}")

    targets = tuple(
        EvalTarget(
            label=str(item["label"]),
            model=str(item["model"]),
            suffix=str(item["suffix"]),
        )
        for item in evaluation.get("targets", [])
    )
    if not targets:
        raise ConfigError("eval.targets is empty — nothing to measure")
    suffixes = [t.suffix for t in targets]
    if len(set(suffixes)) != len(suffixes):
        # Two runs sharing a suffix write the same file and erase each other.
        raise ConfigError(f"eval.targets have duplicate suffixes: {suffixes}")

    return CycleConfig(
        name=str(raw.get("name", "unnamed")),
        dataset_enabled=bool(dataset.get("enabled", False)),
        train_mode=mode,
        train_adapter=str(train.get("adapter", "")),
        train_runbook=str(train.get("runbook", "plan_autotune.md")),
        train_args=tuple(str(a) for a in train.get("args", [])),
        eval_config=str(evaluation.get("config", "E")),
        eval_n=int(evaluation.get("n", 200)),
        eval_seed=int(evaluation.get("seed", 0)),
        provider=str(evaluation.get("provider", "local_vllm")),
        fewshot_top_k=int(evaluation.get("fewshot_top_k", 0)),
        explain_provider=str(evaluation.get("explain_provider", "mistral")),
        reports_root=_resolve(str(evaluation.get("reports_root", "eval/reports"))),
        targets=targets,
        report_out=_resolve(str(report.get("out", ".tmp/autotune_cycle_report.md"))),
        anchors={str(k): float(v) for k, v in dict(report.get("anchors", {})).items()},
    )


def _section(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = raw.get(key, {})
    if not isinstance(value, Mapping):
        raise ConfigError(f"[{key}] must be a table")
    return value


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def dataset_argv() -> list[str]:
    return [sys.executable, str(ROOT / "scripts" / "autotune" / "build_dataset.py")]


def train_argv(cfg: CycleConfig) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "autotune" / "train_qlora.py"),
        *cfg.train_args,
    ]


def eval_argv(cfg: CycleConfig, target: EvalTarget) -> list[str]:
    return [
        sys.executable,
        "-u",
        str(ROOT / "scripts" / "eval_baseline.py"),
        "--config",
        cfg.eval_config,
        "--n",
        str(cfg.eval_n),
        "--seed",
        str(cfg.eval_seed),
        "--provider",
        cfg.provider,
        "--sql-model",
        target.model,
        "--fewshot-top-k",
        str(cfg.fewshot_top_k),
        "--explain-provider",
        cfg.explain_provider,
        "--report-suffix",
        target.suffix,
    ]


def find_report(reports_root: Path, suffix: str) -> Path | None:
    """Newest `eval/reports/<date>/<config>-<suffix>.json`.

    The config part of the filename encodes the flags that were on
    (`E_dense_fewshot_repair`), so it cannot be predicted from the config —
    glob on the suffix, which is the part we control.
    """
    matches = sorted(reports_root.glob(f"*/*-{suffix}.json"), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


@dataclass(frozen=True, slots=True)
class TargetSummary:
    target: EvalTarget
    path: Path
    n: int
    answered: int
    exceptions: int
    ea_raw: float
    ea_answered: float
    validity: float
    per_difficulty: Mapping[str, float]
    matches: Mapping[int, bool]  # question_id → match, answered questions only


def summarise(target: EvalTarget, path: Path) -> TargetSummary:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records: Sequence[Mapping[str, Any]] = payload["records"]
    answered = [r for r in records if r["error_kind"] != EXCEPTION_KIND]
    hits = sum(1 for r in answered if r["match"])
    overall = payload["overall"]
    return TargetSummary(
        target=target,
        path=path,
        n=len(records),
        answered=len(answered),
        exceptions=len(records) - len(answered),
        ea_raw=float(overall["ea"]),
        ea_answered=hits / len(answered) if answered else 0.0,
        validity=float(overall["validity_rate"]),
        per_difficulty=_ea_by_difficulty(answered),
        matches={int(r["question_id"]): bool(r["match"]) for r in answered},
    )


def _ea_by_difficulty(answered: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Per-tier EA over answered questions only.

    Deliberately recomputed instead of read from the report's `per_difficulty`
    block: that one divides by every question in the tier, so on a run with
    holes it mixes "wrong" and "never asked" — the same trap as raw EA. For a
    run with 0 exceptions both agree exactly.
    """
    tiers: dict[str, list[bool]] = {}
    for record in answered:
        tiers.setdefault(str(record["difficulty"]), []).append(bool(record["match"]))
    return {tier: sum(flags) / len(flags) for tier, flags in tiers.items() if flags}


@dataclass(frozen=True, slots=True)
class PairedComparison:
    left: str
    right: str
    n_pairs: int
    left_ea: float
    right_ea: float
    fixed: int  # right wrong → left right
    broke: int  # right right → left wrong
    p_value: float


def compare_paired(left: TargetSummary, right: TargetSummary) -> PairedComparison | None:
    """Compare two runs on the questions BOTH answered.

    Runs through a flaky tunnel have different holes, so their raw EAs are not
    comparable at all. Only the intersection is.
    """
    shared = sorted(set(left.matches) & set(right.matches))
    if not shared:
        return None
    fixed = sum(1 for q in shared if left.matches[q] and not right.matches[q])
    broke = sum(1 for q in shared if right.matches[q] and not left.matches[q])
    return PairedComparison(
        left=left.target.label,
        right=right.target.label,
        n_pairs=len(shared),
        left_ea=sum(left.matches[q] for q in shared) / len(shared),
        right_ea=sum(right.matches[q] for q in shared) / len(shared),
        fixed=fixed,
        broke=broke,
        p_value=mcnemar_exact(fixed, broke),
    )


def mcnemar_exact(fixed: int, broke: int) -> float:
    """Two-sided exact McNemar p-value on the discordant pairs.

    Under H0 each discordant pair is a fair coin, so the count follows
    Binomial(fixed + broke, 0.5). Exact rather than the chi-square
    approximation because these counts are small (24/13 in the v10 cycle).
    """
    total = fixed + broke
    if total == 0:
        return 1.0
    tail = min(fixed, broke)
    cumulative = sum(math.comb(total, k) for k in range(tail + 1))
    return min(1.0, 2.0 * cumulative / (2.0**total))


def render_markdown(cfg: CycleConfig, summaries: Sequence[TargetSummary]) -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Autotune cycle — {cfg.name}",
        "",
        f"Generated {stamp} by `scripts/autotune/run_cycle.py`. "
        f"Config {cfg.eval_config}, n={cfg.eval_n}, seed={cfg.eval_seed}, "
        f"few-shot top-k={cfg.fewshot_top_k}.",
        "",
        "## Runs",
        "",
        "| target | model | answered | exceptions | EA (answered) | EA (raw) | validity |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        lines.append(
            f"| {s.target.label} | `{s.target.model}` | {s.answered}/{s.n} | {s.exceptions} | "
            f"{s.ea_answered * 100:.1f}% | {s.ea_raw * 100:.1f}% | {s.validity * 100:.1f}% |"
        )
    lines += [
        "",
        "`EA (raw)` counts every unanswered question as wrong, so it is only "
        "meaningful when `exceptions` is 0. Read `EA (answered)` otherwise, and "
        "the paired table below before that.",
        "",
        "## Per difficulty (EA over answered)",
        "",
        "| target | simple | moderate | challenging |",
        "|---|---:|---:|---:|",
    ]
    for s in summaries:
        cells = " | ".join(
            f"{s.per_difficulty.get(tier, 0.0) * 100:.1f}%"
            for tier in ("simple", "moderate", "challenging")
        )
        lines.append(f"| {s.target.label} | {cells} |")
    lines += [
        "",
        "Each row is over that run's own answered set. When the runs have "
        "different holes those denominators differ — compare targets through "
        "the paired table, not this one.",
    ]

    if len(summaries) >= 2:
        paired = compare_paired(summaries[0], summaries[1])
        if paired is not None:
            lines += [
                "",
                "## Paired comparison",
                "",
                f"On the {paired.n_pairs} questions both runs answered:",
                "",
                f"- **{paired.left}** {paired.left_ea * 100:.1f}% vs "
                f"**{paired.right}** {paired.right_ea * 100:.1f}% "
                f"(**{(paired.left_ea - paired.right_ea) * 100:+.1f} pp**)",
                f"- discordant: fixed {paired.fixed} / broke {paired.broke}, "
                f"McNemar exact p = {paired.p_value:.3f}",
            ]

    if cfg.anchors:
        lines += ["", "## Anchors", ""]
        lines += [f"- {name}: {value:.1f}%" for name, value in cfg.anchors.items()]

    lines += ["", "## Reports", ""]
    lines += [f"- {s.target.label}: `{s.path.relative_to(ROOT).as_posix()}`" for s in summaries]
    return "\n".join(lines) + "\n"


def _run(argv: Sequence[str], *, dry_run: bool) -> int:
    printable = " ".join(argv)
    if dry_run:
        print(f"    would run: {printable}")
        return 0
    print(f"    running: {printable}")
    # Fixed argv built above, never a shell string.
    return subprocess.call(list(argv), cwd=ROOT)


def stage_dataset(cfg: CycleConfig, *, dry_run: bool) -> int:
    if not cfg.dataset_enabled:
        print("    skipped: dataset.enabled = false (reusing data/autotune/*.jsonl)")
        return 0
    return _run(dataset_argv(), dry_run=dry_run)


def stage_train(cfg: CycleConfig, *, dry_run: bool) -> int:
    if cfg.train_mode == "skip":
        print(f"    skipped: train.mode = skip (adapter {cfg.train_adapter or '?'})")
        return 0
    if cfg.train_mode == "remote":
        print("    remote: training runs on Kaggle/Colab, not here.")
        print(f"    runbook: {cfg.train_runbook}")
        print(f"    expects the adapter at: {cfg.train_adapter or '(unset)'}")
        return 0
    return _run(train_argv(cfg), dry_run=dry_run)


def stage_eval(cfg: CycleConfig, *, dry_run: bool) -> int:
    for target in cfg.targets:
        print(f"  target {target.label} → suffix {target.suffix}")
        code = _run(eval_argv(cfg, target), dry_run=dry_run)
        if code != 0:
            print(f"    eval failed for {target.label} (exit {code})")
            return code
    return 0


def stage_report(cfg: CycleConfig, *, dry_run: bool) -> int:
    summaries: list[TargetSummary] = []
    for target in cfg.targets:
        path = find_report(cfg.reports_root, target.suffix)
        if path is None:
            print(f"    no report yet for {target.label} (suffix {target.suffix})")
            continue
        print(f"    {target.label}: {path.relative_to(ROOT).as_posix()}")
        if not dry_run:
            summaries.append(summarise(target, path))
    if dry_run:
        print(f"    would write: {cfg.report_out.relative_to(ROOT).as_posix()}")
        return 0
    if not summaries:
        print("    nothing to report — run the eval stage first")
        return 1
    cfg.report_out.parent.mkdir(parents=True, exist_ok=True)
    cfg.report_out.write_text(render_markdown(cfg, summaries), encoding="utf-8")
    print(f"    wrote {cfg.report_out.relative_to(ROOT).as_posix()}")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="cycle config (TOML)")
    parser.add_argument(
        "--only",
        default="",
        help=f"comma-separated subset of stages to run (of {','.join(STAGES)})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the resolved commands and exit without running anything",
    )
    return parser.parse_args(argv)


def selected_stages(only: str) -> tuple[str, ...]:
    if not only.strip():
        return STAGES
    wanted = [s.strip() for s in only.split(",") if s.strip()]
    unknown = [s for s in wanted if s not in STAGES]
    if unknown:
        raise ConfigError(f"unknown stage(s): {unknown}; known: {list(STAGES)}")
    return tuple(s for s in STAGES if s in wanted)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        cfg = load_config(Path(args.config))
        stages = selected_stages(args.only)
    except (ConfigError, KeyError, OSError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    mode = "DRY RUN" if args.dry_run else "RUN"
    print(f"[{mode}] cycle {cfg.name} — stages: {', '.join(stages)}")
    runners = {
        "dataset": stage_dataset,
        "train": stage_train,
        "eval": stage_eval,
        "report": stage_report,
    }
    for stage in stages:
        print(f"\n== {stage} ==")
        code = runners[stage](cfg, dry_run=args.dry_run)
        if code != 0:
            print(f"\nstage {stage} failed (exit {code})", file=sys.stderr)
            return code
    print("\ndone")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
