"""CI gate: no NEW use of the raw `compare_results` comparator in scripts/.

`nl_sql.eval.metrics.execution_accuracy.compare_results` is row-level: it scores
`pred_rows=[]` as a match against `gold_rows=[]` regardless of whether the pred
actually executed. Nine voting/rescore scripts that relied on it are frozen in
`scripts/archive/` (see scripts/archive/README.md, the "qid 518" class). Any NEW
script that merges or blesses predictions must use `safe_compare_pred`, which
short-circuits execution failures.

This gate parses each top-level script under scripts/ with `ast` (so a mention in
a docstring/comment doesn't trip it) and fails if a non-exempt file imports or
calls `compare_results`.

    python scripts/check_no_raw_compare.py            # scan the tree, exit 1 on offender
    python scripts/check_no_raw_compare.py --self-test  # prove the detector works
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
BANNED_NAME = "compare_results"

# Files allowed to keep using the raw comparator, with the reason they are safe.
# eval_demo.py is a local demo that prints a single run's matches — it does not
# merge/rescore votes, so the empty-gold false-positive cannot corrupt a reported
# metric. It is intentionally NOT frozen (audit 2026-07-11).
ALLOWLIST = {"eval_demo.py"}


def _uses_raw_compare(source: str) -> bool:
    """True if the module imports or calls `compare_results` (AST, not text)."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == BANNED_NAME for alias in node.names):
                return True
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == BANNED_NAME:
                return True
            if isinstance(func, ast.Attribute) and func.attr == BANNED_NAME:
                return True
    return False


def find_offenders(scripts_dir: Path = SCRIPTS_DIR) -> list[Path]:
    """Top-level scripts (excluding scripts/archive/ and the allowlist) using it."""
    offenders: list[Path] = []
    for path in sorted(scripts_dir.glob("*.py")):
        if path.name in ALLOWLIST or path.name == Path(__file__).name:
            continue
        if _uses_raw_compare(path.read_text(encoding="utf-8")):
            offenders.append(path)
    return offenders


def _self_test() -> int:
    raw = "from nl_sql.eval.metrics.execution_accuracy import compare_results\nx = compare_results([], [])\n"
    safe = "from nl_sql.eval.metrics.execution_accuracy import safe_compare_pred\n"
    docstring_only = '"""mentions compare_results in prose only."""\nimport os\n'
    assert _uses_raw_compare(raw), "detector missed a raw import+call"
    assert not _uses_raw_compare(safe), "detector false-positived on safe_compare_pred"
    assert not _uses_raw_compare(docstring_only), "detector tripped on a docstring mention"
    print("self-test OK: detector flags raw use, ignores safe use and docstrings")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="verify the detector, then exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    offenders = find_offenders()
    if offenders:
        print("Raw compare_results used in non-archived scripts (use safe_compare_pred):")
        for path in offenders:
            print(f"  - {path.relative_to(SCRIPTS_DIR.parent)}")
        print("If a new script genuinely merges predictions, route it through safe_compare_pred.")
        return 1
    print("OK: no raw compare_results outside scripts/archive/ + allowlist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
