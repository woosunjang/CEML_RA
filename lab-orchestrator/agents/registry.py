"""
Lab Orchestrator — Agent Registry

Manages agent registration, discovery, and routing.
Loads agents from config/agents.yaml.
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AgentRegistryEntry:
    """Single agent entry in the registry."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.display_name: str = config.get("name", name)
        self.description: str = config.get("description", "")
        self.port: int = config.get("port", 8001)
        self.icon: str = config.get("icon", "🤖")
        self.capabilities: list[str] = config.get("capabilities", [])
        self.keywords: list[str] = config.get("keywords", [])
        self.model: str = config.get("model", "gpt-4o")
        self.model_heavy: str = config.get("model_heavy", self.model)
        self.base_url: str = f"http://localhost:{self.port}"

    def match_score(self, instruction: str) -> float:
        """Calculate relevance score for an instruction."""
        instruction_lower = instruction.lower()
        score = 0.0
        for kw in self.keywords:
            if kw.lower() in instruction_lower:
                score = max(score, 0.8)
        for cap in self.capabilities:
            if cap.lower() in instruction_lower:
                score = max(score, 0.6)
        return score


class AgentRegistry:
    """Central registry of all available agents."""

    def __init__(self):
        self._agents: dict[str, AgentRegistryEntry] = {}
        self._load_config()

    def _load_config(self):
        """Load agents from config/agents.yaml."""
        config_path = _PROJECT_ROOT / "config" / "agents.yaml"
        if not config_path.exists():
            logger.warning(f"Agent config not found: {config_path}")
            return

        with open(config_path) as f:
            config = yaml.safe_load(f)

        agents_config = config.get("agents", {})
        for name, agent_config in agents_config.items():
            self._agents[name] = AgentRegistryEntry(name, agent_config)
            logger.info(f"Registered agent: {name} ({agent_config.get('icon', '🤖')})")

    def get(self, name: str) -> Optional[AgentRegistryEntry]:
        """Get agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> list[AgentRegistryEntry]:
        """List all registered agents."""
        return list(self._agents.values())

    def find_best_agent(self, instruction: str) -> Optional[AgentRegistryEntry]:
        """Find the best agent for a given instruction using keyword matching."""
        best = None
        best_score = 0.0

        for agent in self._agents.values():
            score = agent.match_score(instruction)
            if score > best_score:
                best_score = score
                best = agent

        if best and best_score > 0:
            logger.info(f"Router: Selected '{best.name}' (score={best_score:.2f}) for: {instruction[:50]}...")
            return best

        # Default to literature agent
        return self._agents.get("literature")

    def find_agents(self, instruction: str, threshold: float = 0.3) -> list[tuple[AgentRegistryEntry, float]]:
        """Find all agents above threshold, sorted by score."""
        scored = []
        for agent in self._agents.values():
            score = agent.match_score(instruction)
            if score >= threshold:
                scored.append((agent, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored


# Module-level singleton
registry = AgentRegistry()
