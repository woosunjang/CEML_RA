"""
Lab Orchestrator — Router

Routes tasks to agent instances directly (in-process).
No HTTP overhead — agents are Python classes called via execute().
"""

import logging
from typing import Optional

from agents.base import BaseAgent, AgentTask, AgentResult

logger = logging.getLogger(__name__)

# Lazy-loaded agent registry (in-process instances)
_agent_instances: dict[str, BaseAgent] = {}


def _get_agent(name: str) -> Optional[BaseAgent]:
    """Get or create an agent instance by name."""
    if name in _agent_instances:
        return _agent_instances[name]

    try:
        if name == "literature":
            from agents.literature.agent import LiteratureAgent
            _agent_instances[name] = LiteratureAgent()
        elif name == "teaching":
            from agents.teaching.agent import TeachingAgent
            _agent_instances[name] = TeachingAgent()
        elif name == "writing":
            from agents.writing.agent import WritingAgent
            _agent_instances[name] = WritingAgent()
        elif name == "presentation":
            from agents.presentation.agent import PresentationAgent
            _agent_instances[name] = PresentationAgent()
        elif name == "project":
            from agents.project.agent import ProjectAgent
            _agent_instances[name] = ProjectAgent()
        else:
            logger.error(f"Unknown agent: {name}")
            return None

        # Inject model config from active profile
        from orchestrator.model_profiles import profile_manager
        agent = _agent_instances[name]
        model, model_heavy = profile_manager.get_models(name)
        if model:
            agent.model = model
            agent.model_heavy = model_heavy
        logger.info(
            f"Loaded agent: {name} "
            f"(model={agent.model}, heavy={agent.model_heavy}, "
            f"profile={profile_manager.active_profile})"
        )

        return _agent_instances[name]

    except Exception as e:
        logger.error(f"Failed to load agent '{name}': {e}")
        return None


async def call_agent(
    agent_name: str,
    task: AgentTask,
) -> AgentResult:
    """Call an agent's execute() method directly (in-process).

    Args:
        agent_name: Name of the agent to call.
        task: The task to execute.

    Returns:
        AgentResult from the agent.
    """
    agent = _get_agent(agent_name)
    if not agent:
        return AgentResult(
            task_id=task.task_id,
            agent_name=agent_name,
            status="failed",
            error=f"Agent '{agent_name}' not found or failed to load.",
        )

    # Refresh model from active profile (supports hot-swap)
    from orchestrator.model_profiles import profile_manager
    model, model_heavy = profile_manager.get_models(agent_name)
    if model:
        agent.model = model
        agent.model_heavy = model_heavy

    try:
        return await agent.execute(task)
    except Exception as e:
        logger.error(f"Agent '{agent_name}' execution error: {e}")
        return AgentResult(
            task_id=task.task_id,
            agent_name=agent_name,
            status="failed",
            error=str(e),
        )


async def check_agent_health(agent_name: str) -> bool:
    """Check if an agent can be loaded."""
    return _get_agent(agent_name) is not None


async def get_all_agent_status() -> dict[str, bool]:
    """Check availability of all registered agents."""
    from agents.registry import registry
    status = {}
    for agent in registry.list_agents():
        status[agent.name] = await check_agent_health(agent.name)
    return status
