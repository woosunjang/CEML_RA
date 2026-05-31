"""
Lab Orchestrator — Workspace Manager

Loads workspace definitions from config/workspaces.yaml and provides
project-scoped context injection for agent tasks.
"""

import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "workspaces.yaml"


class Workspace(BaseModel):
    """A workspace definition."""
    name: str
    description: str = ""
    qdrant_filter: dict = Field(default_factory=dict)
    default_model: str = "gpt-4o"
    context: str = ""


class WorkspaceManager:
    """Loads and manages workspace definitions."""

    def __init__(self):
        self._workspaces: dict[str, Workspace] = {}
        self._load()

    def _load(self):
        """Load workspaces from YAML config."""
        if not _CONFIG_PATH.exists():
            logger.warning(f"Workspaces config not found: {_CONFIG_PATH}")
            self._workspaces["default"] = Workspace(name="일반")
            return

        try:
            data = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
            for key, ws_data in data.get("workspaces", {}).items():
                self._workspaces[key] = Workspace(**ws_data)
            logger.info(f"Loaded {len(self._workspaces)} workspaces")
        except Exception as e:
            logger.error(f"Failed to load workspaces: {e}")
            self._workspaces["default"] = Workspace(name="일반")

    def get(self, name: str) -> Workspace:
        """Get a workspace by name, falling back to default."""
        return self._workspaces.get(name, self._workspaces.get("default", Workspace(name="일반")))

    def list_workspaces(self) -> list[dict]:
        """List all available workspaces."""
        return [
            {"key": k, "name": ws.name, "description": ws.description}
            for k, ws in self._workspaces.items()
        ]

    def inject_context(self, task_filters: dict, task_context: dict,
                       workspace_name: str) -> tuple[dict, dict]:
        """Inject workspace context into task filters and context.

        Args:
            task_filters: Existing task filters.
            task_context: Existing task context.
            workspace_name: Workspace key.

        Returns:
            (updated_filters, updated_context) tuple.
        """
        ws = self.get(workspace_name)

        # Merge qdrant filters
        updated_filters = {**task_filters}
        if ws.qdrant_filter:
            updated_filters.update(ws.qdrant_filter)

        # Add workspace context
        updated_context = {**task_context}
        if ws.context:
            updated_context["workspace_context"] = ws.context
        updated_context["workspace_name"] = workspace_name
        updated_context["workspace_model"] = ws.default_model

        return updated_filters, updated_context


# Module-level singleton
workspace_manager = WorkspaceManager()
