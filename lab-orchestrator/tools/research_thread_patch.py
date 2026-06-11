#!/usr/bin/env python3
"""Preview or apply a small patch to a CEML_RA research_thread artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_thread_patch import (  # noqa: E402
    load_patch_file,
    preview_or_apply_research_thread_patch,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preview or apply a narrow research_thread artifact patch. Defaults "
            "to dry-run and never touches live runtime, Slack, Scout, KG, or RAG stores."
        )
    )
    parser.add_argument("--thread-id", required=True, help="Target research_thread id.")
    parser.add_argument("--patch-file", required=True, type=Path, help="JSON patch file to preview or apply.")
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        help="Override artifact root. Defaults to CEML_RA_ARTIFACTS_DIR or generated/.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually update JSON and Markdown artifacts. Without this, preview only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        patch = load_patch_file(args.patch_file)
        payload = preview_or_apply_research_thread_patch(
            thread_id=args.thread_id,
            patch=patch,
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
