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
import shutil
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

# BIRD Mini-Dev: the canonical bundle (questions + 11 SQLite DBs) lives on Google
# Drive. The official Aliyun mirror is firewalled in some regions; the HuggingFace
# `birdsql/bird_mini_dev` repo only carries the questions JSON, not the SQLite
# databases, so we cannot use snapshot_download here. gdown handles GD's confirm
# token redirect for >100 MB files.
BIRD_MINI_DEV_GDRIVE_ID: Final = "13VLWIwpw5E3d5DUkMvzw7hvHE67a4XkG"
BIRD_MINI_DEV_ARCHIVE: Final = "minidev.zip"
BIRD_MINI_DEV_INNER_PREFIX: Final = "minidev/"  # zip wraps everything one level deep


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
    minidev_dir = target_dir / "MINIDEV"
    if minidev_dir.is_dir() and (minidev_dir / "dev_databases").is_dir():
        print(f"[skip] {minidev_dir} already populated")
        return

    archive = target_dir / BIRD_MINI_DEV_ARCHIVE
    if not archive.exists():
        import gdown

        url = f"https://drive.google.com/uc?id={BIRD_MINI_DEV_GDRIVE_ID}"
        print(f"[gdown] {url} → {archive}")
        gdown.download(url, str(archive), quiet=False)
    else:
        print(f"[skip] {archive} already downloaded ({archive.stat().st_size:,} bytes)")
    _write_checksum(archive)

    print(f"[unzip] {archive} → {target_dir} (stripping '{BIRD_MINI_DEV_INNER_PREFIX}', skipping __MACOSX)")
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            name = member.filename
            if name.startswith("__MACOSX/") or "/._" in name or name.endswith("/.DS_Store"):
                continue
            if not name.startswith(BIRD_MINI_DEV_INNER_PREFIX):
                continue
            stripped = name[len(BIRD_MINI_DEV_INNER_PREFIX):]
            if not stripped:
                continue
            dest = target_dir / stripped
            if member.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, dest.open("wb") as fh:
                shutil.copyfileobj(src, fh)
    print(f"[done] {minidev_dir}")


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
