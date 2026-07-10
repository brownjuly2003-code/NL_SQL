#!/usr/bin/env python
"""Repo hygiene gate — keep internal working notes out of the public tree.

The 2026-07-10 cleanup untracked the internal audits (root ``audit_*.md``) and
the session handoff (``docs/NEXT_SESSION.md``) that had been living in the
public repository (and, via the working-tree deploy, on the public HF Space).

All of these are ignored via ``.gitignore`` now, but ``git add -f`` or a future
``.gitignore`` edit could silently re-introduce them. This gate fails CI the
moment any such path shows up in ``git ls-files``, so the cleanup can't rot.
The HF Space is guarded separately: ``.deploy_hf.py`` uploads only tracked
files and prunes strays from the Space.

Usage::

    python scripts/check_repo_hygiene.py             # scan tracked files, exit 1 on violations
    python scripts/check_repo_hygiene.py --self-test # prove the detector works
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

_DATE_NOTE = re.compile(r"^\d{2}_\d{2}_\d{2}\.md$")  # e.g. 27_05_26.md


def classify(path: str) -> str | None:
    """Return a human-readable reason if *path* is forbidden, else ``None``.

    ``path`` is a forward-slash repo-relative path exactly as ``git ls-files``
    emits it.
    """
    if "/" not in path:
        if path.startswith("audit_") and path.endswith(".md"):
            return "internal root-level audit report"
        if path.startswith("plan_") and path.endswith(".md"):
            return "internal root-level planning note"
        if path.startswith("_ref_"):
            return "internal root-level reference scratch"
        if _DATE_NOTE.match(path):
            return "internal root-level dated session note"
    if path == "docs/NEXT_SESSION.md":
        return "internal session handoff"
    if path == ".claude" or path.startswith(".claude/"):
        return "assistant workspace directory"
    if path == "scratchpad" or path.startswith("scratchpad/"):
        return "local scratch directory"
    return None


def find_violations(paths: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for path in paths:
        reason = classify(path)
        if reason is not None:
            out.append((path, reason))
    return out


def tracked_files() -> list[str]:
    # core.quotepath=false → non-ASCII paths (e.g. cyrillic note names) come
    # through as raw UTF-8 instead of octal-escaped, quoted strings.
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    return [line for line in result.stdout.splitlines() if line]


def self_test() -> int:
    """Prove the detector flags forbidden paths and leaves legitimate ones alone."""
    must_flag = [
        "audit_codex_12_05_26.md",
        "audit_kimi_25_05_26.md",
        "plan_for_pres.md",
        "_ref_presentation3.html",
        "27_05_26.md",
        "docs/NEXT_SESSION.md",
        ".claude/settings.json",
        "scratchpad/tmp.py",
    ]
    must_pass = [
        "README.md",
        "docs/SESSION_HANDOFF.md",  # referenced from README; removal is a separate decision
        "docs/v18_residue_audit.md",  # part of the public eval-methodology doc web
        "scripts/audit_rescore.py",  # product code, not a markdown audit note
        "src/nl_sql/agent/nodes/plan_query.py",  # product code, not a planning note
        "scripts/check_repo_hygiene.py",
        "eval/reports/2026-05-11/G_planner-moderate-n99.json",
    ]
    failures: list[str] = []
    for path in must_flag:
        if classify(path) is None:
            failures.append(f"FAILED to flag forbidden path: {path!r}")
    for path in must_pass:
        reason = classify(path)
        if reason is not None:
            failures.append(f"FALSE POSITIVE on legitimate path: {path!r} -> {reason}")
    if failures:
        print("[repo-hygiene] self-test FAILED:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"[repo-hygiene] self-test passed ({len(must_flag)} flagged, {len(must_pass)} clean).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Verify the detector flags forbidden paths and passes clean ones, then exit.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    paths = tracked_files()
    violations = find_violations(paths)
    if violations:
        print(
            f"[repo-hygiene] FAILED: {len(violations)} internal-only file(s) are tracked in the public repo:",
            file=sys.stderr,
        )
        for path, reason in violations:
            print(f"  {path}  ({reason})", file=sys.stderr)
        print(
            "\nThese were untracked on 2026-07-10 and must stay out of the public tree. "
            "Remove with `git rm --cached <path>` and confirm `.gitignore` still covers them.",
            file=sys.stderr,
        )
        return 1

    print(f"[repo-hygiene] OK: {len(paths)} tracked file(s), no internal-note leaks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
