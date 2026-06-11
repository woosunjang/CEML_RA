"""Tests for research work-package execution packet planning."""

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
    load_research_thread,
    seed_research_threads,
)
from orchestrator.research_work_package import (  # noqa: E402
    build_work_package_execution_packet,
    preview_or_write_work_package_plan,
    render_work_package_markdown,
    work_package_id_from_title,
)


FIXED_NOW = "2026-06-11T14:00:00Z"


def _proposal_seed() -> dict:
    return {
        "schema_version": 1,
        "topic_id": "rare_earth_magnets",
        "prior_reviewed_memory": {
            "proposal_seed": "/tmp/proposal_seed.md",
            "route_ranking_sheet": "/tmp/route_ranking.md",
        },
        "work_packages": [
            {
                "title": "WP1. HRE 사용 강도 정규화 route 비교",
                "output": "제안서 검토용 route 비교표",
            },
            {
                "title": "WP2. 계산 스코핑용 descriptor table",
                "output": "불확실성과 unavailable-field flag를 포함한 계산 스코핑용 descriptor table",
            },
            {
                "title": "WP3. HRE-use caveat가 붙은 circularity appendix",
                "output": "Br, BHmax, HcJ, renewed GBD, added-Tb caveat를 기록한 공급/circularity 맥락 노트",
            },
        ],
        "next_actions": [
            "FSPS, GBD, recycling-linked route의 HRE-intensity table을 만든다.",
            "KG ingest preview 전에 digital twin/ML descriptor table을 먼저 만든다.",
        ],
        "do_not_claim": [
            "missing value를 negative proof로 취급하지 않는다.",
            "Tb-Ga GBD sample의 최종 Br/BHmax 숫자를 추정하지 않는다.",
        ],
        "missing_evidence": [
            {
                "gap": "Coercivity gain 대비 HRE 사용 강도",
                "why_it_matters": "HRE-lean route와 merely HRE-using route를 구분해야 한다.",
                "next_validation": "Tb/Dy mass fraction, route input, Hcj gain을 정규화한다.",
            },
            {
                "gap": "Digital twin/ML descriptor availability",
                "why_it_matters": "Calculation scoping을 실제 작업으로 만들기 위해 필요하다.",
                "next_validation": "confirmed, not_found, missing value status를 포함한 descriptor table을 만든다.",
            },
        ],
    }


class ResearchWorkPackageTests(unittest.TestCase):
    def _write_seed(self, root: Path) -> Path:
        path = root / "proposal_seed.json"
        path.write_text(json.dumps(_proposal_seed(), ensure_ascii=False), encoding="utf-8")
        return path

    def _seed_threads(self, artifacts: Path) -> None:
        seed_research_threads(artifacts_dir=artifacts, execute=True, created_at=FIXED_NOW)

    def test_work_package_id_from_title_is_stable_for_hre_package(self):
        self.assertEqual(
            work_package_id_from_title("WP1. HRE 사용 강도 정규화 route 비교"),
            "hre_intensity_route_comparison",
        )

    def test_build_packet_selects_hre_package_without_creating_research_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            self._seed_threads(artifacts)
            thread = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
            packet = build_work_package_execution_packet(
                proposal_seed=_proposal_seed(),
                research_thread=thread,
                proposal_seed_path=root / "proposal_seed.json",
                created_at=FIXED_NOW,
            )

            self.assertEqual(packet["selected_work_package"]["id"], "hre_intensity_route_comparison")
            self.assertEqual(packet["artifact_contract"]["artifact_type"], "hre_intensity_table")
            self.assertEqual(packet["live_store_mutations"], [])
            self.assertIn("thread_patch_preview", packet)
            self.assertIn("빠진 값을 실패 증거", " ".join(packet["artifact_contract"]["must_not_do"]))
            self.assertFalse(any("새로운 수치" in item for item in packet["artifact_contract"]["must_include"]))

    def test_render_markdown_is_korean_first_and_includes_required_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            self._seed_threads(artifacts)
            thread = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
            packet = build_work_package_execution_packet(
                proposal_seed=_proposal_seed(),
                research_thread=thread,
                proposal_seed_path=root / "proposal_seed.json",
                created_at=FIXED_NOW,
            )

            markdown = render_work_package_markdown(packet)

            self.assertIn("연구 Work Package 실행 패킷", markdown)
            self.assertIn("선택된 작업 패키지", markdown)
            self.assertIn("왜 이 작업인가", markdown)
            self.assertIn("Artifact Contract", markdown)
            self.assertIn("Stop Conditions", markdown)
            self.assertIn("Thread Patch Preview", markdown)

    def test_dry_run_does_not_write_files_or_mutate_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            self._seed_threads(artifacts)
            seed_path = self._write_seed(root)
            before = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)

            payload = preview_or_write_work_package_plan(
                proposal_seed_path=seed_path,
                thread_id="rare_earth_magnets",
                artifacts_dir=artifacts,
                execute=False,
                created_at=FIXED_NOW,
            )

            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["status"], "would_write")
            self.assertEqual(payload["live_store_mutations"], [])
            self.assertFalse((artifacts / "research_work_packages").exists())
            after = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
            self.assertEqual(before, after)

    def test_execute_writes_packet_and_patch_preview_without_mutating_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            self._seed_threads(artifacts)
            seed_path = self._write_seed(root)
            before = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)

            payload = preview_or_write_work_package_plan(
                proposal_seed_path=seed_path,
                thread_id="rare_earth_magnets",
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
            self.assertEqual(packet["selected_work_package"]["id"], "hre_intensity_route_comparison")
            patch = json.loads(Path(payload["patch_preview_path"]).read_text(encoding="utf-8"))
            self.assertEqual(patch["thread_id"], "rare_earth_magnets")
            after = load_research_thread("rare_earth_magnets", artifacts_dir=artifacts)
            self.assertEqual(before, after)

    def test_cli_execute_writes_expected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            self._seed_threads(artifacts)
            seed_path = self._write_seed(root)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ORCH_ROOT / "tools" / "research_work_package_plan.py"),
                    "--proposal-seed",
                    str(seed_path),
                    "--thread-id",
                    "rare_earth_magnets",
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
            self.assertEqual(payload["selected_work_package_id"], "hre_intensity_route_comparison")
            self.assertTrue(Path(payload["json_path"]).exists())
            self.assertTrue(Path(payload["markdown_path"]).exists())
            self.assertTrue(Path(payload["patch_preview_path"]).exists())


if __name__ == "__main__":
    unittest.main()
