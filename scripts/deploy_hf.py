#!/usr/bin/env python
"""Clean-clone-safe deploy of the tracked tree to the Hugging Face Space.

Uploads **exactly** the filtered ``git ls-files`` set (never the working tree),
scans every publish file for tunnel-client markers, sets the Space secret from
the process environment only, and prunes remote strays. Requires an explicit
``--apply`` for any remote mutation.

Usage::

    python scripts/deploy_hf.py --self-test   # local safety gate, no network
    python scripts/deploy_hf.py --dry-run     # print upload set, no network
    python scripts/deploy_hf.py --apply       # mutate the Space (needs env secrets)

Environment (``--apply`` only):

    HF_TOKEN          Hugging Face write token (``HfApi`` auth)
    MISTRAL_API_KEY   Space secret value (never read from a local file path)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ID = "liovina/nl-sql"
SPACE_SDK = "docker"
APP_PORT = 7860
SHORT_DESCRIPTION = "NL to SQL RU/EN — 61.5% BIRD Mini-Dev, reproducible"

# Paths that ship in the GitHub repo but must not land on the Space host.
EXCLUDE_PREFIXES: tuple[str, ...] = (
    "tests/",
    ".github/",
    "docs/research/",
    "reviews/",
    "eval/baselines/",
    "eval/reports/",
    "scripts/autotune/",
)

# Files that belong in the source repository but not on the app-hosting Space.
# The README is replaced by an HF-frontmatter version. Deployment tooling and
# closure metadata carry the tunnel-marker terms they document, so publishing
# them would make the byte-level safety gate block its own implementation.
PUBLISH_EXCLUDE_FILES: frozenset[str] = frozenset(
    {
        "README.md",
        "DEPLOY.md",
        "docs/PROJECT_CLOSURE.md",
        "scripts/deploy_hf.py",
    }
)

# Always part of the expected remote tree (generated or tracked).
GENERATED_REMOTE_README = "README.md"
TRACKED_DOCKERFILE = "Dockerfile"
TRACKED_GITATTRIBUTES = ".gitattributes"

# Case-insensitive tunnel markers (HF abuse-handler: rule Cloudflared, etc.).
TUNNEL_MARKERS: tuple[bytes, ...] = (
    b"cloudflared",
    b"trycloudflare",
    b"ngrok",
    b"localtunnel",
    b"bore.pub",
    b"serveo.net",
    b"pinggy",
    b"loca.lt",
)
_TUNNEL_RE = re.compile(
    b"|".join(re.escape(m) for m in TUNNEL_MARKERS),
    re.IGNORECASE,
)
# Overlap so a marker split across two read() calls is still visible.
_CHUNK_SIZE = 64 * 1024
_CHUNK_OVERLAP = max(len(m) for m in TUNNEL_MARKERS)


# ---------------------------------------------------------------------------
# Repo root / tracked files
# ---------------------------------------------------------------------------


def repo_root() -> Path:
    """Repository root derived from this script's path (clean-clone safe)."""
    return Path(__file__).resolve().parents[1]


def _hygiene_classify(path: str) -> str | None:
    """Delegate to the hygiene detector (works as package or as a script)."""
    try:
        from scripts.check_repo_hygiene import classify
    except ImportError:  # running as ``python scripts/deploy_hf.py``
        from check_repo_hygiene import classify  # type: ignore[import-not-found,no-redef]

    return classify(path)


def tracked_files(*, root: Path | None = None) -> list[str]:
    """Return repo-relative tracked paths via ``git ls-files`` (UTF-8, unquoted)."""
    cwd = root if root is not None else repo_root()
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    return [line for line in result.stdout.splitlines() if line]


def is_excluded_prefix(path: str) -> bool:
    """True when *path* falls under a publish-exclude prefix."""
    return any(path == p.rstrip("/") or path.startswith(p) for p in EXCLUDE_PREFIXES)


def filter_publish_paths(paths: Iterable[str]) -> list[str]:
    """Apply prefix, hygiene, and app-host file exclusions."""
    out: list[str] = []
    for path in paths:
        if is_excluded_prefix(path):
            continue
        if path in PUBLISH_EXCLUDE_FILES:
            continue
        if _hygiene_classify(path) is not None:
            continue
        out.append(path)
    return out


def publish_paths(*, root: Path | None = None) -> list[str]:
    """Tracked files that would be bulk-uploaded to the Space."""
    return filter_publish_paths(tracked_files(root=root))


def expected_remote_paths(
    publish: Sequence[str],
    *,
    root: Path | None = None,
    has_gitattributes: bool | None = None,
) -> set[str]:
    """Remote paths that should remain after upload + prune.

    Always includes the generated frontmatter ``README.md`` and the tracked
    ``Dockerfile``. Includes ``.gitattributes`` when present in the tree.
    """
    base = repo_root() if root is None else root
    remote = set(publish)
    remote.add(GENERATED_REMOTE_README)
    remote.add(TRACKED_DOCKERFILE)
    if has_gitattributes is None:
        has_gitattributes = (base / TRACKED_GITATTRIBUTES).is_file() or (
            TRACKED_GITATTRIBUTES in remote
        )
    if has_gitattributes:
        remote.add(TRACKED_GITATTRIBUTES)
    return remote


# ---------------------------------------------------------------------------
# Tunnel scan
# ---------------------------------------------------------------------------


def file_has_tunnel_marker(path: Path) -> bool:
    """Scan *path* in binary chunks with overlap for any tunnel marker."""
    prev = b""
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_CHUNK_SIZE)
            if not chunk and not prev:
                return False
            if not chunk:
                return _TUNNEL_RE.search(prev) is not None
            data = prev + chunk
            if _TUNNEL_RE.search(data) is not None:
                return True
            prev = data[-_CHUNK_OVERLAP:] if len(data) >= _CHUNK_OVERLAP else data


def tunnel_hits(paths: Iterable[str], *, root: Path | None = None) -> list[str]:
    """Return publish-set paths whose bytes carry a tunnel-client marker."""
    base = repo_root() if root is None else root
    hits: list[str] = []
    for rel in paths:
        full = base / rel
        if not full.is_file():
            continue
        if file_has_tunnel_marker(full):
            hits.append(rel)
    return hits


# ---------------------------------------------------------------------------
# HF README frontmatter
# ---------------------------------------------------------------------------


def hf_readme_frontmatter() -> str:
    """YAML frontmatter for a Docker HF Space (port 7860, MIT, 61.5%)."""
    return (
        "---\n"
        "title: NL→SQL Assistant\n"
        "emoji: 🗃️\n"
        "colorFrom: indigo\n"
        "colorTo: purple\n"
        f"sdk: {SPACE_SDK}\n"
        f"app_port: {APP_PORT}\n"
        "license: mit\n"
        f"short_description: {SHORT_DESCRIPTION}\n"
        "---\n"
    )


def build_hf_readme(*, root: Path | None = None) -> str:
    """Frontmatter + a Space-safe repository README body."""
    base = repo_root() if root is None else root
    body = (base / "README.md").read_text(encoding="utf-8")
    sanitized_body = _TUNNEL_RE.sub(
        b"tunnel-client rule",
        body.encode("utf-8"),
    ).decode("utf-8")
    return hf_readme_frontmatter() + "\n" + sanitized_body


# ---------------------------------------------------------------------------
# Local safety gate
# ---------------------------------------------------------------------------


def run_safety_gate(*, root: Path | None = None) -> list[str]:
    """Return human-readable failure strings; empty list means the gate passed."""
    base = repo_root() if root is None else root
    failures: list[str] = []

    candidates = tracked_files(root=base)
    publish = filter_publish_paths(candidates)

    required_tracked = {TRACKED_DOCKERFILE, "scripts/deploy_hf.py"}
    missing_required = sorted(required_tracked - set(candidates))
    if missing_required:
        failures.append(f"required deploy files are not tracked: {missing_required}")

    for prefix in EXCLUDE_PREFIXES:
        leaked = [p for p in publish if p == prefix.rstrip("/") or p.startswith(prefix)]
        if leaked:
            failures.append(f"exclude prefix {prefix!r} leaked into publish set: {leaked[:3]}")

    if "README.md" in publish:
        failures.append("repository README.md must not be bulk-uploaded")

    # Scanner must not be vacuous: a planted marker in a temp file is caught.
    with tempfile.TemporaryDirectory(dir=base) as tmp:
        probe = Path(tmp) / "_tunnel_probe.bin"
        # Marker deliberately split-friendly; full string present.
        probe.write_bytes(b"x" * 8 + b"cloudflared" + b"y" * 8)
        probe_rel = probe.relative_to(base).as_posix()
        if not tunnel_hits([probe_rel], root=base):
            failures.append("tunnel scanner is vacuous: it missed a planted cloudflared marker")

    leaks = tunnel_hits(publish, root=base)
    if leaks:
        failures.append(f"publish set ships a tunnel client (HF abuse rule): {leaks}")

    generated_readme = build_hf_readme(root=base).encode("utf-8")
    if _TUNNEL_RE.search(generated_readme) is not None:
        failures.append("generated HF README still carries a tunnel-client marker")

    if TRACKED_DOCKERFILE not in expected_remote_paths(publish, root=base):
        failures.append("expected remote set must include Dockerfile")

    return failures


def self_test(*, root: Path | None = None) -> int:
    """Local, credential-free, no-network safety gate."""
    failures = run_safety_gate(root=root)
    if failures:
        print("[deploy-hf] self-test FAILED:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1
    publish = publish_paths(root=root)
    remote = expected_remote_paths(publish, root=root)
    print(
        f"[deploy-hf] self-test passed "
        f"({len(publish)} publish file(s), {len(remote)} expected remote path(s))."
    )
    return 0


def dry_run(*, root: Path | None = None) -> int:
    """Print the upload set and local gate status without touching the network."""
    base = repo_root() if root is None else root
    publish = publish_paths(root=base)
    remote = expected_remote_paths(publish, root=base)
    print(f"[deploy-hf] dry-run: {len(publish)} file(s) would be bulk-uploaded")
    for path in publish:
        print(f"  + {path}")
    print(f"[deploy-hf] dry-run: expected remote set size = {len(remote)}")
    print(f"  (includes generated {GENERATED_REMOTE_README!r})")
    failures = run_safety_gate(root=base)
    if failures:
        print("[deploy-hf] dry-run: safety gate FAILED:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print("[deploy-hf] dry-run: safety gate OK (no network, no credentials used).")
    return 0


# ---------------------------------------------------------------------------
# Remote (lazy huggingface_hub)
# ---------------------------------------------------------------------------


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise RuntimeError(
            f"{name} must be set in the process environment for --apply "
            "(never read from a local credential file path)."
        )
    return value


def _get_hf_api() -> Any:
    """Lazy-import HfApi; authenticate via ``HF_TOKEN`` only."""
    from huggingface_hub import HfApi

    token = _require_env("HF_TOKEN")
    return HfApi(token=token)


def apply_deploy(*, root: Path | None = None) -> int:
    """Run the local gate, then mutate the Space. Requires env secrets."""
    base = repo_root() if root is None else root
    failures = run_safety_gate(root=base)
    if failures:
        print("[deploy-hf] --apply aborted: local safety gate failed:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    mistral_key = _require_env("MISTRAL_API_KEY")
    # Token consumed inside _get_hf_api; never printed.
    api = _get_hf_api()

    from huggingface_hub import CommitOperationDelete

    publish = publish_paths(root=base)
    expected = expected_remote_paths(publish, root=base)

    if api.repo_exists(repo_id=REPO_ID, repo_type="space"):
        print(f"[deploy-hf] Space {REPO_ID} already exists — skipping create_repo.")
    else:
        print(f"[deploy-hf] Creating Space {REPO_ID} (sdk={SPACE_SDK})…")
        api.create_repo(
            repo_id=REPO_ID,
            repo_type="space",
            space_sdk=SPACE_SDK,
            exist_ok=True,
        )

    print("[deploy-hf] Setting Space secret MISTRAL_API_KEY (value not printed)…")
    api.add_space_secret(repo_id=REPO_ID, key="MISTRAL_API_KEY", value=mistral_key)

    # Stage the filtered tracked set into a temp tree and upload as a folder.
    with tempfile.TemporaryDirectory(prefix="nl_sql_hf_upload_") as tmp:
        stage = Path(tmp)
        for rel in publish:
            src = base / rel
            dest = stage / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
        print(f"[deploy-hf] Uploading {len(publish)} filtered tracked file(s)…")
        api.upload_folder(
            folder_path=str(stage),
            repo_id=REPO_ID,
            repo_type="space",
            commit_message="Deploy filtered tracked tree",
        )

    print("[deploy-hf] Uploading generated README.md (HF frontmatter)…")
    api.upload_file(
        path_or_fileobj=build_hf_readme(root=base).encode("utf-8"),
        path_in_repo=GENERATED_REMOTE_README,
        repo_id=REPO_ID,
        repo_type="space",
        commit_message="HF Space README frontmatter",
    )

    remote = set(api.list_repo_files(REPO_ID, repo_type="space"))
    strays = sorted(remote - expected)
    if strays:
        print(f"[deploy-hf] Pruning {len(strays)} remote stray(s)…")
        ops = [CommitOperationDelete(path_in_repo=p) for p in strays]
        api.create_commit(
            repo_id=REPO_ID,
            repo_type="space",
            operations=ops,
            commit_message="Prune remote files not in filtered tracked set",
        )
    else:
        print("[deploy-hf] No remote strays to prune.")

    space_url = f"https://huggingface.co/spaces/{REPO_ID}"
    direct_url = f"https://{REPO_ID.replace('/', '-')}.hf.space"
    print(f"[deploy-hf] Done. Dashboard: {space_url}")
    print(f"[deploy-hf] Direct:    {direct_url}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--self-test",
        action="store_true",
        help="Run the local safety gate (no network, no credentials).",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the filtered upload set and run the gate (no network).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Mutate the HF Space (requires HF_TOKEN and MISTRAL_API_KEY in env).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.dry_run:
        return dry_run()
    if args.apply:
        try:
            return apply_deploy()
        except RuntimeError as exc:
            print(f"[deploy-hf] {exc}", file=sys.stderr)
            return 1

    # No flags: refuse mutation, print usage, nonzero — no network.
    parser.print_help()
    print(
        "\n[deploy-hf] Refusing to run without an explicit mode. "
        "Use --self-test, --dry-run, or --apply.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
