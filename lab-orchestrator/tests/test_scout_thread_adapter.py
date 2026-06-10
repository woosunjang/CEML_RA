"""Tests for read-only Scout evidence to research_thread adapter."""

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

from orchestrator.research_thread import (  # noqa: E402
    build_seed_research_thread,
    load_research_thread,
    write_research_thread,
)
from orchestrator.scout_thread_adapter import (  # noqa: E402
    preview_or_apply_scout_evidence,
)


FIXED_NOW = "2026-06-11T01:00:00Z"


class ScoutThreadAdapterTests(unittest.TestCase):
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
                "p1",
                "Materials ontology knowledge graph for battery data",
                json.dumps(["Kim", "Lee"]),
                "semantic_scholar",
                "https://example.com/p1",
                2026,
                "Materials ontology knowledge graph and provenance.",
                91.5,
                "analyzed",
                json.dumps({
                    "one_line_summary": "Candidate paper for materials KG memory design.",
                    "tags": ["Knowledge Graph", "Ontology"],
                }),
            ),
            (
                "p2",
                "Unrelated low score paper",
                json.dumps(["Park"]),
                "arxiv",
                "https://example.com/p2",
                2025,
                "Materials ontology knowledge graph side note.",
                20.0,
                "analyzed",
                json.dumps({"one_line_summary": "Low score item."}),
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

    def _seed_thread(self, artifacts: Path, thread_id: str = "materials_ontology_kg") -> None:
        thread = build_seed_research_thread(thread_id, created_at=FIXED_NOW)
        write_research_thread(thread, artifacts_dir=artifacts)

    def _paper_count(self, db_path: Path) -> int:
        conn = sqlite3.connect(db_path)
        try:
            return conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        finally:
            conn.close()

    def test_dry_run_builds_patch_without_writing_thread_or_scout_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            db_path = self._make_scout_db(root)
            self._seed_thread(artifacts)

            before = load_research_thread("materials_ontology_kg", artifacts_dir=artifacts)
            payload = preview_or_apply_scout_evidence(
                thread_id="materials_ontology_kg",
                artifacts_dir=artifacts,
                db_path=db_path,
                query="materials ontology knowledge graph",
                execute=False,
                created_at=FIXED_NOW,
            )
            after = load_research_thread("materials_ontology_kg", artifacts_dir=artifacts)

            self.assertEqual(payload["status"], "would_update")
            self.assertTrue(payload["dry_run"])
            self.assertEqual(len(payload["patch"]["source_signals"]), 1)
            self.assertEqual(len(payload["patch"]["evidence"]), 1)
            self.assertEqual(before, after)
            self.assertEqual(self._paper_count(db_path), 2)
            self.assertEqual(payload["live_store_mutations"], [])

    def test_execute_updates_thread_artifacts_without_claims_or_live_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            db_path = self._make_scout_db(root)
            self._seed_thread(artifacts)

            payload = preview_or_apply_scout_evidence(
                thread_id="materials_ontology_kg",
                artifacts_dir=artifacts,
                db_path=db_path,
                query="materials ontology knowledge graph",
                execute=True,
                created_at=FIXED_NOW,
            )
            thread = load_research_thread("materials_ontology_kg", artifacts_dir=artifacts)

            self.assertEqual(payload["status"], "updated")
            self.assertEqual(thread["research_state"], "scout_evidence_previewed")
            self.assertEqual(thread["claims"], [])
            self.assertEqual(len(thread["evidence"]), 1)
            self.assertIn("needs_review", thread["evidence"][0]["status"])
            self.assertEqual(thread["metadata"]["last_scout_adapter_run"]["live_store_mutations"], [])
            self.assertEqual(self._paper_count(db_path), 2)

    def test_execute_is_idempotent_for_existing_scout_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            db_path = self._make_scout_db(root)
            self._seed_thread(artifacts)

            preview_or_apply_scout_evidence(
                thread_id="materials_ontology_kg",
                artifacts_dir=artifacts,
                db_path=db_path,
                query="materials ontology knowledge graph",
                execute=True,
                created_at=FIXED_NOW,
            )
            second = preview_or_apply_scout_evidence(
                thread_id="materials_ontology_kg",
                artifacts_dir=artifacts,
                db_path=db_path,
                query="materials ontology knowledge graph",
                execute=True,
                created_at=FIXED_NOW,
            )
            thread = load_research_thread("materials_ontology_kg", artifacts_dir=artifacts)

            self.assertEqual(second["status"], "no_changes")
            self.assertEqual(second["patch"]["duplicates"]["evidence"], 1)
            self.assertEqual(len(thread["evidence"]), 1)

    def test_cli_defaults_to_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            db_path = self._make_scout_db(root)
            self._seed_thread(artifacts)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ORCH_ROOT / "tools" / "scout_evidence_to_thread.py"),
                    "--thread-id",
                    "materials_ontology_kg",
                    "--query",
                    "materials ontology knowledge graph",
                    "--artifacts-dir",
                    str(artifacts),
                    "--db-path",
                    str(db_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(proc.stdout)
            thread = load_research_thread("materials_ontology_kg", artifacts_dir=artifacts)

            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["status"], "would_update")
            self.assertEqual(thread["evidence"], [])


if __name__ == "__main__":
    unittest.main()
