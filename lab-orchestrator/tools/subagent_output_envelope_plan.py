#!/usr/bin/env python3
"""Plan a reviewable subagent output envelope from a Research Loop Packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.subagent_output_envelope import (  # noqa: E402
    ROLE_OUTPUT_TYPES,
    preview_or_write_subagent_output_envelope,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a dry-run or durable Subagent Output Envelope from a Research Loop Packet. "
            "This does not execute subagents, call LLMs, mutate research_thread, or touch live stores."
        )
    )
    parser.add_argument("--loop-packet", required=True, type=Path, help="Path to a Research Loop Packet JSON file.")
    parser.add_argument("--role", required=True, choices=tuple(ROLE_OUTPUT_TYPES), help="Selected subagent role.")
    parser.add_argument(
        "--output-type",
        required=True,
        help="Role-specific output type, such as evidence_boundary_preview or next_action_plan.",
    )
    parser.add_argument("--summary", required=True, help="Korean-first summary supplied by the subagent or operator.")
    parser.add_argument(
        "--missing-evidence",
        action="append",
        default=[],
        help="Optional Korean-first missing evidence note. Repeat for multiple notes.",
    )
    parser.add_argument(
        "--counterargument",
        action="append",
        default=[],
        help="Optional Korean-first counterargument note. Repeat for multiple notes.",
    )
    parser.add_argument(
        "--failure-mode",
        action="append",
        default=[],
        help="Optional Korean-first failure mode note. Repeat for multiple notes.",
    )
    parser.add_argument(
        "--artifact-candidate",
        action="append",
        default=[],
        help="Optional Korean-first durable artifact candidate note. Repeat for multiple notes.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        help="Override artifact root. Defaults to CEML_RA_ARTIFACTS_DIR or generated/.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write envelope artifacts. Without this, preview only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = preview_or_write_subagent_output_envelope(
            loop_packet_path=args.loop_packet,
            role=args.role,
            output_type=args.output_type,
            summary=args.summary,
            artifacts_dir=args.artifacts_dir,
            execute=args.execute,
            missing_evidence=args.missing_evidence,
            counterarguments=args.counterargument,
            failure_modes=args.failure_mode,
            artifact_candidates=args.artifact_candidate,
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
