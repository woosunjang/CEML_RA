"""Tests for read-only research_thread API endpoints."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

import orchestrator.research_thread as research_thread  # noqa: E402
from api.server import app  # noqa: E402
from orchestrator.research_thread import seed_research_threads  # noqa: E402


FIXED_NOW = "2026-06-11T03:00:00Z"


class ResearchThreadApiTests(unittest.TestCase):
    def _client_with_seeded_threads(self):
        tmp = tempfile.TemporaryDirectory()
        artifacts = Path(tmp.name) / "artifacts"
        seed_research_threads(artifacts_dir=artifacts, execute=True, created_at=FIXED_NOW)
        patcher = patch.object(research_thread, "ARTIFACTS_DIR", artifacts)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(tmp.cleanup)
        return TestClient(app), artifacts

    def test_list_research_threads_is_read_only(self):
        client, artifacts = self._client_with_seeded_threads()

        response = client.get("/research/threads")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["research_threads_dir"], str((artifacts / "research_threads").resolve()))
        self.assertEqual(
            [item["thread_id"] for item in payload["threads"]],
            ["materials_ontology_kg", "rare_earth_magnets"],
        )

    def test_get_research_thread_json(self):
        client, _ = self._client_with_seeded_threads()

        response = client.get("/research/threads/materials_ontology_kg")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["thread"]["thread_id"], "materials_ontology_kg")
        self.assertEqual(payload["thread"]["claims"], [])
        self.assertTrue(payload["json_path"].endswith("materials_ontology_kg.json"))

    def test_get_research_thread_markdown(self):
        client, _ = self._client_with_seeded_threads()

        response = client.get("/research/threads/rare_earth_magnets/markdown")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["thread_id"], "rare_earth_magnets")
        self.assertEqual(payload["source"], "artifact")
        self.assertIn("# Research Thread: rare_earth_magnets", payload["markdown"])

    def test_missing_and_invalid_thread_ids(self):
        client, _ = self._client_with_seeded_threads()

        missing = client.get("/research/threads/not_a_thread")
        invalid = client.get("/research/threads/bad$id")

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(invalid.status_code, 400)

    def test_no_mutation_methods_exist_for_research_threads(self):
        client, _ = self._client_with_seeded_threads()

        self.assertEqual(client.post("/research/threads").status_code, 405)
        self.assertEqual(client.put("/research/threads/materials_ontology_kg").status_code, 405)
        self.assertEqual(client.delete("/research/threads/materials_ontology_kg").status_code, 405)


if __name__ == "__main__":
    unittest.main()
