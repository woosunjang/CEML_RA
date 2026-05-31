"""Helpers for reading SQLite databases from cloud-synced folders."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile


@contextmanager
def sqlite_snapshot(db_path: Path):
    """Copy a SQLite DB and sidecar files to local temp storage for read-only use."""
    with tempfile.TemporaryDirectory(prefix="ceml_sqlite_") as tmp:
        snapshot = Path(tmp) / db_path.name
        shutil.copy2(db_path, snapshot)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{db_path}{suffix}")
            if sidecar.exists():
                shutil.copy2(sidecar, Path(f"{snapshot}{suffix}"))
        yield snapshot
