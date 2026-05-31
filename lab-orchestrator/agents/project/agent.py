"""
Project Agent — Milestone Tracking, Deadline Management, Reporting, Meetings

Sub-modes:
  - milestone: Project milestone tracking and status
  - deadline: Deadline management with D-day calculation
  - report: Progress report generation
  - meeting: Meeting notes structuring and action items
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents.base import BaseAgent, AgentTask, AgentResult
from agents.project.prompts import (
    MILESTONE_PROMPT, DEADLINE_PROMPT, REPORT_PROMPT, MEETING_PROMPT,
)
from agents.project import project_store
from llm.pool import generate_answer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sub-mode detection
# ---------------------------------------------------------------------------
_DEADLINE_KEYWORDS = ["마감", "제출", "deadline", "due date", "d-day", "디데이"]
_REPORT_KEYWORDS = ["보고서", "주간보고", "월간", "report", "summary", "요약"]
_MEETING_KEYWORDS = ["회의", "미팅", "회의록", "meeting", "minutes", "액션"]
_MILESTONE_KEYWORDS = [
    "마일스톤", "진행상황", "일정", "milestone", "progress", "프로젝트",
    "현황", "status", "등록", "추가",
]

_SUBMODE_PROMPTS = {
    "milestone": MILESTONE_PROMPT,
    "deadline": DEADLINE_PROMPT,
    "report": REPORT_PROMPT,
    "meeting": MEETING_PROMPT,
}


def _detect_submode(instruction: str) -> str:
    lower = instruction.lower()
    scores = {
        "deadline": sum(1 for kw in _DEADLINE_KEYWORDS if kw in lower),
        "report": sum(1 for kw in _REPORT_KEYWORDS if kw in lower),
        "meeting": sum(1 for kw in _MEETING_KEYWORDS if kw in lower),
        "milestone": sum(1 for kw in _MILESTONE_KEYWORDS if kw in lower),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "milestone"


class ProjectAgent(BaseAgent):
    name = "project"
    description = "과제 추적·일정·리포트·회의록"
    icon = "📋"
    capabilities = [
        "project_tracking", "deadline_management", "report_generation",
        "meeting_notes", "프로젝트", "일정", "마감", "회의", "보고서",
        "마일스톤", "deadline", "milestone",
    ]

    async def execute(self, task: AgentTask) -> AgentResult:
        submode = _detect_submode(task.instruction)
        logger.info(f"ProjectAgent sub-mode: {submode}")

        try:
            # Gather project context
            project_context = self._get_project_context(task)

            # Build prompt
            user_prompt = self._build_user_prompt(
                task.instruction, project_context, task.parent_results
            )

            system_prompt = _SUBMODE_PROMPTS[submode]

            chat_history = task.context.get("chat_history", [])
            selected_model = self.select_model(task)
            logger.info(f"ProjectAgent using model: {selected_model}")
            answer = await generate_answer(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=selected_model,
                chat_history=chat_history,
            )

            # Save only if response contains explicit artifact marker
            content = answer
            artifacts: list[dict] = []
            artifact_content = self._extract_artifact(answer)
            if artifact_content:
                saved_path = self._save_artifact(submode, artifact_content)
                if saved_path:
                    content += f"\n\n---\n📁 **산출물 저장**: `{saved_path}`"

            return AgentResult(
                task_id=task.task_id,
                agent_name=self.name,
                status="completed",
                content=content,
                artifacts=artifacts,
                metadata={"submode": submode},
            )

        except Exception as e:
            logger.error(f"ProjectAgent error: {e}", exc_info=True)
            return AgentResult(
                task_id=task.task_id, agent_name=self.name,
                status="failed", error=str(e),
            )

    # ------------------------------------------------------------------
    # Context gathering
    # ------------------------------------------------------------------

    def _get_project_context(self, task: AgentTask) -> str:
        """Build project context from stored data."""
        parts = []

        # Add current date
        parts.append(f"오늘 날짜: {datetime.now().strftime('%Y-%m-%d')}")

        # Workspace context
        ws_context = task.context.get("workspace_context", "")
        if ws_context:
            parts.append(f"## 프로젝트 배경\n{ws_context}")

        # Project status data
        workspace_name = task.context.get("workspace_name", "default")
        proj = project_store.get_project(workspace_name)
        if proj:
            parts.append(project_store.get_project_status_text(workspace_name))
        else:
            # Try to get all projects status
            all_status = project_store.get_all_status_text()
            if all_status != "등록된 프로젝트가 없습니다.":
                parts.append(all_status)

        # All upcoming deadlines
        deadlines = project_store.get_all_deadlines()
        if deadlines:
            urgent = [d for d in deadlines if 0 < d["d_day"] <= 30]
            if urgent:
                dl_lines = ["## 임박한 마감일"]
                for d in urgent:
                    dl_lines.append(
                        f"- {d['name']} ({d['project']}): "
                        f"{d['due']} — D-{d['d_day']}"
                    )
                parts.append("\n".join(dl_lines))

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_prompt(
        instruction: str,
        project_context: str,
        parent_results: Optional[list[dict]],
    ) -> str:
        parts = [f"## 요청\n{instruction}"]

        if parent_results:
            parent_text = "\n\n".join(
                f"### {r.get('agent_name', 'unknown')} 결과:\n{r.get('content', '')[:2000]}"
                for r in parent_results
            )
            parts.append(f"## 이전 에이전트 결과\n{parent_text}")

        if project_context:
            parts.append(f"## 프로젝트 데이터\n{project_context}")

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Artifact extraction & file save
    # ------------------------------------------------------------------

    _ARTIFACT_KEYWORDS = [
        "작성해", "생성해", "만들어", "보고서", "회의록", "리포트",
        "report", "generate", "create", "draft",
    ]

    @staticmethod
    def _extract_artifact(content: str) -> Optional[str]:
        """Extract artifact content from LLM response.

        Returns artifact text only if:
        1. [ARTIFACT]...[/ARTIFACT] markers exist, OR
        2. Response contains structured document markers (##, table, etc.)
           AND is longer than 500 chars (indicates a substantive document)

        Simple Q&A responses return None → no file saved.
        """
        import re

        # Check for explicit markers
        match = re.search(
            r"\[ARTIFACT\]\s*(.*?)\s*\[/ARTIFACT\]", content, re.DOTALL
        )
        if match:
            return match.group(1).strip()

        # No markers → don't save
        return None

    @staticmethod
    def _save_artifact(submode: str, content: str) -> Optional[str]:
        """Save extracted artifact to file."""
        from orchestrator.config import GENERATED_PROJECT_DIR
        save_dir = GENERATED_PROJECT_DIR
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ts}_{submode}.md"
            save_path = save_dir / filename
            save_path.write_text(content, encoding="utf-8")
            return str(save_path)
        except Exception as e:
            logger.warning(f"Failed to save: {e}")
            return None

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def can_handle(self, instruction: str) -> float:
        lower = instruction.lower()
        high = [
            "프로젝트", "일정", "마감", "회의", "보고서", "deadline",
            "마일스톤", "milestone", "미팅", "회의록",
        ]
        for kw in high:
            if kw in lower:
                return 0.85
        mid = ["현황", "진행", "계획", "일정표"]
        for kw in mid:
            if kw in lower:
                return 0.6
        return 0.0
