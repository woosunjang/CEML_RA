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

    def test_preview_evidence_matrix_api_is_read_only(self):
        client, artifacts = self._client_with_seeded_threads()

        response = client.post(
            "/research/threads/rare_earth_magnets/evidence-matrix/preview",
            json={"trigger_type": "on_demand", "trigger_summary": "matrix review"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["status"], "would_write")
        self.assertEqual(payload["matrix"]["coverage"]["row_count"], 3)
        self.assertEqual(payload["recommended_thread_patch"]["schema_version"], 2)
        self.assertEqual(payload["live_store_mutations"], [])
        self.assertFalse((artifacts / "evidence_matrices").exists())

    def test_write_evidence_matrix_api_requires_confirmation(self):
        client, artifacts = self._client_with_seeded_threads()

        blocked = client.post(
            "/research/threads/rare_earth_magnets/evidence-matrix/write",
            json={"trigger_type": "on_demand", "trigger_summary": "matrix review"},
        )
        response = client.post(
            "/research/threads/rare_earth_magnets/evidence-matrix/write",
            json={
                "trigger_type": "on_demand",
                "trigger_summary": "matrix review",
                "confirm_artifact_write": True,
            },
        )

        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["read_only"])
        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["status"], "written")
        self.assertTrue(Path(payload["json_path"]).exists())
        self.assertTrue(Path(payload["markdown_path"]).exists())
        self.assertTrue(Path(payload["patch_preview_path"]).exists())
        self.assertTrue((artifacts / "evidence_matrices").exists())
        self.assertEqual(payload["live_store_mutations"], [])

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

    def test_patch_review_preview_api_does_not_write(self):
        client, artifacts = self._client_with_seeded_threads()
        patch_payload = {
            "schema_version": 2,
            "thread_id": "rare_earth_magnets",
            "research_state": "patch_review_candidate",
            "append": {
                "claims": [
                    {
                        "id": "claim.api.preview",
                        "text": "API preview는 thread를 변경하지 않는다.",
                        "status": "proposed",
                    }
                ]
            },
            "live_store_mutations": [],
        }

        response = client.post(
            "/research/threads/rare_earth_magnets/patches/preview",
            json={"patch": patch_payload, "reviewer": "tester"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        thread = research_thread.load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["status"], "previewed")
        self.assertEqual(payload["patch_result"]["status"], "would_update")
        self.assertEqual(payload["review_record_path"], None)
        self.assertEqual(payload["live_store_mutations"], [])
        self.assertFalse((artifacts / "research_patch_reviews").exists())
        self.assertFalse(any(item["id"] == "claim.api.preview" for item in thread["claims"]))

    def test_patch_review_apply_api_requires_confirmation_and_writes_artifacts(self):
        client, artifacts = self._client_with_seeded_threads()
        patch_payload = {
            "schema_version": 2,
            "thread_id": "rare_earth_magnets",
            "append": {
                "claims": [
                    {
                        "id": "claim.api.apply",
                        "text": "명시 승인된 patch만 thread에 적용한다.",
                        "status": "proposed",
                    }
                ]
            },
            "live_store_mutations": [],
        }

        blocked = client.post(
            "/research/threads/rare_earth_magnets/patches/apply",
            json={"patch": patch_payload},
        )
        response = client.post(
            "/research/threads/rare_earth_magnets/patches/apply",
            json={"patch": patch_payload, "reviewer": "tester", "confirm_artifact_write": True},
        )

        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        thread = research_thread.load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
        self.assertFalse(payload["read_only"])
        self.assertEqual(payload["status"], "applied")
        self.assertEqual(payload["patch_result"]["status"], "updated")
        self.assertTrue(Path(payload["review_record_path"]).exists())
        self.assertEqual(payload["live_store_mutations"], [])
        self.assertTrue(any(item["id"] == "claim.api.apply" for item in thread["claims"]))

    def test_patch_review_reject_api_writes_review_record_only(self):
        client, artifacts = self._client_with_seeded_threads()
        patch_payload = {
            "schema_version": 2,
            "thread_id": "rare_earth_magnets",
            "append": {
                "claims": [
                    {
                        "id": "claim.api.reject",
                        "text": "거절된 patch는 review record로만 남는다.",
                        "status": "proposed",
                    }
                ]
            },
            "live_store_mutations": [],
        }

        response = client.post(
            "/research/threads/rare_earth_magnets/patches/reject",
            json={
                "patch": patch_payload,
                "reviewer": "tester",
                "review_note": "근거 부족",
                "confirm_artifact_write": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        thread = research_thread.load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
        self.assertFalse(payload["read_only"])
        self.assertEqual(payload["status"], "rejected")
        self.assertEqual(payload["review_record"]["result_status"], "rejected")
        self.assertEqual([item["type"] for item in payload["artifact_mutations"]], ["patch_review_record"])
        self.assertFalse(any(item["id"] == "claim.api.reject" for item in thread["claims"]))

    def test_patch_review_api_rejects_invalid_patch(self):
        client, _ = self._client_with_seeded_threads()

        response = client.post(
            "/research/threads/rare_earth_magnets/patches/preview",
            json={"patch": {"schema_version": 2, "thread_id": "other_thread"}},
        )

        self.assertEqual(response.status_code, 422)

    def test_knowledge_accumulation_preview_api_is_read_only(self):
        client, artifacts = self._client_with_seeded_threads()

        response = client.post(
            "/research/threads/rare_earth_magnets/knowledge/preview",
            json={"purpose": "api knowledge accumulation"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["dry_run"])
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["status"], "would_write")
        self.assertGreater(payload["record_set"]["coverage"]["record_count"], 0)
        self.assertGreater(payload["record_set"]["coverage"]["ready_for_archival_queue"], 0)
        self.assertEqual(payload["live_store_mutations"], [])
        self.assertFalse((artifacts / "research_knowledge_records").exists())

    def test_knowledge_accumulation_write_and_enqueue_require_confirmation(self):
        client, artifacts = self._client_with_seeded_threads()
        queue_dir = artifacts / "archival_queue"

        blocked_write = client.post(
            "/research/threads/rare_earth_magnets/knowledge/write",
            json={"purpose": "api knowledge accumulation"},
        )
        write_response = client.post(
            "/research/threads/rare_earth_magnets/knowledge/write",
            json={
                "purpose": "api knowledge accumulation",
                "confirm_artifact_write": True,
            },
        )

        with patch("orchestrator.research_knowledge_accumulation.ARCHIVAL_QUEUE_DIR", queue_dir):
            blocked_enqueue = client.post(
                "/research/threads/rare_earth_magnets/knowledge/enqueue-archival",
                json={
                    "purpose": "api knowledge accumulation",
                    "confirm_artifact_write": True,
                },
            )
            enqueue_response = client.post(
                "/research/threads/rare_earth_magnets/knowledge/enqueue-archival",
                json={
                    "purpose": "api knowledge accumulation",
                    "confirm_artifact_write": True,
                    "confirm_archival_enqueue": True,
                },
            )

        self.assertEqual(blocked_write.status_code, 400)
        self.assertEqual(write_response.status_code, 200)
        self.assertEqual(blocked_enqueue.status_code, 400)
        self.assertEqual(enqueue_response.status_code, 200)
        write_payload = write_response.json()
        enqueue_payload = enqueue_response.json()
        self.assertEqual(write_payload["status"], "written")
        self.assertTrue(Path(write_payload["json_path"]).exists())
        self.assertEqual(enqueue_payload["status"], "archival_queued")
        self.assertTrue(enqueue_payload["archival_queue_mutations"])
        self.assertTrue(queue_dir.exists())
        self.assertEqual(enqueue_payload["live_store_mutations"], [])

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
