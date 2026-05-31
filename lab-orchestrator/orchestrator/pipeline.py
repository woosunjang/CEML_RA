"""
Lab Orchestrator — Pipeline Executor

Sequential agent chaining with artifact passing and HITL checkpoints.

Usage:
    from orchestrator.pipeline import pipeline_executor
    result = await pipeline_executor.run("literature_to_writing", {"topic": "NASICON"})
"""

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from agents.base import AgentTask, AgentResult
from orchestrator.router import call_agent

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "pipelines.yaml"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class PipelineStep:
    agent: str
    task_template: str = ""
    output_key: str = ""
    checkpoint: bool = False
    checkpoint_message: str = ""


@dataclass
class PipelineDef:
    id: str
    name: str
    description: str = ""
    trigger_patterns: list[str] = field(default_factory=list)
    steps: list[PipelineStep] = field(default_factory=list)


@dataclass
class PipelineRunState:
    """Tracks a running pipeline for HITL support."""
    run_id: str
    pipeline_id: str
    variables: dict
    step_results: list[AgentResult] = field(default_factory=list)
    current_step: int = 0
    status: str = "running"  # running | paused | completed | failed
    checkpoint_question: str = ""


@dataclass
class PipelineResult:
    """Final result of a pipeline execution."""
    pipeline_id: str
    run_id: str
    final_content: str = ""
    step_results: list[AgentResult] = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)  # output_key → content
    status: str = "completed"
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Pipeline Executor
# ---------------------------------------------------------------------------
class PipelineExecutor:
    """Sequential pipeline executor with artifact passing and checkpoints."""

    def __init__(self):
        self._pipelines: dict[str, PipelineDef] = {}
        self._active_runs: dict[str, PipelineRunState] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self._load_config()
            self._loaded = True

    def _load_config(self):
        """Load pipeline definitions from YAML."""
        if not _CONFIG_PATH.exists():
            logger.warning(f"Pipeline config not found: {_CONFIG_PATH}")
            return

        with open(_CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}

        for pid, pdef in data.get("pipelines", {}).items():
            steps = []
            for s in pdef.get("steps", []):
                steps.append(PipelineStep(
                    agent=s["agent"],
                    task_template=s.get("task_template", ""),
                    output_key=s.get("output_key", ""),
                    checkpoint=s.get("checkpoint", False),
                    checkpoint_message=s.get("checkpoint_message", ""),
                ))
            self._pipelines[pid] = PipelineDef(
                id=pid,
                name=pdef.get("name", pid),
                description=pdef.get("description", ""),
                trigger_patterns=pdef.get("trigger_patterns", []),
                steps=steps,
            )
        logger.info(f"Loaded {len(self._pipelines)} pipeline definitions")

    def get_pipeline(self, pipeline_id: str) -> Optional[PipelineDef]:
        self._ensure_loaded()
        return self._pipelines.get(pipeline_id)

    def list_pipelines(self) -> list[dict]:
        self._ensure_loaded()
        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "steps": [{"agent": s.agent, "output_key": s.output_key} for s in p.steps],
            }
            for p in self._pipelines.values()
        ]

    def match_pipeline(self, instruction: str) -> Optional[str]:
        """Match instruction to a pipeline using trigger patterns.

        Returns pipeline_id or None.
        """
        self._ensure_loaded()
        instruction_lower = instruction.lower()

        for pid, pdef in self._pipelines.items():
            for pattern in pdef.trigger_patterns:
                if re.search(pattern, instruction_lower):
                    logger.info(
                        f"Pipeline matched: {pid} (pattern='{pattern}')"
                    )
                    return pid
        return None

    async def run(
        self,
        pipeline_id: str,
        variables: dict,
        skip_checkpoints: bool = False,
    ) -> PipelineResult:
        """Execute a pipeline sequentially.

        Args:
            pipeline_id: Which pipeline to run.
            variables: Initial variables (topic, section, reviewer_comments, etc.)
            skip_checkpoints: If True, skip HITL checkpoints.

        Returns:
            PipelineResult with all step results and artifacts.
        """
        self._ensure_loaded()
        pdef = self._pipelines.get(pipeline_id)
        if not pdef:
            return PipelineResult(
                pipeline_id=pipeline_id,
                run_id="",
                status="failed",
                error=f"Pipeline '{pipeline_id}' not found",
            )

        run_id = str(uuid.uuid4())[:8]
        state = PipelineRunState(
            run_id=run_id,
            pipeline_id=pipeline_id,
            variables=dict(variables),
        )
        self._active_runs[run_id] = state

        logger.info(
            f"Pipeline '{pdef.name}' started (run_id={run_id}, "
            f"steps={len(pdef.steps)})"
        )

        artifacts: dict[str, str] = {}

        for i, step in enumerate(pdef.steps):
            state.current_step = i

            # ── HITL Checkpoint ──
            if step.checkpoint and not skip_checkpoints:
                state.status = "paused"
                state.checkpoint_question = (
                    step.checkpoint_message
                    or f"Step {i} 완료. 계속 진행할까요?"
                )
                logger.info(
                    f"Pipeline paused at step {i}: {state.checkpoint_question}"
                )
                # In HITL mode, we'd wait for user response.
                # For now, auto-proceed (UI integration in session 8).
                state.status = "running"

            # ── Build task instruction ──
            # Merge initial variables + accumulated artifacts
            merge_vars = {**variables, **artifacts}
            if step.task_template:
                try:
                    instruction = step.task_template.format(**merge_vars)
                except KeyError as e:
                    # Missing variable — use raw template
                    logger.warning(f"Template variable missing: {e}")
                    instruction = step.task_template
            else:
                instruction = variables.get("topic", variables.get("message", ""))

            # ── Call agent ──
            task = AgentTask(
                task_id=f"{run_id}_step{i}",
                instruction=instruction,
                context={"pipeline_id": pipeline_id, "step": i},
                parent_results=[
                    r.model_dump() for r in state.step_results
                ] if state.step_results else [],
            )

            logger.info(
                f"  Step {i}: {step.agent} "
                f"(instruction={instruction[:80]}...)"
            )

            result = await call_agent(step.agent, task)
            state.step_results.append(result)

            # ── Handle failure ──
            if result.status == "failed":
                logger.error(
                    f"Pipeline step {i} ({step.agent}) failed: {result.error}"
                )
                state.status = "failed"
                # Collect what we have so far
                return PipelineResult(
                    pipeline_id=pipeline_id,
                    run_id=run_id,
                    final_content=self._build_partial_output(state, pdef),
                    step_results=state.step_results,
                    artifacts=artifacts,
                    status="failed",
                    error=f"Step {i} ({step.agent}): {result.error}",
                )

            # ── Store artifact ──
            if step.output_key:
                artifacts[step.output_key] = result.content
                logger.info(
                    f"  Artifact '{step.output_key}': {len(result.content)} chars"
                )

        # ── Pipeline complete ──
        state.status = "completed"
        del self._active_runs[run_id]

        final_content = state.step_results[-1].content if state.step_results else ""

        logger.info(
            f"Pipeline '{pdef.name}' completed "
            f"({len(state.step_results)} steps, "
            f"final={len(final_content)} chars)"
        )

        return PipelineResult(
            pipeline_id=pipeline_id,
            run_id=run_id,
            final_content=final_content,
            step_results=state.step_results,
            artifacts=artifacts,
            status="completed",
        )

    async def run_stream(
        self,
        pipeline_id: str,
        variables: dict,
    ):
        """Run pipeline with SSE event streaming.

        Yields dicts: {"event": str, "data": dict}
        """
        self._ensure_loaded()
        pdef = self._pipelines.get(pipeline_id)
        if not pdef:
            yield {"event": "pipeline_error", "data": {"error": f"Pipeline '{pipeline_id}' not found"}}
            return

        run_id = str(uuid.uuid4())[:8]
        yield {"event": "pipeline_start", "data": {
            "run_id": run_id,
            "pipeline": pdef.name,
            "steps": [{"agent": s.agent, "output_key": s.output_key} for s in pdef.steps],
        }}

        artifacts: dict[str, str] = {}
        step_results: list[AgentResult] = []

        for i, step in enumerate(pdef.steps):
            yield {"event": "step_start", "data": {"step": i, "agent": step.agent}}

            merge_vars = {**variables, **artifacts}
            if step.task_template:
                try:
                    instruction = step.task_template.format(**merge_vars)
                except KeyError:
                    instruction = step.task_template
            else:
                instruction = variables.get("topic", "")

            task = AgentTask(
                task_id=f"{run_id}_step{i}",
                instruction=instruction,
                context={"pipeline_id": pipeline_id, "step": i},
                parent_results=[r.model_dump() for r in step_results] if step_results else [],
            )

            result = await call_agent(step.agent, task)
            step_results.append(result)

            if result.status == "failed":
                yield {"event": "step_failed", "data": {
                    "step": i, "agent": step.agent, "error": result.error,
                }}
                yield {"event": "pipeline_failed", "data": {"run_id": run_id, "failed_step": i}}
                return

            if step.output_key:
                artifacts[step.output_key] = result.content

            yield {"event": "step_done", "data": {
                "step": i,
                "agent": step.agent,
                "output_key": step.output_key,
                "content_length": len(result.content),
            }}

        final = step_results[-1].content if step_results else ""
        yield {"event": "pipeline_done", "data": {
            "run_id": run_id,
            "final_content": final,
            "artifacts": {k: v[:200] + "..." if len(v) > 200 else v for k, v in artifacts.items()},
        }}

    # ── HITL Checkpoint API ──

    def get_checkpoint(self, run_id: str) -> Optional[dict]:
        """Get current checkpoint info for a paused pipeline."""
        state = self._active_runs.get(run_id)
        if not state or state.status != "paused":
            return None
        return {
            "run_id": run_id,
            "pipeline_id": state.pipeline_id,
            "current_step": state.current_step,
            "question": state.checkpoint_question,
            "options": ["proceed", "modify", "abort"],
        }

    async def respond_checkpoint(
        self, run_id: str, action: str, modifications: dict = None
    ) -> dict:
        """Respond to a HITL checkpoint.

        Actions: proceed, modify, abort
        """
        state = self._active_runs.get(run_id)
        if not state or state.status != "paused":
            return {"error": "No active checkpoint for this run_id"}

        if action == "abort":
            state.status = "failed"
            del self._active_runs[run_id]
            return {"status": "aborted", "run_id": run_id}

        if action == "modify" and modifications:
            state.variables.update(modifications)

        state.status = "running"
        return {"status": "resumed", "run_id": run_id}

    # ── Helpers ──

    def _build_partial_output(
        self, state: PipelineRunState, pdef: PipelineDef
    ) -> str:
        """Build partial output from completed steps after a failure."""
        parts = []
        for i, result in enumerate(state.step_results):
            step = pdef.steps[i] if i < len(pdef.steps) else None
            agent_name = step.agent if step else "unknown"
            status_icon = "✅" if result.status == "completed" else "❌"
            parts.append(
                f"### {status_icon} Step {i+1}: {agent_name}\n\n"
                f"{result.content[:500] if result.content else result.error or 'No output'}"
            )
        return "\n\n---\n\n".join(parts)

    def reload_config(self):
        """Hot-reload pipeline configuration."""
        self._loaded = False
        self._ensure_loaded()


# Module-level singleton
pipeline_executor = PipelineExecutor()
