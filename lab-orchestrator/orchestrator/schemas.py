"""
Lab Orchestrator — Schemas

Common data structures for the orchestration pipeline.
"""

from typing import Optional
from pydantic import BaseModel, Field


class TaskPlan(BaseModel):
    """A single task in the execution plan."""
    agent: str
    task: str
    depends_on: list[str] = Field(default_factory=list)
    filters: dict = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    """Complete execution plan from the planner."""
    tasks: list[TaskPlan]
    reasoning: str = ""
    is_multi_agent: bool = False
    pipeline_id: Optional[str] = None  # If set, use PipelineExecutor


class ChatRequest(BaseModel):
    """Incoming chat request from the UI."""
    message: str
    conversation_id: Optional[str] = None
    workspace: str = "default"
    agent_override: Optional[str] = None  # Force specific agent
    mode: str = "normal"  # normal | debate | pipeline
    debate_rounds: Optional[int] = None  # Override debate rounds (2 or 3)
    pipeline_id: Optional[str] = None  # Force specific pipeline
    pipeline_vars: dict = Field(default_factory=dict)  # Variables for pipeline
    filters: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Chat response to the UI."""
    conversation_id: str
    content: str
    agent_name: str = "orchestrator"
    citations: list[dict] = Field(default_factory=list)
    execution_steps: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

