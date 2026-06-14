"""Tests for the local-only Research Coordinator dry-run loop."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_coordinator import run_coordinator_dry_run  # noqa: E402
from orchestrator.research_thread import (  # noqa: E402
    DEFAULT_SEED_TOPICS,
    load_research_thread,
    seed_research_threads,
)


FIXED_NOW = "2026-06-11T02:00:00Z"


class ResearchCoordinatorTests(unittest.TestCase):
    def _make_scout_db(self, root: Path) -> Path:
        db_path = root / "paper_scout.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE papers (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                authors TEXT,
                source TEXT,
                url TEXT,
                year INTEGER,
                abstract TEXT,
                relevance_score REAL DEFAULT 0.0,
                status TEXT DEFAULT 'collected',
                analysis_json TEXT
            )
            """
        )
        rows = [
            (
                "kg1",
                "Materials ontology knowledge graph for battery data",
                json.dumps(["Kim", "Lee"]),
                "semantic_scholar",
                "https://example.com/kg1",
                2026,
                "Materials ontology knowledge graph and provenance.",
                91.5,
                "analyzed",
                json.dumps({"one_line_summary": "Candidate paper for materials KG memory design."}),
            ),
            (
                "mag1",
                "Rare earth magnets coercivity and recycling review",
                json.dumps(["Choi"]),
                "arxiv",
                "https://example.com/mag1",
                2025,
                "Rare earth magnets coercivity processing recycling.",
                88.0,
                "analyzed",
                json.dumps({"one_line_summary": "Candidate paper for magnet bottleneck review."}),
            ),
        ]
        conn.executemany(
            """
            INSERT INTO papers (
                id, title, authors, source, url, year, abstract,
                relevance_score, status, analysis_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        conn.close()
        return db_path

    def _seed_threads(self, artifacts: Path) -> None:
        seed_research_threads(artifacts_dir=artifacts, execute=True, created_at=FIXED_NOW)

    def _paper_count(self, db_path: Path) -> int:
        conn = sqlite3.connect(db_path)
        try:
            return conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        finally:
            conn.close()

    def test_dry_run_advances_both_threads_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            db_path = self._make_scout_db(root)
            self._seed_threads(artifacts)
            before = {
                topic: load_research_thread(topic, artifacts_dir=artifacts)
                for topic in DEFAULT_SEED_TOPICS
            }

            payload = run_coordinator_dry_run(
                artifacts_dir=artifacts,
                db_path=db_path,
                execute=False,
                created_at=FIXED_NOW,
            )

            self.assertTrue(payload["dry_run"])
            self.assertEqual([item["thread_id"] for item in payload["threads"]], list(DEFAULT_SEED_TOPICS))
            self.assertEqual([item["status"] for item in payload["threads"]], ["would_update", "would_update"])
            for result in payload["threads"]:
                self.assertIn("context_bundle", result)
                self.assertIn("loop_packet", result)
                self.assertIn("evidence_critic_envelope", result)
                self.assertIn("merged_thread_patch_preview", result)
                self.assertEqual(result["context_bundle"]["live_store_mutations"], [])
                self.assertEqual(result["loop_packet"]["live_store_mutations"], [])
                self.assertEqual(result["evidence_critic_envelope"]["critique_gate"]["status"], "requires_review")
                self.assertEqual(result["merged_thread_patch_preview"]["schema_version"], 2)
            for topic in DEFAULT_SEED_TOPICS:
                self.assertEqual(before[topic], load_research_thread(topic, artifacts_dir=artifacts))
            self.assertEqual(self._paper_count(db_path), 2)
            self.assertEqual(payload["live_store_mutations"], [])

    def test_execute_updates_both_threads_through_full_stage_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            db_path = self._make_scout_db(root)
            self._seed_threads(artifacts)

            payload = run_coordinator_dry_run(
                artifacts_dir=artifacts,
                db_path=db_path,
                execute=True,
                created_at=FIXED_NOW,
            )

            self.assertFalse(payload["dry_run"])
            self.assertEqual(payload["stage_order"], ["scout", "evidence_synthesis", "idea_candidate", "critique", "next_action"])
            for result in payload["threads"]:
                self.assertEqual(result["status"], "updated")
                self.assertGreaterEqual(result["stages"]["scout"]["evidence_added"], 1)

            for topic in DEFAULT_SEED_TOPICS:
                thread = load_research_thread(topic, artifacts_dir=artifacts)
                self.assertEqual(thread["research_state"], "coordinator_dry_run_completed")
                self.assertGreaterEqual(len(thread["evidence"]), 1)
                self.assertTrue(any(item["id"] == "coordinator.claim.evidence_preview_ready" for item in thread["claims"]))
                self.assertTrue(any(item["id"] == "coordinator.idea.first_comparison" for item in thread["idea_candidates"]))
                self.assertTrue(any(item["id"] == "coordinator.counterargument.source_metadata_only" for item in thread["counterarguments"]))
                self.assertTrue(any(item["id"] == "coordinator.failure_mode.thread_drift" for item in thread["failure_modes"]))
                self.assertTrue(any(item["id"] == "coordinator.next_action.first_review_step" for item in thread["next_actions"]))
                self.assertEqual(thread["metadata"]["last_coordinator_dry_run"]["live_store_mutations"], [])
            self.assertEqual(self._paper_count(db_path), 2)

    def test_execute_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            db_path = self._make_scout_db(root)
            self._seed_threads(artifacts)

            run_coordinator_dry_run(
                artifacts_dir=artifacts,
                db_path=db_path,
                execute=True,
                created_at=FIXED_NOW,
            )
            second = run_coordinator_dry_run(
                artifacts_dir=artifacts,
                db_path=db_path,
                execute=True,
                created_at=FIXED_NOW,
            )

            self.assertEqual([item["status"] for item in second["threads"]], ["no_changes", "no_changes"])
            for topic in DEFAULT_SEED_TOPICS:
                thread = load_research_thread(topic, artifacts_dir=artifacts)
                self.assertEqual(len([item for item in thread["claims"] if item["id"] == "coordinator.claim.evidence_preview_ready"]), 1)

    def test_cli_execute_updates_both_default_topics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            db_path = self._make_scout_db(root)
            self._seed_threads(artifacts)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ORCH_ROOT / "tools" / "research_coordinator_dry_run.py"),
                    "--artifacts-dir",
                    str(artifacts),
                    "--db-path",
                    str(db_path),
                    "--execute",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(proc.stdout)

            self.assertFalse(payload["dry_run"])
            self.assertEqual([item["thread_id"] for item in payload["threads"]], list(DEFAULT_SEED_TOPICS))
            for topic in DEFAULT_SEED_TOPICS:
                thread = load_research_thread(topic, artifacts_dir=artifacts)
                self.assertEqual(thread["research_state"], "coordinator_dry_run_completed")


if __name__ == "__main__":
    unittest.main()
