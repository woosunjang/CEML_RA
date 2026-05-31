"""
Lab Orchestrator — Planner

LLM-based task decomposition: takes a user instruction
and produces an execution plan of agent tasks.
"""

import json
import logging
from typing import Optional

from llm.pool import generate_answer
from agents.registry import registry
from orchestrator.schemas import TaskPlan, ExecutionPlan

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are a task planner for a multi-agent research assistant system.

Given a user instruction, you decompose it into one or more tasks,
each assigned to a specific agent.

Available agents:
{agent_list}

## Rules
1. If the instruction maps to a single agent, return a plan with one task.
2. If it requires multiple agents, order them by dependency.
3. Use 'depends_on' to specify that a task needs results from a prior task.
4. Each task's 'agent' field must be one of the available agent names.
5. Each task's 'task' field should be a clear, specific instruction for that agent.
6. **IMPORTANT**: If the message is a greeting, casual chat, test message, general question,
   or anything that does NOT require any specialized agent, set the agent to "none".
   Examples of "none": "안녕", "테스트", "고마워", "잘 되나?", "지금 몇 시야?",
   "넌 뭘 할 수 있어?", trivial chitchat, system status inquiries without specific agent needs.
   Do NOT force-assign these to project/literature/etc.

## Resource Constraints (MUST FOLLOW)
7. **presentation agent MUST always run alone as a single task.**
   Never combine presentation with writing, literature, or any other agent.
   The presentation agent already handles content quality internally.
8. **Maximum 2 tasks per plan.** Do not create plans with 3 or more tasks.

## Output Format (JSON only, no markdown fences)
{{
  "tasks": [
    {{"agent": "literature", "task": "...", "depends_on": []}},
    {{"agent": "teaching", "task": "...", "depends_on": ["literature"]}}
  ],
  "reasoning": "Brief explanation of the plan"
}}
"""


# Quick chitchat patterns — bypass LLM planner entirely
_CHITCHAT_PATTERNS = [
    "안녕", "하이", "헬로", "hello", "hi ", "hey", "테스트", "test",
    "고마워", "감사", "thanks", "ㅎㅇ", "ㅎㅎ", "ㅋㅋ",
    "잘 되", "작동", "반가",
]


def _is_chitchat(instruction: str) -> bool:
    """Fast check for obvious chitchat messages."""
    lower = instruction.lower().strip()
    if len(lower) < 30:  # Short messages are likely chitchat
        for pat in _CHITCHAT_PATTERNS:
            if pat in lower:
                return True
    return False


async def create_plan(instruction: str, agent_override: Optional[str] = None) -> ExecutionPlan:
    """Create an execution plan from a user instruction.

    Args:
        instruction: User's natural language instruction.
        agent_override: If set, skip planning and route directly to this agent.

    Returns:
        ExecutionPlan with ordered tasks.
    """
    # If agent is explicitly specified, skip planning and route directly
    if agent_override:
        agent = registry.get(agent_override)
        if agent:
            return ExecutionPlan(
                tasks=[TaskPlan(agent=agent_override, task=instruction)],
                reasoning=f"User selected {agent.display_name} directly.",
                is_multi_agent=False,
            )

    # Fast chitchat bypass (no LLM call needed)
    if _is_chitchat(instruction):
        return ExecutionPlan(
            tasks=[TaskPlan(agent="none", task=instruction)],
            reasoning="Chitchat / general message — no specialized agent needed.",
            is_multi_agent=False,
        )

    # Check for pipeline pattern match
    from orchestrator.pipeline import pipeline_executor
    matched_pipeline = pipeline_executor.match_pipeline(instruction)
    if matched_pipeline:
        pdef = pipeline_executor.get_pipeline(matched_pipeline)
        if pdef:
            tasks = [
                TaskPlan(agent=step.agent, task=step.task_template or instruction)
                for step in pdef.steps
            ]
            return ExecutionPlan(
                tasks=tasks,
                reasoning=f"Pipeline matched: {pdef.name}",
                is_multi_agent=True,
                pipeline_id=matched_pipeline,
            )

    # Build agent list for the prompt
    agents = registry.list_agents()
    agent_list = "\n".join(
        f"- {a.name} ({a.icon} {a.display_name}): {a.description}. "
        f"Capabilities: {', '.join(a.capabilities)}"
        for a in agents
    )

    system_prompt = PLANNER_SYSTEM_PROMPT.format(agent_list=agent_list)

    try:
        response = await generate_answer(
            system_prompt=system_prompt,
            user_prompt=f"User instruction: {instruction}",
            temperature=0.1,
        )

        # Parse JSON response
        # Strip potential markdown code fences
        response = response.strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[1]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

        plan_data = json.loads(response)

        tasks = [TaskPlan(**t) for t in plan_data.get("tasks", [])]
        reasoning = plan_data.get("reasoning", "")

        # If LLM classified as "none", keep it
        if tasks and tasks[0].agent == "none":
            return ExecutionPlan(
                tasks=tasks,
                reasoning=reasoning or "General conversation — no agent needed.",
                is_multi_agent=False,
            )

        if not tasks:
            # Fallback: route to best matching agent
            best = registry.find_best_agent(instruction)
            agent_name = best.name if best else "literature"
            tasks = [TaskPlan(agent=agent_name, task=instruction)]
            reasoning = f"Fallback: routed to {agent_name}"

        # ── Resource constraints (hard enforcement) ──
        # Presentation must run alone (OOM risk with multi-agent chains)
        has_presentation = any(t.agent == "presentation" for t in tasks)
        if has_presentation and len(tasks) > 1:
            pres_task = next(t for t in tasks if t.agent == "presentation")
            tasks = [pres_task]
            reasoning += " [Enforced: presentation runs alone]"
            logger.info("Enforced single-agent for presentation task")

        # Cap at 2 tasks max (16GB memory constraint)
        if len(tasks) > 2:
            tasks = tasks[:2]
            reasoning += " [Enforced: max 2 tasks]"
            logger.info(f"Enforced max 2 tasks (was {len(tasks)})")

        return ExecutionPlan(
            tasks=tasks,
            reasoning=reasoning,
            is_multi_agent=len(tasks) > 1,
        )

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Planner error: {e}")
        # Fallback: keyword-based routing
        best = registry.find_best_agent(instruction)
        agent_name = best.name if best else "literature"
        return ExecutionPlan(
            tasks=[TaskPlan(agent=agent_name, task=instruction)],
            reasoning=f"Fallback (planner error): routed to {agent_name}",
            is_multi_agent=False,
        )
