#!/usr/bin/env python3
"""Run the local-only CEML_RA Research Coordinator dry-run loop."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_thread import DEFAULT_SEED_TOPICS  # noqa: E402
from orchestrator.research_coordinator import (  # noqa: E402
    run_coordinator_dry_run,
    run_coordinator_dry_run_for_thread,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a local-only Research Coordinator dry-run over research_thread "
            "artifacts. Defaults to dry-run and never touches live KG/RAG/Slack/runtime stores."
        )
    )
    parser.add_argument(
        "--thread-id",
        choices=DEFAULT_SEED_TOPICS,
        help="Run one research_thread. Defaults to both seed threads.",
    )
    parser.add_argument(
        "--query",
        help="Scout query. Only valid with --thread-id; otherwise topic defaults are used.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        help="Override artifact root. Defaults to CEML_RA_ARTIFACTS_DIR or generated/.",
    )
    parser.add_argument("--db-path", type=Path, help="Override Scout SQLite path for local tests or previews.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum Scout rows per thread.")
    parser.add_argument("--min-score", type=float, default=70.0, help="Minimum Scout relevance score.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually update thread JSON/Markdown artifacts. Without this, preview only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.query and not args.thread_id:
        raise SystemExit("--query requires --thread-id so the query-to-thread mapping is explicit")

    if args.thread_id:
        payload = run_coordinator_dry_run_for_thread(
            thread_id=args.thread_id,
            artifacts_dir=args.artifacts_dir,
            db_path=args.db_path,
            query=args.query,
            limit=args.limit,
            min_score=args.min_score,
            execute=args.execute,
        )
    else:
        payload = run_coordinator_dry_run(
            artifacts_dir=args.artifacts_dir,
            db_path=args.db_path,
            limit=args.limit,
            min_score=args.min_score,
            execute=args.execute,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
