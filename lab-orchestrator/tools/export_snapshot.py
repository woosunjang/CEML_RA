#!/usr/bin/env python3
"""Export one explicit snapshot file into the CEML_RA artifact root."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from integrations.export_manifest import (  # noqa: E402
    VALID_SNAPSHOT_KINDS,
    execute_snapshot_export,
    plan_snapshot_export,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Copy one explicit snapshot/export file into CEML_RA_ARTIFACTS_DIR "
            "and append a JSONL manifest row. Defaults to dry-run."
        )
    )
    parser.add_argument("--source", required=True, help="Explicit source file to export.")
    parser.add_argument(
        "--kind",
        required=True,
        choices=sorted(VALID_SNAPSHOT_KINDS),
        help="Snapshot/export category.",
    )
    parser.add_argument("--label", help="Short manifest label. Defaults to source stem.")
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        help="Override artifact root. Defaults to CEML_RA_ARTIFACTS_DIR or generated/.",
    )
    parser.add_argument(
        "--include-sidecars",
        action="store_true",
        help="Also copy SQLite -wal/-shm sidecars when they exist.",
    )
    parser.add_argument("--actor", default="manual", help="Manifest actor label.")
    parser.add_argument("--note", default="", help="Optional manifest note.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually copy files and append the manifest. Without this, preview only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    kwargs = {}
    if args.artifacts_dir is not None:
        kwargs["artifacts_dir"] = args.artifacts_dir

    plan = plan_snapshot_export(
        Path(args.source),
        kind=args.kind,
        label=args.label,
        include_sidecars=args.include_sidecars,
        **kwargs,
    )

    if args.execute:
        record = execute_snapshot_export(plan, actor=args.actor, note=args.note)
    else:
        record = plan.preview_record()

    print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
