"""Focused tests for Stage 0 artifact/runtime path boundaries."""

import importlib
import importlib.util
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ORCH_ROOT.parent
SCOUT_CONFIG_PATH = REPO_ROOT / "lab-paper-scout" / "src" / "config.py"
ARTIFACTS_ENV = "CEML_RA_ARTIFACTS_DIR"

sys.path.insert(0, str(ORCH_ROOT))


def _load_orchestrator_config():
    import orchestrator.config as config

    return importlib.reload(config)


def _load_scout_config_module():
    spec = importlib.util.spec_from_file_location(
        "paper_scout_config_for_test",
        SCOUT_CONFIG_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ConfigPathTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop(ARTIFACTS_ENV, None)
        _load_orchestrator_config()

    def test_orchestrator_artifacts_fall_back_to_generated(self):
        os.environ.pop(ARTIFACTS_ENV, None)

        config = _load_orchestrator_config()

        self.assertEqual(config.ARTIFACTS_DIR, config.CEML_ROOT / "generated")
        self.assertEqual(config.GENERATED_DIR, config.ARTIFACTS_DIR)
        self.assertEqual(config.GENERATED_REPORTS_DIR, config.ARTIFACTS_DIR / "reports")
        self.assertEqual(config.DATA_DIR, config.CEML_ROOT / "data")
        self.assertEqual(config.USAGE_DB, config.DATA_DIR / "usage.db")

    def test_orchestrator_artifacts_env_does_not_move_runtime_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_dir = Path(tmp) / "RA_artifacts"
            os.environ[ARTIFACTS_ENV] = str(artifacts_dir)

            config = _load_orchestrator_config()

            self.assertEqual(config.ARTIFACTS_DIR, artifacts_dir.resolve())
            self.assertEqual(config.GENERATED_WRITING_DIR, artifacts_dir.resolve() / "writing")
            self.assertEqual(config.GENERATED_REPORTS_DIR, artifacts_dir.resolve() / "reports")
            self.assertEqual(config.DATA_DIR, config.CEML_ROOT / "data")
            self.assertEqual(config.LOG_DIR, config.CEML_ROOT / "logs")
            self.assertEqual(config.COMMANDS_DIR, config.PROJECT_ROOT / "commands")
            self.assertFalse(str(config.USAGE_DB).startswith(str(artifacts_dir.resolve())))

    def test_scout_reports_follow_artifacts_env_but_live_paths_stay_local(self):
        scout_config = _load_scout_config_module()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "paper-scout"
            config_dir = root / "config"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "config.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    topics: []
                    schedule: {}
                    api: {}
                    paths:
                      inbox: "./data/inbox"
                      processed: "./data/processed"
                      archive: "./data/archive"
                      reports: "../../generated/reports"
                      db: "./data/paper_scout.db"
                      logs: "./logs"
                    """
                ).strip(),
                encoding="utf-8",
            )
            artifacts_dir = Path(tmp) / "RA_artifacts"
            os.environ[ARTIFACTS_ENV] = str(artifacts_dir)

            config = scout_config.Config(config_path=str(config_path))

            self.assertEqual(config.get_path("reports"), artifacts_dir.resolve() / "reports")
            self.assertEqual(config.get_path("db"), root.resolve() / "data" / "paper_scout.db")
            self.assertEqual(config.get_path("processed"), root.resolve() / "data" / "processed")
