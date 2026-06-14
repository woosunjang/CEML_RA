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

    def test_get_research_context_bundle_preview(self):
        client, _ = self._client_with_seeded_threads()

        response = client.get(
            "/research/threads/rare_earth_magnets/context",
            params={"trigger_type": "on_demand", "trigger_summary": "proposal discussion"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["live_store_mutations"], [])
        self.assertEqual(payload["bundle"]["trigger"]["type"], "on_demand")
        self.assertEqual(payload["bundle"]["activation_previews"]["kg_ingest_preview"]["status"], "preview_only")

    def test_preview_research_loop_packet_api(self):
        client, _ = self._client_with_seeded_threads()

        response = client.post(
            "/research/loops/preview",
            json={
                "thread_id": "rare_earth_magnets",
                "trigger_type": "on_demand",
                "trigger_summary": "proposal discussion",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["live_store_mutations"], [])
        self.assertIn("context_bundle", payload["packet"])
        self.assertEqual(payload["packet"]["thread_patch_preview"]["schema_version"], 2)

    def test_preview_subagent_output_envelope_api(self):
        client, _ = self._client_with_seeded_threads()
        packet = client.post(
            "/research/loops/preview",
            json={
                "thread_id": "rare_earth_magnets",
                "trigger_type": "on_demand",
                "trigger_summary": "proposal discussion",
            },
        ).json()["packet"]

        response = client.post(
            "/research/subagent-envelopes/preview",
            json={
                "loop_packet": packet,
                "role": "Evidence Critic",
                "output_type": "evidence_boundary_preview",
                "summary": "근거 경계를 검토하되 확정 claim을 만들지 않는다.",
                "missing_evidence": ["primary source 확인 필요"],
                "counterarguments": ["요약만으로는 연구 품질을 증명하지 못한다."],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["live_store_mutations"], [])
        self.assertEqual(payload["envelope"]["schema_version"], 2)
        self.assertEqual(payload["envelope"]["critique_gate"]["status"], "requires_review")

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
