"""
lab-paper-scout: Configuration loader
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml


class Config:
    """Loads and provides access to config.yaml settings."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path_obj = Path(__file__).parent.parent / "config" / "config.yaml"
        else:
            config_path_obj = Path(config_path)

        with open(config_path_obj, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f)

        self.project_root = config_path_obj.parent.parent
        self._path_overrides: Dict[str, str] = {}
        self._ensure_directories()

    def _ensure_directories(self):
        """Create data directories if they don't exist."""
        for key in ["inbox", "processed", "archive", "reports"]:
            path = self.get_path(key)
            path.mkdir(parents=True, exist_ok=True)

        log_path = self.get_path("logs")
        log_path.mkdir(parents=True, exist_ok=True)

    def override_paths(self, **kwargs):
        """Override specific path keys for testing. e.g. override_paths(db='data/.test.db')"""
        self._path_overrides.update(kwargs)
        self._ensure_directories()

    def get_path(self, key: str) -> Path:
        """Resolve a path from config relative to project root."""
        if key in self._path_overrides:
            return (self.project_root / self._path_overrides[key]).resolve()
        raw = self._data["paths"].get(key, f"./data/{key}")
        return (self.project_root / raw).resolve()

    @property
    def topics(self) -> List[Dict]:
        return self._data.get("topics") or []

    @property
    def schedule(self) -> Dict:
        return self._data["schedule"]

    @property
    def api(self) -> Dict:
        return self._data["api"]

    @property
    def slack(self) -> Dict:
        return self._data.get("slack", {})

    @property
    def gemini_api_key(self) -> str:
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise EnvironmentError(
                "GEMINI_API_KEY environment variable is not set."
            )
        return key

    @property
    def slack_webhook_url(self) -> Optional[str]:
        env_var = self.slack.get("webhook_url_env", "SLACK_WEBHOOK_URL")
        return os.environ.get(env_var)
