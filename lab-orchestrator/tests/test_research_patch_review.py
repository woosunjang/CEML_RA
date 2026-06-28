"""Tests for local research_thread patch review decisions."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_patch_review import process_research_patch_review  # noqa: E402
from orchestrator.research_thread import load_research_thread, seed_research_threads  # noqa: E402


FIXED_NOW = "2026-06-15T03:00:00Z"


def _patch(claim_id: str = "claim.patch_review.test") -> dict:
    return {
        "schema_version": 2,
        "thread_id": "rare_earth_magnets",
        "research_state": "patch_review_candidate",
        "append": {
            "claims": [
                {
                    "id": claim_id,
                    "text": "Patch review workflow가 승인된 claim 후보만 thread에 반영한다.",
                    "status": "proposed",
                    "source_refs": ["docs/ceml-ra-capability-development-plan-v1.md"],
                    "tags": ["patch-review"],
                    "authority_state": "proposed",
                    "review_state": "pending_review",
                    "support_state": "needs_evidence",
                    "metadata": {"live_store_mutations": []},
                }
            ]
        },
        "live_store_mutations": [],
    }


class ResearchPatchReviewTests(unittest.TestCase):
    def _seed_artifacts(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        tmp = tempfile.TemporaryDirectory()
        artifacts = Path(tmp.name) / "artifacts"
        seed_research_threads(artifacts_dir=artifacts, execute=True, created_at=FIXED_NOW)
        return tmp, artifacts

    def test_preview_does_not_write_thread_or_review_record(self):
        tmp, artifacts = self._seed_artifacts()
        self.addCleanup(tmp.cleanup)

        payload = process_research_patch_review(
            thread_id="rare_earth_magnets",
            patch=_patch(),
            action="preview",
            artifacts_dir=artifacts,
            created_at=FIXED_NOW,
        )

        thread = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
        self.assertEqual(payload["status"], "previewed")
        self.assertTrue(payload["dry_run"])
        self.assertTrue(payload["read_only"])
        self.assertIsNone(payload["review_record_path"])
        self.assertEqual(payload["live_store_mutations"], [])
        self.assertFalse((artifacts / "research_patch_reviews").exists())
        self.assertFalse(any(item["id"] == "claim.patch_review.test" for item in thread["claims"]))

    def test_apply_writes_thread_and_review_record(self):
        tmp, artifacts = self._seed_artifacts()
        self.addCleanup(tmp.cleanup)

        payload = process_research_patch_review(
            thread_id="rare_earth_magnets",
            patch=_patch(),
            action="apply",
            reviewer="tester",
            review_note="승인된 temp artifact 적용",
            confirm_artifact_write=True,
            artifacts_dir=artifacts,
            created_at=FIXED_NOW,
        )

        thread = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
        review_record_path = Path(payload["review_record_path"])
        review_record = json.loads(review_record_path.read_text(encoding="utf-8"))
        mutation_types = {item["type"] for item in payload["artifact_mutations"]}
        self.assertEqual(payload["status"], "applied")
        self.assertFalse(payload["dry_run"])
        self.assertFalse(payload["read_only"])
        self.assertEqual(payload["patch_result"]["status"], "updated")
        self.assertTrue(any(item["id"] == "claim.patch_review.test" for item in thread["claims"]))
        self.assertTrue(review_record_path.exists())
        self.assertEqual(review_record["action"], "apply")
        self.assertEqual(review_record["reviewer"], "tester")
        self.assertEqual(review_record["live_store_mutations"], [])
        self.assertEqual(payload["live_store_mutations"], [])
        self.assertIn("research_thread_json", mutation_types)
        self.assertIn("research_thread_markdown", mutation_types)
        self.assertIn("patch_review_record", mutation_types)

    def test_reject_writes_review_record_without_mutating_thread(self):
        tmp, artifacts = self._seed_artifacts()
        self.addCleanup(tmp.cleanup)

        payload = process_research_patch_review(
            thread_id="rare_earth_magnets",
            patch=_patch(),
            action="reject",
            reviewer="tester",
            review_note="근거가 부족해서 거절",
            confirm_artifact_write=True,
            artifacts_dir=artifacts,
            created_at=FIXED_NOW,
        )

        thread = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
        review_record = json.loads(Path(payload["review_record_path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "rejected")
        self.assertEqual(payload["patch_result"]["status"], "would_update")
        self.assertEqual(review_record["result_status"], "rejected")
        self.assertFalse(any(item["id"] == "claim.patch_review.test" for item in thread["claims"]))
        self.assertEqual([item["type"] for item in payload["artifact_mutations"]], ["patch_review_record"])
        self.assertEqual(payload["live_store_mutations"], [])

    def test_apply_and_reject_require_confirmation(self):
        tmp, artifacts = self._seed_artifacts()
        self.addCleanup(tmp.cleanup)

        with self.assertRaises(PermissionError):
            process_research_patch_review(
                thread_id="rare_earth_magnets",
                patch=_patch(),
                action="apply",
                artifacts_dir=artifacts,
            )
        with self.assertRaises(PermissionError):
            process_research_patch_review(
                thread_id="rare_earth_magnets",
                patch=_patch(),
                action="reject",
                artifacts_dir=artifacts,
            )

    def test_non_empty_live_store_mutations_are_rejected(self):
        tmp, artifacts = self._seed_artifacts()
        self.addCleanup(tmp.cleanup)
        patch = _patch()
        patch["live_store_mutations"] = [{"store": "neo4j"}]

        with self.assertRaises(ValueError):
            process_research_patch_review(
                thread_id="rare_earth_magnets",
                patch=patch,
                action="preview",
                artifacts_dir=artifacts,
            )


if __name__ == "__main__":
    unittest.main()
