"""Tests for research_thread knowledge accumulation records."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_knowledge_accumulation import (  # noqa: E402
    build_knowledge_record_set,
    preview_or_write_knowledge_records,
    render_knowledge_record_set_markdown,
)
from orchestrator.research_thread import build_seed_research_thread, write_research_thread  # noqa: E402
from orchestrator.research_thread_patch import apply_research_thread_patch  # noqa: E402


FIXED_NOW = "2026-06-22T01:00:00Z"


def _thread_with_pending_claim() -> dict:
    thread = build_seed_research_thread("rare_earth_magnets", created_at=FIXED_NOW)
    thread, _ = apply_research_thread_patch(
        thread,
        {
            "schema_version": 2,
            "thread_id": "rare_earth_magnets",
            "append": {
                "claims": [
                    {
                        "id": "claim.pending.not_knowledge_yet",
                        "text": "아직 reviewed가 아닌 claim은 기본 지식 축적 대상이 아니다.",
                        "status": "proposed",
                        "support_state": "needs_evidence",
                        "review_state": "pending_review",
                    }
                ]
            },
            "live_store_mutations": [],
        },
        created_at=FIXED_NOW,
    )
    return thread


class ResearchKnowledgeAccumulationTests(unittest.TestCase):
    def test_reviewed_thread_objects_become_knowledge_records(self):
        record_set = build_knowledge_record_set(
            research_thread=_thread_with_pending_claim(),
            purpose="test accumulation",
            created_at=FIXED_NOW,
        )

        record_ids = {record["object_id"] for record in record_set["records"]}
        self.assertGreaterEqual(record_set["coverage"]["record_count"], 5)
        self.assertEqual(record_set["coverage"]["record_count"], record_set["coverage"]["ready_for_archival_queue"])
        self.assertNotIn("claim.pending.not_knowledge_yet", record_ids)
        self.assertTrue(record_set["archival_queue_preview"])
        self.assertEqual(record_set["live_store_mutations"], [])
        self.assertEqual(record_set["destination_previews"]["graphiti_archival_queue"]["status"], "preview_only")

    def test_pending_objects_are_only_included_when_explicit(self):
        record_set = build_knowledge_record_set(
            research_thread=_thread_with_pending_claim(),
            purpose="test accumulation",
            include_pending_review=True,
            created_at=FIXED_NOW,
        )

        pending = next(record for record in record_set["records"] if record["object_id"] == "claim.pending.not_knowledge_yet")
        self.assertEqual(pending["accumulation_state"], "needs_review")
        self.assertEqual(pending["destination_policy"]["graphiti"], "hold_until_reviewed")

    def test_preview_write_and_enqueue_use_local_artifacts_and_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            queue = root / "archival_queue"
            write_research_thread(_thread_with_pending_claim(), artifacts_dir=artifacts)

            preview = preview_or_write_knowledge_records(
                thread_id="rare_earth_magnets",
                purpose="test accumulation",
                artifacts_dir=artifacts,
                execute=False,
                created_at=FIXED_NOW,
            )
            self.assertTrue(preview["dry_run"])
            self.assertEqual(preview["status"], "would_write")
            self.assertFalse((artifacts / "research_knowledge_records").exists())

            written = preview_or_write_knowledge_records(
                thread_id="rare_earth_magnets",
                purpose="test accumulation",
                artifacts_dir=artifacts,
                execute=True,
                created_at=FIXED_NOW,
            )
            self.assertEqual(written["status"], "written")
            self.assertTrue(Path(written["json_path"]).exists())
            self.assertTrue(Path(written["markdown_path"]).exists())
            self.assertTrue(Path(written["archival_queue_preview_path"]).exists())
            self.assertEqual(written["live_store_mutations"], [])

            enqueued = preview_or_write_knowledge_records(
                thread_id="rare_earth_magnets",
                purpose="test accumulation",
                artifacts_dir=artifacts,
                execute=True,
                enqueue_archival=True,
                archival_queue_dir=queue,
                created_at=FIXED_NOW,
            )
            self.assertEqual(enqueued["status"], "archival_queued")
            self.assertTrue(enqueued["archival_queue_mutations"])
            self.assertTrue(all(Path(item["path"]).exists() for item in enqueued["archival_queue_mutations"]))
            job = json.loads(Path(enqueued["archival_queue_mutations"][0]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(job["agent_name"], "research_knowledge_accumulation_v1")
            self.assertEqual(enqueued["live_store_mutations"], [])

    def test_markdown_is_korean_first_accumulation_surface(self):
        record_set = build_knowledge_record_set(
            research_thread=_thread_with_pending_claim(),
            purpose="test accumulation",
            created_at=FIXED_NOW,
        )

        markdown = render_knowledge_record_set_markdown(record_set)

        self.assertIn("# Research Knowledge Records", markdown)
        self.assertIn("라이브 저장소 변경: 없음", markdown)
        self.assertIn("축적 경계", markdown)
        self.assertIn("Knowledge Records", markdown)


if __name__ == "__main__":
    unittest.main()
