"""Tests for dry-run-first Research Loop Packet planning."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_loop_packet import (  # noqa: E402
    build_research_loop_packet,
    preview_or_write_research_loop_packet,
    render_research_loop_packet_markdown,
)
from orchestrator.research_thread import (  # noqa: E402
    load_research_thread,
    seed_research_threads,
)


FIXED_NOW = "2026-06-12T01:00:00Z"
TRIGGER_SUMMARY = "다음 연구 루프를 구조화한다"


class ResearchLoopPacketTests(unittest.TestCase):
    def _seed_threads(self, artifacts: Path) -> None:
        seed_research_threads(artifacts_dir=artifacts, execute=True, created_at=FIXED_NOW)

    def test_build_packet_has_required_shape_without_research_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            self._seed_threads(artifacts)
            thread = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)

            packet = build_research_loop_packet(
                research_thread=thread,
                trigger_type="on_demand",
                trigger_summary=TRIGGER_SUMMARY,
                created_at=FIXED_NOW,
            )

            self.assertEqual(packet["schema_version"], 1)
            self.assertEqual(packet["thread_id"], "rare_earth_magnets")
            self.assertEqual(packet["trigger"]["type"], "on_demand")
            self.assertEqual(packet["live_store_mutations"], [])
            self.assertIn("selected_roles", packet)
            self.assertIn("expected_outputs", packet)
            self.assertIn("stop_conditions", packet)
            self.assertIn("artifact_candidates", packet)
            self.assertIn("thread_patch_preview", packet)
            self.assertIn("새 연구 claim", " ".join(packet["stop_conditions"]))
            self.assertEqual(packet["thread_patch_preview"]["research_state"], "loop_packet_planned")

    def test_render_markdown_is_korean_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            self._seed_threads(artifacts)
            thread = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
            packet = build_research_loop_packet(
                research_thread=thread,
                trigger_type="automatic",
                trigger_summary=TRIGGER_SUMMARY,
                created_at=FIXED_NOW,
            )

            markdown = render_research_loop_packet_markdown(packet)

            self.assertIn("## 목적", markdown)
            self.assertIn("## Selected Roles", markdown)
            self.assertIn("라이브 저장소 변경: 없음", markdown)
            self.assertIn("새 연구 claim", markdown)

    def test_dry_run_does_not_write_or_mutate_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            self._seed_threads(artifacts)
            before = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)

            payload = preview_or_write_research_loop_packet(
                thread_id="rare_earth_magnets",
                trigger_type="on_demand",
                trigger_summary=TRIGGER_SUMMARY,
                artifacts_dir=artifacts,
                execute=False,
                created_at=FIXED_NOW,
            )

            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["status"], "would_write")
            self.assertEqual(payload["live_store_mutations"], [])
            self.assertFalse((artifacts / "research_loop_packets").exists())
            after = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
            self.assertEqual(before, after)

    def test_execute_writes_packet_and_patch_preview_without_mutating_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            self._seed_threads(artifacts)
            before = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)

            payload = preview_or_write_research_loop_packet(
                thread_id="rare_earth_magnets",
                trigger_type="on_demand",
                trigger_summary=TRIGGER_SUMMARY,
                artifacts_dir=artifacts,
                execute=True,
                created_at=FIXED_NOW,
            )

            self.assertFalse(payload["dry_run"])
            self.assertEqual(payload["status"], "written")
            self.assertTrue(Path(payload["json_path"]).exists())
            self.assertTrue(Path(payload["markdown_path"]).exists())
            self.assertTrue(Path(payload["patch_preview_path"]).exists())
            packet = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
            patch = json.loads(Path(payload["patch_preview_path"]).read_text(encoding="utf-8"))
            self.assertEqual(packet["live_store_mutations"], [])
            self.assertEqual(patch["thread_id"], "rare_earth_magnets")
            after = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
            self.assertEqual(before, after)

    def test_cli_execute_writes_expected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            self._seed_threads(artifacts)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ORCH_ROOT / "tools" / "research_loop_packet_plan.py"),
                    "--thread-id",
                    "rare_earth_magnets",
                    "--trigger-type",
                    "on_demand",
                    "--trigger-summary",
                    TRIGGER_SUMMARY,
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
            self.assertEqual(payload["thread_id"], "rare_earth_magnets")
            self.assertEqual(payload["live_store_mutations"], [])
            self.assertTrue(Path(payload["json_path"]).exists())
            self.assertTrue(Path(payload["markdown_path"]).exists())
            self.assertTrue(Path(payload["patch_preview_path"]).exists())


if __name__ == "__main__":
    unittest.main()
