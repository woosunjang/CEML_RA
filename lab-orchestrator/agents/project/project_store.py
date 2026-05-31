"""
Project Agent — Project Data Store

JSON-based persistent storage for project milestones, deadlines, and meetings.
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from orchestrator.config import PROJECTS_JSON
_STORE_PATH = PROJECTS_JSON


def _load() -> dict:
    """Load project data from JSON file."""
    if not _STORE_PATH.exists():
        return {}
    try:
        return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to load projects: {e}")
        return {}


def _save(data: dict):
    """Save project data to JSON file."""
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_projects() -> list[dict]:
    """List all projects with basic info."""
    data = _load()
    return [
        {
            "key": k,
            "name": v.get("name", k),
            "milestone_count": len(v.get("milestones", [])),
            "deadline_count": len(v.get("deadlines", [])),
        }
        for k, v in data.items()
    ]


def get_project(key: str) -> Optional[dict]:
    """Get a project by key."""
    return _load().get(key)


def save_project(key: str, project: dict):
    """Save or update a project."""
    data = _load()
    data[key] = project
    _save(data)
    logger.info(f"Project saved: {key}")


def get_all_deadlines() -> list[dict]:
    """Get all deadlines across projects, sorted by date."""
    data = _load()
    deadlines = []
    today = date.today()

    for proj_key, proj in data.items():
        for dl in proj.get("deadlines", []):
            due = dl.get("due", "")
            try:
                due_date = datetime.strptime(due, "%Y-%m-%d").date()
                d_day = (due_date - today).days
            except ValueError:
                d_day = 999

            deadlines.append({
                "project": proj.get("name", proj_key),
                "project_key": proj_key,
                "name": dl.get("name", ""),
                "due": due,
                "d_day": d_day,
                "status": dl.get("status", "pending"),
            })

    return sorted(deadlines, key=lambda x: x["d_day"])


def get_project_status_text(key: str) -> str:
    """Generate a text summary of project status for LLM context."""
    proj = get_project(key)
    if not proj:
        return f"프로젝트 '{key}'를 찾을 수 없습니다."

    today = date.today()
    lines = [f"## 프로젝트: {proj.get('name', key)}\n"]

    # Milestones
    milestones = proj.get("milestones", [])
    if milestones:
        lines.append("### 마일스톤")
        for ms in milestones:
            lines.append(
                f"- {ms['name']}: {ms.get('status', '?')} "
                f"({ms.get('progress', 0)}%) — 기한: {ms.get('due', '미정')}"
            )

    # Deadlines
    deadlines = proj.get("deadlines", [])
    if deadlines:
        lines.append("\n### 마감일")
        for dl in deadlines:
            try:
                due_date = datetime.strptime(dl["due"], "%Y-%m-%d").date()
                d_day = (due_date - today).days
                status = "⚠️ 임박" if d_day <= 7 else f"D-{d_day}"
            except ValueError:
                status = "?"
            lines.append(f"- {dl['name']}: {dl['due']} ({status})")

    return "\n".join(lines)


def get_all_status_text() -> str:
    """Generate status text for all projects."""
    data = _load()
    if not data:
        return "등록된 프로젝트가 없습니다."

    parts = []
    for key in data:
        parts.append(get_project_status_text(key))
    return "\n\n---\n\n".join(parts)
