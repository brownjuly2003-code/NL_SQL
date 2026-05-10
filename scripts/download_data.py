"""Download datasets that back target databases.

Run examples (idempotent — already-present files are skipped):
    uv run python scripts/download_data.py chinook
    uv run python scripts/download_data.py bird-mini-dev
    uv run python scripts/download_data.py all

Outputs land under data/ which is gitignored. Each downloader records a
SHA-256 next to the file so eval reports can pin dataset checksums.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Final

import requests

DATA_ROOT: Final = Path("data")

CHINOOK_URL: Final = (
    "https://github.com/lerocha/chinook-database/raw/master/"
    "ChinookDatabase/DataSources/Chinook_Sqlite.sqlite"
)
CHINOOK_FILENAME: Final = "Chinook.sqlite"

# BIRD Mini-Dev moved off the GitHub repo and is now hosted on HuggingFace +
# Google Drive. Direct fetch via the HF dataset API requires `huggingface_hub`
# auth-aware download or a Google Drive resumable cookie dance. Implementing
# that properly is its own task (see docs/SESSION_HANDOFF.md "next session" §2).
BIRD_MINI_DEV_URL: Final = (
    "https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip"
)
BIRD_MINI_DEV_HF_REPO: Final = "birdsql/bird_mini_dev"


def _download_file(url: str, dest: Path, *, chunk_size: int = 1 << 15) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"[skip] {dest} already present ({dest.stat().st_size:,} bytes)")
        return dest
    print(f"[download] {url} → {dest}")
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    fh.write(chunk)
    print(f"[done] {dest} ({dest.stat().st_size:,} bytes)")
    return dest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_checksum(path: Path) -> None:
    sha = _sha256(path)
    sums = path.with_suffix(path.suffix + ".sha256")
    sums.write_text(f"{sha}  {path.name}\n", encoding="utf-8")
    print(f"[checksum] {sums}")


def download_chinook() -> None:
    target_dir = DATA_ROOT / "chinook"
    dest = target_dir / CHINOOK_FILENAME
    _download_file(CHINOOK_URL, dest)
    _write_checksum(dest)


def download_bird_mini_dev() -> None:
    target_dir = DATA_ROOT / "bird_mini_dev"
    target_dir.mkdir(parents=True, exist_ok=True)
    archive = target_dir / "minidev.zip"
    _download_file(BIRD_MINI_DEV_URL, archive)
    _write_checksum(archive)
    print(f"[unzip] {archive} → {target_dir}")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(target_dir)
    print(f"[done] {target_dir}")


DOWNLOADERS: Final[dict[str, Callable[[], None]]] = {
    "chinook": download_chinook,
    "bird-mini-dev": download_bird_mini_dev,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "datasets",
        nargs="+",
        choices=[*DOWNLOADERS, "all"],
        help="Which dataset(s) to download.",
    )
    args = parser.parse_args()
    targets = list(DOWNLOADERS) if "all" in args.datasets else args.datasets
    for name in targets:
        DOWNLOADERS[name]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
