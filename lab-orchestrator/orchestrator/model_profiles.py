"""
Lab Orchestrator — Model Profile Manager

Manages cost/performance model profiles with:
  - Global profile switching (all agents)
  - Per-agent override
  - Runtime hot-swap without restart

Usage:
    from orchestrator.model_profiles import profile_manager
    profile_manager.set_profile("cost")
    profile_manager.set_agent_profile("writing", "performance")
    m, mh = profile_manager.get_models("literature")
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config" / "model_profiles.yaml"


class ModelProfileManager:
    """Manages model profile switching."""

    def __init__(self):
        self._profiles: dict = {}
        self._active_profile: str = "performance"
        self._agent_overrides: dict[str, str] = {}  # agent → profile name
        self._load()

    def _load(self):
        """Load profiles from YAML config."""
        if not _CONFIG_PATH.exists():
            logger.warning(f"Model profiles not found: {_CONFIG_PATH}")
            return

        with open(_CONFIG_PATH) as f:
            config = yaml.safe_load(f)

        self._profiles = config.get("profiles", {})
        self._active_profile = config.get("default_profile", "performance")
        logger.info(
            f"Loaded {len(self._profiles)} model profiles, "
            f"active: {self._active_profile}"
        )

    def set_profile(self, profile_name: str) -> bool:
        """Switch global profile for all agents."""
        if profile_name not in self._profiles:
            logger.error(f"Unknown profile: {profile_name}")
            return False

        self._active_profile = profile_name
        self._agent_overrides.clear()  # Clear per-agent overrides
        logger.info(f"Switched global profile to: {profile_name}")
        return True

    def set_agent_profile(self, agent_name: str, profile_name: str) -> bool:
        """Override profile for a specific agent."""
        if profile_name not in self._profiles:
            logger.error(f"Unknown profile: {profile_name}")
            return False

        self._agent_overrides[agent_name] = profile_name
        logger.info(f"Agent '{agent_name}' → profile '{profile_name}'")
        return True

    def clear_agent_override(self, agent_name: str):
        """Remove per-agent override, fall back to global."""
        self._agent_overrides.pop(agent_name, None)

    def get_models(self, agent_name: str) -> tuple[Optional[str], Optional[str]]:
        """Get (model, model_heavy) for an agent.

        Returns:
            Tuple of (default_model, heavy_model).
            Either may be None if not configured.
        """
        profile_name = self._agent_overrides.get(agent_name, self._active_profile)
        profile = self._profiles.get(profile_name, {})
        agent_config = profile.get(agent_name, {})

        model = agent_config.get("model")
        model_heavy = agent_config.get("model_heavy", model)
        return model, model_heavy

    def get_planner_model(self) -> Optional[str]:
        """Get the planner model for the active profile."""
        profile = self._profiles.get(self._active_profile, {})
        planner = profile.get("planner", {})
        return planner.get("model")

    @property
    def active_profile(self) -> str:
        return self._active_profile

    @property
    def agent_overrides(self) -> dict[str, str]:
        return dict(self._agent_overrides)

    def get_status(self) -> dict:
        """Return current profile status."""
        status = {
            "active_profile": self._active_profile,
            "description": self._profiles.get(
                self._active_profile, {}
            ).get("description", ""),
            "agent_overrides": dict(self._agent_overrides),
            "available_profiles": list(self._profiles.keys()),
        }

        # Show effective models per agent
        agents = ["literature", "teaching", "writing", "presentation", "project"]
        effective = {}
        for agent in agents:
            m, mh = self.get_models(agent)
            profile = self._agent_overrides.get(agent, self._active_profile)
            effective[agent] = {
                "profile": profile,
                "model": m,
                "model_heavy": mh,
            }
        status["effective_models"] = effective
        return status


# Module-level singleton
profile_manager = ModelProfileManager()
