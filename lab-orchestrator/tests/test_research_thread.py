"""Tests for Phase 1 research_thread durable artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_thread import (  # noqa: E402
    DEFAULT_SEED_TOPICS,
    build_seed_research_thread,
    list_research_threads,
    load_research_thread,
    research_thread_paths,
    render_research_thread_markdown,
    seed_research_threads,
    validate_research_thread,
    write_research_thread,
)
from orchestrator.research_thread_patch import (  # noqa: E402
    apply_research_thread_patch,
    preview_or_apply_research_thread_patch,
)


FIXED_NOW = "2026-06-11T00:00:00Z"


class ResearchThreadTests(unittest.TestCase):
    def test_seed_thread_schema_has_required_sections_without_fake_evidence(self):
        thread = build_seed_research_thread("materials_ontology_kg", created_at=FIXED_NOW)

        validate_research_thread(thread)
        self.assertEqual(thread["schema_version"], 1)
        self.assertEqual(thread["thread_id"], "materials_ontology_kg")
        self.assertEqual(thread["claims"], [])
        self.assertEqual(thread["evidence"], [])
        self.assertFalse(thread["metadata"]["contains_literature_claims"])
        self.assertEqual(len(thread["next_actions"]), 3)
        self.assertIn("ground contract", thread["source_signals"][0]["text"])

    def test_render_markdown_is_human_readable(self):
        thread = build_seed_research_thread("rare_earth_magnets", created_at=FIXED_NOW)

        markdown = render_research_thread_markdown(thread)

        self.assertIn("# Research Thread: rare_earth_magnets", markdown)
        self.assertIn("## Evidence", markdown)
        self.assertIn("_None recorded yet._", markdown)
        self.assertIn("No KG ingest is proposed", markdown)

    def test_dry_run_does_not_write_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"

            payload = seed_research_threads(
                artifacts_dir=artifacts,
                execute=False,
                created_at=FIXED_NOW,
            )

            self.assertTrue(payload["dry_run"])
            self.assertEqual(
                [item["thread_id"] for item in payload["threads"]],
                list(DEFAULT_SEED_TOPICS),
            )
            self.assertEqual([item["status"] for item in payload["threads"]], ["would_create", "would_create"])
            self.assertFalse((artifacts / "research_threads").exists())

    def test_execute_writes_json_and_markdown_then_reader_loads_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"

            payload = seed_research_threads(
                artifacts_dir=artifacts,
                execute=True,
                created_at=FIXED_NOW,
            )

            self.assertFalse(payload["dry_run"])
            self.assertEqual([item["status"] for item in payload["threads"]], ["created", "created"])
            for topic in DEFAULT_SEED_TOPICS:
                paths = research_thread_paths(topic, artifacts)
                self.assertTrue(paths.json_path.exists())
                self.assertTrue(paths.markdown_path.exists())
                loaded = load_research_thread(topic, artifacts_dir=artifacts)
                self.assertEqual(loaded["thread_id"], topic)
                self.assertEqual(loaded["evidence"], [])
                self.assertIn("Research Thread", paths.markdown_path.read_text(encoding="utf-8"))

            listed = list_research_threads(artifacts_dir=artifacts)
            self.assertEqual([item["thread_id"] for item in listed], list(DEFAULT_SEED_TOPICS))

    def test_existing_thread_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            thread = build_seed_research_thread("materials_ontology_kg", created_at=FIXED_NOW)

            first = write_research_thread(thread, artifacts_dir=artifacts)
            self.assertEqual(first["status"], "created")
            paths = research_thread_paths("materials_ontology_kg", artifacts)
            original = json.loads(paths.json_path.read_text(encoding="utf-8"))
            original["research_state"] = "manually-edited"
            paths.json_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

            second = write_research_thread(thread, artifacts_dir=artifacts)

            self.assertEqual(second["status"], "exists")
            stored = json.loads(paths.json_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["research_state"], "manually-edited")

    def test_cli_defaults_to_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ORCH_ROOT / "tools" / "seed_research_threads.py"),
                    "--artifacts-dir",
                    str(artifacts),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(proc.stdout)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(len(payload["threads"]), 2)
            self.assertFalse((artifacts / "research_threads").exists())

    def test_cli_execute_writes_default_topics(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ORCH_ROOT / "tools" / "seed_research_threads.py"),
                    "--artifacts-dir",
                    str(artifacts),
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
                self.assertTrue((artifacts / "research_threads" / f"{topic}.json").exists())
                self.assertTrue((artifacts / "research_threads" / f"{topic}.md").exists())

    def test_research_thread_patch_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            seed_research_threads(artifacts_dir=artifacts, execute=True, created_at=FIXED_NOW)
            before = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
            patch = {
                "schema_version": 1,
                "thread_id": "rare_earth_magnets",
                "research_state": "proposal_seed_ready",
                "append": {
                    "decisions": [
                        {
                            "id": "decision.test.patch_cli",
                            "text": "패치 CLI dry-run 검증을 위해 추가되는 결정이다.",
                            "status": "accepted",
                            "confidence": "test",
                            "tags": ["patch-cli"],
                        }
                    ]
                },
            }

            payload = preview_or_apply_research_thread_patch(
                thread_id="rare_earth_magnets",
                patch=patch,
                artifacts_dir=artifacts,
                execute=False,
                created_at=FIXED_NOW,
            )

            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["status"], "would_update")
            self.assertEqual(payload["live_store_mutations"], [])
            self.assertIn("패치 CLI", payload["preview_markdown"])
            after = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
            self.assertEqual(before, after)

    def test_research_thread_patch_execute_appends_and_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            seed_research_threads(artifacts_dir=artifacts, execute=True, created_at=FIXED_NOW)
            patch = {
                "schema_version": 1,
                "thread_id": "rare_earth_magnets",
                "research_state": "proposal_seed_ready",
                "append": {
                    "decisions": [
                        {
                            "id": "decision.test.patch_cli_execute",
                            "text": "패치 CLI execute 검증 결정이다.",
                            "status": "accepted",
                            "confidence": "test",
                        }
                    ],
                    "failure_modes": [
                        {
                            "id": "failure_mode.test.patch_cli_execute",
                            "text": "패치 CLI 검증 실패 모드다.",
                            "status": "open",
                        }
                    ],
                },
                "updates": {
                    "next_actions": [
                        {
                            "id": "next_action.q1",
                            "status": "completed",
                            "metadata": {"completed_by": "research_thread_patch_cli_test"},
                        }
                    ]
                },
                "metadata": {"last_patch_cli_test": FIXED_NOW},
            }

            payload = preview_or_apply_research_thread_patch(
                thread_id="rare_earth_magnets",
                patch=patch,
                artifacts_dir=artifacts,
                execute=True,
                created_at=FIXED_NOW,
            )

            self.assertFalse(payload["dry_run"])
            self.assertEqual(payload["status"], "updated")
            thread = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
            self.assertEqual(thread["research_state"], "proposal_seed_ready")
            self.assertTrue(any(item["id"] == "decision.test.patch_cli_execute" for item in thread["decisions"]))
            self.assertTrue(any(item["id"] == "failure_mode.test.patch_cli_execute" for item in thread["failure_modes"]))
            q1 = next(item for item in thread["next_actions"] if item["id"] == "next_action.q1")
            self.assertEqual(q1["status"], "completed")
            self.assertEqual(q1["metadata"]["completed_by"], "research_thread_patch_cli_test")
            self.assertEqual(thread["metadata"]["last_patch_cli_test"], FIXED_NOW)
            self.assertIn("패치 CLI execute", (artifacts / "research_threads" / "rare_earth_magnets.md").read_text(encoding="utf-8"))

    def test_research_thread_patch_rejects_duplicate_append_id(self):
        thread = build_seed_research_thread("rare_earth_magnets", created_at=FIXED_NOW)
        patch = {
            "append": {
                "decisions": [
                    {
                        "id": "decision.seed_first_proof_loop",
                        "text": "이미 존재하는 결정 ID다.",
                        "status": "accepted",
                    }
                ]
            }
        }

        with self.assertRaisesRegex(ValueError, "duplicate item id"):
            apply_research_thread_patch(thread, patch, created_at=FIXED_NOW)

    def test_research_thread_patch_rejects_invalid_section(self):
        thread = build_seed_research_thread("rare_earth_magnets", created_at=FIXED_NOW)
        patch = {
            "append": {
                "claims": [
                    {
                        "id": "claim.not.allowed",
                        "text": "v1 patch CLI에서는 claims를 직접 패치하지 않는다.",
                        "status": "candidate",
                    }
                ]
            }
        }

        with self.assertRaisesRegex(ValueError, "unsupported patch section"):
            apply_research_thread_patch(thread, patch, created_at=FIXED_NOW)

    def test_research_thread_patch_cli_defaults_to_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            seed_research_threads(artifacts_dir=artifacts, execute=True, created_at=FIXED_NOW)
            patch_path = Path(tmp) / "patch.json"
            patch_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "thread_id": "rare_earth_magnets",
                        "append": {
                            "decisions": [
                                {
                                    "id": "decision.test.patch_cli_subprocess",
                                    "text": "CLI dry-run 검증 결정이다.",
                                    "status": "accepted",
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ORCH_ROOT / "tools" / "research_thread_patch.py"),
                    "--artifacts-dir",
                    str(artifacts),
                    "--thread-id",
                    "rare_earth_magnets",
                    "--patch-file",
                    str(patch_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(proc.stdout)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["status"], "would_update")
            thread = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
            self.assertFalse(any(item["id"] == "decision.test.patch_cli_subprocess" for item in thread["decisions"]))


if __name__ == "__main__":
    unittest.main()
