"""Explicit portable snapshot exports for Stage 0 storage boundaries.

This module copies a user-selected file into the durable artifact root and
writes a JSONL manifest row. It does not discover or move live runtime state by
itself.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import socket
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from orchestrator.config import ARTIFACTS_DIR


MANIFEST_RELATIVE_PATH = Path("manifests") / "knowledge_snapshots.jsonl"
SNAPSHOTS_DIR_NAME = "snapshots"
VALID_SNAPSHOT_KINDS = {
    "scout_sqlite",
    "scout_jsonl",
    "orchestrator_sqlite",
    "kg_export",
    "qdrant_snapshot",
    "neo4j_dump",
    "source_archive",
    "other",
}


@dataclass(frozen=True)
class ExportedFile:
    source_path: Path
    destination_path: Path
    size_bytes: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "destination_path": str(self.destination_path),
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class SnapshotExportPlan:
    kind: str
    label: str
    source_path: Path
    destination_path: Path
    artifacts_dir: Path
    manifest_path: Path
    include_sidecars: bool = False
    sidecar_sources: tuple[Path, ...] = field(default_factory=tuple)

    def preview_record(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "dry_run": True,
            "kind": self.kind,
            "label": self.label,
            "source_path": str(self.source_path),
            "destination_path": str(self.destination_path),
            "artifacts_dir": str(self.artifacts_dir),
            "manifest_path": str(self.manifest_path),
            "include_sidecars": self.include_sidecars,
            "sidecar_sources": [str(path) for path in self.sidecar_sources],
        }


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _safe_slug(value: str, fallback: str = "snapshot") -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", value).strip("._-")
    return slug[:80] or fallback


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_sidecars(source_path: Path) -> tuple[Path, ...]:
    sidecars = []
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{source_path}{suffix}")
        if sidecar.exists():
            sidecars.append(sidecar)
    return tuple(sidecars)


def _validate_kind(kind: str) -> str:
    if kind not in VALID_SNAPSHOT_KINDS:
        valid = ", ".join(sorted(VALID_SNAPSHOT_KINDS))
        raise ValueError(f"Unsupported snapshot kind '{kind}'. Valid kinds: {valid}")
    return kind


def plan_snapshot_export(
    source_path: Path,
    *,
    kind: str,
    label: Optional[str] = None,
    artifacts_dir: Path = ARTIFACTS_DIR,
    include_sidecars: bool = False,
    created_at: Optional[str] = None,
) -> SnapshotExportPlan:
    """Build a snapshot export plan without copying files."""
    resolved_source = source_path.expanduser().resolve()
    if not resolved_source.exists():
        raise FileNotFoundError(f"Snapshot source does not exist: {resolved_source}")
    if not resolved_source.is_file():
        raise IsADirectoryError(
            f"Snapshot export expects one explicit file, not a directory: {resolved_source}"
        )

    kind = _validate_kind(kind)
    timestamp = (created_at or _utc_now()).replace(":", "").replace("-", "")
    timestamp = timestamp.replace("Z", "Z")
    safe_label = _safe_slug(label or resolved_source.stem)
    file_name = f"{timestamp}_{safe_label}_{resolved_source.name}"

    resolved_artifacts = artifacts_dir.expanduser().resolve()
    destination = resolved_artifacts / SNAPSHOTS_DIR_NAME / kind / file_name
    manifest = resolved_artifacts / MANIFEST_RELATIVE_PATH

    sidecars: tuple[Path, ...] = ()
    if include_sidecars:
        sidecars = _sqlite_sidecars(resolved_source)

    return SnapshotExportPlan(
        kind=kind,
        label=safe_label,
        source_path=resolved_source,
        destination_path=destination,
        artifacts_dir=resolved_artifacts,
        manifest_path=manifest,
        include_sidecars=include_sidecars,
        sidecar_sources=sidecars,
    )


def _copy_file(source: Path, destination: Path) -> ExportedFile:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return ExportedFile(
        source_path=source,
        destination_path=destination,
        size_bytes=destination.stat().st_size,
        sha256=sha256_file(destination),
    )


def _sidecar_destination(plan: SnapshotExportPlan, sidecar: Path) -> Path:
    suffix = sidecar.name.removeprefix(plan.source_path.name)
    return Path(f"{plan.destination_path}{suffix}")


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def execute_snapshot_export(
    plan: SnapshotExportPlan,
    *,
    actor: str = "manual",
    note: str = "",
) -> dict[str, Any]:
    """Copy the planned file into ARTIFACTS_DIR and append a manifest row."""
    exported_main = _copy_file(plan.source_path, plan.destination_path)
    sidecars = [
        _copy_file(sidecar, _sidecar_destination(plan, sidecar))
        for sidecar in plan.sidecar_sources
    ]

    record = {
        "schema_version": 1,
        "created_at": _utc_now(),
        "host": socket.gethostname(),
        "actor": actor,
        "kind": plan.kind,
        "label": plan.label,
        "source_path": str(plan.source_path),
        "destination_path": str(plan.destination_path),
        "artifacts_dir": str(plan.artifacts_dir),
        "manifest_path": str(plan.manifest_path),
        "note": note,
        "file": exported_main.as_dict(),
        "sidecars": [sidecar.as_dict() for sidecar in sidecars],
    }
    _append_jsonl(plan.manifest_path, record)
    return record


def latest_manifest_records(
    manifest_path: Path,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Read recent manifest records, newest last in the file."""
    if not manifest_path.exists():
        return []
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    records = []
    for line in lines[-limit:]:
        if line.strip():
            records.append(json.loads(line))
    return records
