#!/usr/bin/env python3
"""Plan the next CEML_RA research work package from durable artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_work_package import preview_or_write_work_package_plan  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a dry-run or durable execution packet for the next research "
            "work package. This does not mutate research_thread, Slack, Scout, "
            "KG/RAG stores, or runtime services."
        )
    )
    parser.add_argument("--proposal-seed", required=True, type=Path, help="Proposal seed JSON path.")
    parser.add_argument("--thread-id", required=True, help="Target research_thread id.")
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        help="Override artifact root. Defaults to CEML_RA_ARTIFACTS_DIR or generated/.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write execution packet artifacts. Without this, preview only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = preview_or_write_work_package_plan(
            proposal_seed_path=args.proposal_seed,
            thread_id=args.thread_id,
            artifacts_dir=args.artifacts_dir,
            execute=args.execute,
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
