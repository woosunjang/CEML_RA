#!/usr/bin/env python3
"""CLI wrapper for research memory preflight checks."""

from __future__ import annotations

import sys
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_memory_healthcheck import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
