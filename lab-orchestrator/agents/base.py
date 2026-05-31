"""
Lab Orchestrator — Base Agent Interface

Abstract base class that all agents must implement.
Provides common schemas for agent communication.
Supports dual-model selection (model + model_heavy).
"""

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AgentTask(BaseModel):
    """Request from orchestrator to an agent."""
    task_id: str
    instruction: str
    context: dict = Field(default_factory=dict)
    output_format: str = "markdown"
    parent_results: list[dict] = Field(default_factory=list)
    filters: dict = Field(default_factory=dict)


class AgentResult(BaseModel):
    """Response from an agent to the orchestrator."""
    task_id: str
    agent_name: str
    status: str = "completed"  # completed | failed | needs_input
    content: str = ""
    artifacts: list[dict] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    suggested_next: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class AgentInfo(BaseModel):
    """Agent registration info."""
    name: str
    description: str
    icon: str = "🤖"
    capabilities: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Heavy task detection keywords
# ---------------------------------------------------------------------------
_HEAVY_KEYWORDS = [
    "비교분석", "종합", "systematic", "synthesis", "critique",
    "최종", "final", "논문 본문", "manuscript", "rebuttal",
    "grant", "과제 신청", "심층", "deep",
]


# ---------------------------------------------------------------------------
# Base Agent ABC
# ---------------------------------------------------------------------------

class BaseAgent(ABC):
    """Abstract base class for all agents."""

    name: str
    description: str
    icon: str = "🤖"
    capabilities: list[str] = []
    model: Optional[str] = None
    model_heavy: Optional[str] = None

    @abstractmethod
    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a task and return the result."""
        ...

    def select_model(self, task: AgentTask) -> Optional[str]:
        """Select appropriate model based on task complexity.

        Returns model_heavy when:
          - Task has parent_results (multi-agent chain)
          - Instruction contains heavy-task keywords
          - Instruction is very long (> 500 chars)
        Otherwise returns the default model.
        """
        if self.model_heavy and self._is_heavy(task):
            return self.model_heavy
        return self.model

    def _is_heavy(self, task: AgentTask) -> bool:
        """Detect if a task requires the heavy model."""
        if task.parent_results:
            return True
        instruction = task.instruction.lower()
        if len(instruction) > 500:
            return True
        for kw in _HEAVY_KEYWORDS:
            if kw in instruction:
                return True
        return False

    def can_handle(self, instruction: str) -> float:
        """Return confidence score (0.0 - 1.0)."""
        instruction_lower = instruction.lower()
        score = 0.0
        for cap in self.capabilities:
            if cap.lower() in instruction_lower:
                score = max(score, 0.7)
        return score

    def get_info(self) -> AgentInfo:
        """Return agent registration info."""
        return AgentInfo(
            name=self.name,
            description=self.description,
            icon=self.icon,
            capabilities=self.capabilities,
        )
