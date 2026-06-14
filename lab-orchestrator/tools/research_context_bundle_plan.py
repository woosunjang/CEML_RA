#!/usr/bin/env python3
"""Preview or write a shared Research Context Bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_context_bundle import preview_or_write_research_context_bundle  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a read-only context bundle shared by automatic and on-demand loops. "
            "Defaults to dry-run and never touches live KG/RAG/Slack/runtime stores."
        )
    )
    parser.add_argument("--thread-id", required=True, help="research_thread id to load")
    parser.add_argument(
        "--trigger-type",
        required=True,
        choices=("automatic", "on_demand"),
        help="Loop trigger type",
    )
    parser.add_argument("--trigger-summary", required=True, help="Human-readable trigger summary")
    parser.add_argument("--artifacts-dir", type=Path, default=None, help="Optional artifacts root")
    parser.add_argument("--max-objects", type=int, default=12, help="Maximum relevant objects to include")
    parser.add_argument("--created-at", default=None, help="Optional deterministic timestamp")
    parser.add_argument("--execute", action="store_true", help="Write JSON/Markdown bundle artifacts")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = preview_or_write_research_context_bundle(
        thread_id=args.thread_id,
        trigger_type=args.trigger_type,
        trigger_summary=args.trigger_summary,
        artifacts_dir=args.artifacts_dir,
        execute=args.execute,
        created_at=args.created_at,
        max_objects=args.max_objects,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
