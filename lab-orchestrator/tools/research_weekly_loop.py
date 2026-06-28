#!/usr/bin/env python3
"""Run the Weekly Useful Research Loop v0."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_weekly_loop import DEFAULT_QUERY, DEFAULT_THREAD_ID, preview_or_run_weekly_loop  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run CEML_RA Weekly Useful Research Loop v0. "
            "v0 supports materials_ontology_kg and writes artifacts/live memory only with --execute."
        )
    )
    parser.add_argument("--thread-id", default=DEFAULT_THREAD_ID, help=f"Research thread id. v0 default: {DEFAULT_THREAD_ID}")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Research query for Scout/RAG/KG retrieval.")
    parser.add_argument("--days", type=int, default=7, help="Weekly lookback window metadata, 1-31 days.")
    parser.add_argument("--artifacts-dir", type=Path, help="Override artifact root.")
    parser.add_argument("--scout-limit", type=int, default=5)
    parser.add_argument("--rag-limit", type=int, default=5)
    parser.add_argument("--kg-limit", type=int, default=5)
    parser.add_argument("--execute", action="store_true", help="Write weekly artifacts, update thread, and attempt live memory writes.")
    parser.add_argument("--no-live-memory", action="store_true", help="When executing, skip Graphiti/Qdrant writes.")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = await preview_or_run_weekly_loop(
        thread_id=args.thread_id,
        query=args.query,
        days=args.days,
        artifacts_dir=args.artifacts_dir,
        execute=args.execute,
        use_live_memory=not args.no_live_memory,
        scout_limit=args.scout_limit,
        rag_limit=args.rag_limit,
        kg_limit=args.kg_limit,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
