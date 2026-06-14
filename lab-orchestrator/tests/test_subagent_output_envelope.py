"""Tests for dry-run-first Subagent Output Envelope planning."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_loop_packet import preview_or_write_research_loop_packet  # noqa: E402
from orchestrator.research_thread import load_research_thread, seed_research_threads  # noqa: E402
from orchestrator.subagent_output_envelope import (  # noqa: E402
    build_subagent_output_envelope,
    load_loop_packet,
    preview_or_write_subagent_output_envelope,
    render_subagent_output_envelope_markdown,
)


FIXED_NOW = "2026-06-12T02:00:00Z"
TRIGGER_SUMMARY = "서브에이전트 결과 반환 경계를 점검한다"
ENVELOPE_SUMMARY = "근거 비판 역할은 입력 packet의 계획을 검토 대상으로만 다루고, 새 문헌 주장을 만들지 않는다."


class SubagentOutputEnvelopeTests(unittest.TestCase):
    def _seed_threads(self, artifacts: Path) -> None:
        seed_research_threads(artifacts_dir=artifacts, execute=True, created_at=FIXED_NOW)

    def _write_loop_packet(self, artifacts: Path) -> Path:
        payload = preview_or_write_research_loop_packet(
            thread_id="rare_earth_magnets",
            trigger_type="on_demand",
            trigger_summary=TRIGGER_SUMMARY,
            artifacts_dir=artifacts,
            execute=True,
            created_at=FIXED_NOW,
        )
        return Path(payload["json_path"])

    def test_build_envelope_has_required_shape_without_live_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            self._seed_threads(artifacts)
            loop_packet_path = self._write_loop_packet(artifacts)
            loop_packet = load_loop_packet(loop_packet_path)

            envelope = build_subagent_output_envelope(
                loop_packet=loop_packet,
                role="Evidence Critic",
                output_type="evidence_boundary_preview",
                summary=ENVELOPE_SUMMARY,
                loop_packet_ref=str(loop_packet_path),
                missing_evidence=["아직 검토된 source ref가 없으므로 수치나 citation을 확정할 수 없다."],
                counterarguments=["역할 출력 형식만으로는 연구 품질이 좋아졌다고 볼 수 없다."],
                failure_modes=["입력 summary를 확정 evidence로 승격하면 실패한다."],
                artifact_candidates=["Coordinator 검토용 evidence boundary note 후보"],
                created_at=FIXED_NOW,
            )

            self.assertEqual(envelope["schema_version"], 2)
            self.assertEqual(envelope["planner"], "subagent_output_envelope_v2")
            self.assertEqual(envelope["thread_id"], "rare_earth_magnets")
            self.assertEqual(envelope["role"], "Evidence Critic")
            self.assertEqual(envelope["output_type"], "evidence_boundary_preview")
            self.assertEqual(envelope["live_store_mutations"], [])
            self.assertIn("context_bundle", envelope)
            self.assertEqual(envelope["critique_gate"]["status"], "requires_review")
            self.assertFalse(envelope["critique_gate"]["allows_thread_mutation"])
            self.assertEqual(envelope["artifact_co_production"]["status"], "preview_only")
            self.assertEqual(envelope["recommended_thread_patch"]["schema_version"], 2)
            self.assertEqual(envelope["recommended_thread_patch"]["thread_id"], "rare_earth_magnets")
            self.assertEqual(envelope["recommended_thread_patch"]["research_state"], "subagent_output_envelope_planned")
            self.assertIn("counterarguments", envelope["recommended_thread_patch"]["append"])
            self.assertIn("새 문헌 claim", envelope["source_boundary"]["text"])
            self.assertIn("evidence preview", " ".join(item["text"] for item in envelope["evidence_boundaries"]))

    def test_invalid_role_or_output_type_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            self._seed_threads(artifacts)
            loop_packet = load_loop_packet(self._write_loop_packet(artifacts))

            with self.assertRaisesRegex(ValueError, "role is not selected"):
                build_subagent_output_envelope(
                    loop_packet=loop_packet,
                    role="Scout",
                    output_type="source_signal_preview",
                    summary=ENVELOPE_SUMMARY,
                    loop_packet_ref="packet.json",
                )
            with self.assertRaisesRegex(ValueError, "unsupported output_type"):
                build_subagent_output_envelope(
                    loop_packet=loop_packet,
                    role="Evidence Critic",
                    output_type="next_action_plan",
                    summary=ENVELOPE_SUMMARY,
                    loop_packet_ref="packet.json",
                )

    def test_render_markdown_is_korean_first_and_reviewable(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            self._seed_threads(artifacts)
            loop_packet_path = self._write_loop_packet(artifacts)
            loop_packet = load_loop_packet(loop_packet_path)
            envelope = build_subagent_output_envelope(
                loop_packet=loop_packet,
                role="Writing",
                output_type="response_context_plan",
                summary="사용자 응답 전에 어떤 thread 맥락을 읽어야 하는지 한국어로 정리한다.",
                loop_packet_ref=str(loop_packet_path),
                created_at=FIXED_NOW,
            )

            markdown = render_subagent_output_envelope_markdown(envelope)

            self.assertIn("## 목적", markdown)
            self.assertIn("## 입력 경계", markdown)
            self.assertIn("## 역할 출력 요약", markdown)
            self.assertIn("## Critique Gate", markdown)
            self.assertIn("## Artifact Co-production", markdown)
            self.assertIn("라이브 저장소 변경: 없음", markdown)
            self.assertIn("research_thread를 직접 변경하지 않는다", markdown)

    def test_dry_run_does_not_write_or_mutate_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            self._seed_threads(artifacts)
            loop_packet_path = self._write_loop_packet(artifacts)
            before = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)

            payload = preview_or_write_subagent_output_envelope(
                loop_packet_path=loop_packet_path,
                role="Project",
                output_type="next_action_plan",
                summary="다음 행동 후보를 확정하지 않고 Coordinator 검토용 preview로만 반환한다.",
                artifacts_dir=artifacts,
                execute=False,
                created_at=FIXED_NOW,
            )

            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["status"], "would_write")
            self.assertEqual(payload["live_store_mutations"], [])
            self.assertFalse((artifacts / "subagent_output_envelopes").exists())
            after = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
            self.assertEqual(before, after)

    def test_execute_writes_envelope_and_patch_preview_without_mutating_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            self._seed_threads(artifacts)
            loop_packet_path = self._write_loop_packet(artifacts)
            before = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)

            payload = preview_or_write_subagent_output_envelope(
                loop_packet_path=loop_packet_path,
                role="Evidence Critic",
                output_type="counterargument_review",
                summary=ENVELOPE_SUMMARY,
                artifacts_dir=artifacts,
                execute=True,
                failure_modes=["counterargument가 research claim처럼 저장되면 실패한다."],
                created_at=FIXED_NOW,
            )

            self.assertFalse(payload["dry_run"])
            self.assertEqual(payload["status"], "written")
            self.assertTrue(Path(payload["json_path"]).exists())
            self.assertTrue(Path(payload["markdown_path"]).exists())
            self.assertTrue(Path(payload["patch_preview_path"]).exists())
            envelope = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
            patch = json.loads(Path(payload["patch_preview_path"]).read_text(encoding="utf-8"))
            self.assertEqual(envelope["live_store_mutations"], [])
            self.assertEqual(envelope["critique_gate"]["live_store_mutations"], [])
            self.assertEqual(patch["thread_id"], "rare_earth_magnets")
            self.assertEqual(patch["schema_version"], 2)
            self.assertIn("append", patch)
            after = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
            self.assertEqual(before, after)

    def test_cli_execute_writes_expected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            self._seed_threads(artifacts)
            loop_packet_path = self._write_loop_packet(artifacts)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ORCH_ROOT / "tools" / "subagent_output_envelope_plan.py"),
                    "--loop-packet",
                    str(loop_packet_path),
                    "--role",
                    "Project",
                    "--output-type",
                    "next_action_plan",
                    "--summary",
                    "Coordinator가 검토할 다음 행동 후보만 정리하고 실제 thread는 변경하지 않는다.",
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
            self.assertEqual(payload["status"], "written")
            self.assertEqual(payload["thread_id"], "rare_earth_magnets")
            self.assertEqual(payload["live_store_mutations"], [])
            self.assertTrue(Path(payload["json_path"]).exists())
            self.assertTrue(Path(payload["markdown_path"]).exists())
            self.assertTrue(Path(payload["patch_preview_path"]).exists())


if __name__ == "__main__":
    unittest.main()
