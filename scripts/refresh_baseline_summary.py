"""Regenerate `overall.ea` / `overall.matched` headers in merged baseline reports.

Codex audit 2026-05-25 #5: after the `safe_compare_pred` fix patched per-record
`match` fields surgically, the top-level summary in every v22-v29 merged JSON
remained stale (each +1 inflated). This walks a list of report paths and
rewrites `overall.ea` + `overall.matched` from the truthful `records[]` array.

Idempotent: running twice leaves identical bytes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def refresh(report_path: Path) -> tuple[bool, str]:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    records = data.get("records")
    if not isinstance(records, list) or not records:
        return False, "no records[]"
    overall = data.setdefault("overall", {})
    n = len(records)
    matched = sum(1 for r in records if r.get("match") is True)
    ea_new = round(matched / n, 4) if n else 0.0
    stored_matched = overall.get("matched")
    stored_ea = overall.get("ea")
    if stored_matched == matched and stored_ea is not None and abs(stored_ea - ea_new) < 1e-6:
        return False, f"already consistent ({matched}/{n}={ea_new})"
    overall["matched"] = matched
    overall["ea"] = ea_new
    overall["n"] = n
    report_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return True, f"{stored_matched}/{stored_ea} -> {matched}/{ea_new}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh stale overall.ea/matched in baseline reports"
    )
    parser.add_argument("paths", nargs="+", type=Path, help="merged baseline JSON paths")
    args = parser.parse_args(argv)

    changed = 0
    for p in args.paths:
        if not p.exists():
            print(f"SKIP {p} (missing)")
            continue
        did, info = refresh(p)
        marker = "FIX " if did else "OK  "
        changed += int(did)
        print(f"{marker}{p}: {info}")
    print(f"\n{changed} file(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
