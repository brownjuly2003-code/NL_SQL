"""Registry of target databases the pipeline knows about.

The default registry is populated from disk: any SQLite file under data/ that
matches a known shape (Chinook, BIRD slices) is auto-registered. Postgres-
backed databases are registered explicitly when the docker-compose stack is
running.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from nl_sql.db.connection import DatabaseSpec, sqlite_url_readonly

DATA_ROOT = Path("data")


@dataclass(slots=True)
class DatabaseRegistry:
    specs: dict[str, DatabaseSpec] = field(default_factory=dict)

    def register(self, spec: DatabaseSpec) -> None:
        self.specs[spec.id] = spec

    def get(self, db_id: str) -> DatabaseSpec:
        if db_id not in self.specs:
            raise KeyError(f"database {db_id!r} not registered. Known: {sorted(self.specs)}")
        return self.specs[db_id]

    def ids(self) -> list[str]:
        return sorted(self.specs)


def get_default_registry(data_root: Path = DATA_ROOT) -> DatabaseRegistry:
    """Build a registry by scanning the data/ tree.

    Resolution order:
    - data/chinook/Chinook.sqlite                                 → id="chinook"
    - data/bird_mini_dev/MINIDEV/dev_databases/<db>/<db>.sqlite   → id=f"bird_{db}"
    """
    registry = DatabaseRegistry()

    chinook_path = data_root / "chinook" / "Chinook.sqlite"
    if chinook_path.exists():
        registry.register(
            DatabaseSpec(
                id="chinook",
                dialect="sqlite",
                url=sqlite_url_readonly(chinook_path),
                description="Chinook music store — invoices, tracks, customers (smoke / sanity).",
            )
        )

    bird_dev_root = data_root / "bird_mini_dev" / "MINIDEV" / "dev_databases"
    if bird_dev_root.is_dir():
        for db_dir in sorted(p for p in bird_dev_root.iterdir() if p.is_dir()):
            sqlite_file = db_dir / f"{db_dir.name}.sqlite"
            if sqlite_file.exists():
                registry.register(
                    DatabaseSpec(
                        id=f"bird_{db_dir.name}",
                        dialect="sqlite",
                        url=sqlite_url_readonly(sqlite_file),
                        description=f"BIRD Mini-Dev / {db_dir.name}.",
                    )
                )

    return registry
