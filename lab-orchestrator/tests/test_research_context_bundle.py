"""Tests for shared Research Context Bundle planning."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_context_bundle import (  # noqa: E402
    build_research_context_bundle,
    preview_or_write_research_context_bundle,
    render_research_context_bundle_markdown,
)
from orchestrator.research_thread import build_seed_research_thread, research_thread_paths, write_research_thread  # noqa: E402
from orchestrator.research_thread_patch import apply_research_thread_patch  # noqa: E402


FIXED_NOW = "2026-06-15T00:00:00Z"


class ResearchContextBundleTests(unittest.TestCase):
    def test_bundle_is_shared_for_automatic_and_on_demand_triggers(self):
        thread = build_seed_research_thread("rare_earth_magnets", created_at=FIXED_NOW)
        thread, _ = apply_research_thread_patch(
            thread,
            {
                "schema_version": 2,
                "append": {
                    "claims": [
                        {
                            "id": "claim.test.needs_evidence",
                            "text": "HRE 저감 아이디어는 아직 근거 검토가 필요하다.",
                            "status": "candidate",
                            "support_state": "needs_evidence",
                            "review_state": "pending_review",
                            "source_refs": ["source:test-paper"],
                        }
                    ],
                    "evidence": [
                        {
                            "id": "evidence.test.preview",
                            "text": "테스트용 evidence preview다.",
                            "status": "candidate",
                            "support_state": "not_evaluated",
                            "review_state": "pending_review",
                            "source_refs": ["source:test-paper"],
                        }
                    ],
                },
            },
            created_at=FIXED_NOW,
        )

        automatic = build_research_context_bundle(
            research_thread=thread,
            trigger_type="automatic",
            trigger_summary="weekly synthesis",
            created_at=FIXED_NOW,
        )
        on_demand = build_research_context_bundle(
            research_thread=thread,
            trigger_type="on_demand",
            trigger_summary="proposal discussion",
            created_at=FIXED_NOW,
        )

        self.assertEqual(automatic["thread_summary"]["thread_id"], on_demand["thread_summary"]["thread_id"])
        self.assertEqual(automatic["thread_summary"]["section_counts"], on_demand["thread_summary"]["section_counts"])
        self.assertEqual(automatic["live_store_mutations"], [])
        self.assertEqual(on_demand["live_store_mutations"], [])
        self.assertTrue(automatic["weak_claims"])
        self.assertTrue(any(item["source_ref"] == "source:test-paper" for item in automatic["retrieval_candidates"]))
        self.assertEqual(automatic["activation_previews"]["kg_ingest_preview"]["status"], "preview_only")
        self.assertIn("approval_boundary", automatic["activation_previews"]["kg_ingest_preview"])
        self.assertIn("approval_boundary", automatic["activation_previews"]["rag_retrieval_preview"])
        self.assertIn("approval_boundary", automatic["activation_previews"]["slack_discussion_preview"])
        self.assertEqual(on_demand["activation_previews"]["slack_discussion_preview"]["thread_id"], "rare_earth_magnets")

    def test_preview_does_not_write_and_execute_writes_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            thread = build_seed_research_thread("materials_ontology_kg", created_at=FIXED_NOW)
            write_research_thread(thread, artifacts_dir=artifacts)

            preview = preview_or_write_research_context_bundle(
                thread_id="materials_ontology_kg",
                trigger_type="automatic",
                trigger_summary="weekly synthesis",
                artifacts_dir=artifacts,
                execute=False,
                created_at=FIXED_NOW,
            )

            self.assertTrue(preview["dry_run"])
            self.assertEqual(preview["status"], "would_write")
            self.assertFalse((artifacts / "research_context_bundles").exists())

            written = preview_or_write_research_context_bundle(
                thread_id="materials_ontology_kg",
                trigger_type="automatic",
                trigger_summary="weekly synthesis",
                artifacts_dir=artifacts,
                execute=True,
                created_at=FIXED_NOW,
            )

            self.assertFalse(written["dry_run"])
            self.assertEqual(written["status"], "written")
            self.assertTrue(Path(written["json_path"]).exists())
            self.assertTrue(Path(written["markdown_path"]).exists())
            stored = json.loads(Path(written["json_path"]).read_text(encoding="utf-8"))
            self.assertEqual(stored["live_store_mutations"], [])

    def test_markdown_is_korean_first_review_surface(self):
        thread = build_seed_research_thread("rare_earth_magnets", created_at=FIXED_NOW)
        bundle = build_research_context_bundle(
            research_thread=thread,
            trigger_type="on_demand",
            trigger_summary="사용자 토론",
            created_at=FIXED_NOW,
        )

        markdown = render_research_context_bundle_markdown(bundle)

        self.assertIn("# Research Context Bundle", markdown)
        self.assertIn("라이브 저장소 변경: 없음", markdown)
        self.assertIn("Relevant Objects", markdown)
        self.assertIn("Activation Previews", markdown)

    def test_cli_defaults_to_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            write_research_thread(
                build_seed_research_thread("materials_ontology_kg", created_at=FIXED_NOW),
                artifacts_dir=artifacts,
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ORCH_ROOT / "tools" / "research_context_bundle_plan.py"),
                    "--artifacts-dir",
                    str(artifacts),
                    "--thread-id",
                    "materials_ontology_kg",
                    "--trigger-type",
                    "automatic",
                    "--trigger-summary",
                    "weekly synthesis",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(proc.stdout)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["status"], "would_write")
            self.assertFalse((artifacts / "research_context_bundles").exists())


if __name__ == "__main__":
    unittest.main()
