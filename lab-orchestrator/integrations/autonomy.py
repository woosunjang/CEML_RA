"""
Autonomy action log.

Records actions the assistant performs without step-by-step user approval.
The log is append-only JSONL so it remains easy to inspect, archive, and
replay into reports later.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrator.config import DATA_DIR


ACTION_LOG_PATH = DATA_DIR / "autonomy_actions.jsonl"


def log_autonomy_action(
    action_type: str,
    reason: str,
    *,
    inputs: dict[str, Any] | None = None,
    files_changed: list[str] | None = None,
    status: str = "completed",
    error: str = "",
) -> dict[str, Any]:
    """Append one autonomy action entry and return it."""
    ACTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": action_type,
        "reason": reason,
        "inputs": inputs or {},
        "files_changed": files_changed or [],
        "status": status,
        "error": error,
    }
    with ACTION_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def list_autonomy_actions(limit: int = 100) -> list[dict[str, Any]]:
    """Read the newest autonomy action entries."""
    if not ACTION_LOG_PATH.exists():
        return []

    lines = ACTION_LOG_PATH.read_text(encoding="utf-8").splitlines()
    entries: list[dict[str, Any]] = []
    for line in reversed(lines[-limit:]):
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries
