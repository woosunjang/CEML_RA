#!/usr/bin/env python3
"""Seed the Phase 1 CEML_RA research_thread artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_thread import seed_research_threads  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create dry-run or durable seed artifacts for the CEML_RA Phase 1 "
            "research_thread memory spine. Defaults to dry-run."
        )
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        help="Override artifact root. Defaults to CEML_RA_ARTIFACTS_DIR or generated/.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write JSON and Markdown artifacts. Without this, preview only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = seed_research_threads(
        artifacts_dir=args.artifacts_dir,
        execute=args.execute,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
