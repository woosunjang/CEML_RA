"""Tests for Evidence Matrix review surface artifacts."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.research_evidence_matrix import (  # noqa: E402
    build_evidence_matrix,
    preview_or_write_evidence_matrix,
    render_evidence_matrix_markdown,
)
from orchestrator.research_thread import build_seed_research_thread, write_research_thread  # noqa: E402
from orchestrator.research_thread_patch import apply_research_thread_patch  # noqa: E402


FIXED_NOW = "2026-06-17T05:00:00Z"


def _thread_with_evidence_matrix_inputs() -> dict:
    thread = build_seed_research_thread("rare_earth_magnets", created_at=FIXED_NOW)
    thread, _ = apply_research_thread_patch(
        thread,
        {
            "schema_version": 2,
            "thread_id": "rare_earth_magnets",
            "append": {
                "claims": [
                    {
                        "id": "claim.matrix.focus",
                        "text": "FSPS 기반 HRE-free 자석 후보는 proposal 검토 전에 근거 matrix가 필요하다.",
                        "status": "candidate",
                        "support_state": "needs_evidence",
                        "review_state": "pending_review",
                        "source_refs": ["source:fsps-review"],
                    }
                ],
                "evidence": [
                    {
                        "id": "evidence.matrix.support",
                        "text": "FSPS source signal은 후보 공정 검토의 출발점으로만 사용할 수 있다.",
                        "status": "candidate",
                        "support_state": "secondary_only",
                        "review_state": "pending_review",
                        "source_refs": ["source:fsps-review"],
                        "related_object_refs": ["claim:claim.matrix.focus"],
                    }
                ],
                "counterarguments": [
                    {
                        "id": "counterargument.matrix.limit",
                        "text": "공정 후보가 있더라도 coercivity와 온도 안정성 근거가 없으면 proposal-ready가 아니다.",
                        "status": "open",
                        "support_state": "needs_evidence",
                        "review_state": "pending_review",
                        "source_refs": ["source:fsps-review"],
                        "related_object_refs": ["claim:claim.matrix.focus"],
                    }
                ],
                "idea_candidates": [
                    {
                        "id": "idea.matrix.calculation",
                        "text": "HRE intensity route comparison을 계산 준비 lane 후보로 검토한다.",
                        "status": "candidate",
                        "support_state": "needs_evidence",
                        "review_state": "pending_review",
                        "metadata": {"maturity_lane": "calculation_ready"},
                    }
                ],
            },
        },
        created_at=FIXED_NOW,
    )
    return thread


class ResearchEvidenceMatrixTests(unittest.TestCase):
    def test_matrix_pairs_evidence_counterarguments_and_missing_evidence(self):
        matrix = build_evidence_matrix(
            research_thread=_thread_with_evidence_matrix_inputs(),
            trigger_type="on_demand",
            trigger_summary="matrix review",
            created_at=FIXED_NOW,
        )

        focus_row = next(row for row in matrix["rows"] if row["focus"]["id"] == "claim.matrix.focus")
        idea_row = next(row for row in matrix["rows"] if row["focus"]["id"] == "idea.matrix.calculation")

        self.assertEqual(matrix["live_store_mutations"], [])
        self.assertEqual(matrix["coverage"]["rows_with_evidence"], 1)
        self.assertEqual(matrix["coverage"]["rows_with_counterarguments"], 1)
        self.assertEqual(matrix["coverage"]["critique_gate"], "requires_review")
        self.assertEqual(focus_row["current_evidence"][0]["id"], "evidence.matrix.support")
        self.assertEqual(focus_row["counterarguments"][0]["id"], "counterargument.matrix.limit")
        self.assertTrue(focus_row["missing_evidence"])
        self.assertEqual(focus_row["recommended_review_action"]["action"], "hold_for_evidence")
        self.assertEqual(idea_row["maturity_lane"]["lane"], "calculation_ready")
        self.assertEqual(idea_row["maturity_lane"]["source"], "metadata")

    def test_recommended_patch_uses_existing_patch_shape_without_live_mutations(self):
        matrix = build_evidence_matrix(
            research_thread=_thread_with_evidence_matrix_inputs(),
            trigger_type="on_demand",
            trigger_summary="matrix review",
            created_at=FIXED_NOW,
        )
        patch = matrix["recommended_thread_patch"]

        self.assertEqual(patch["schema_version"], 2)
        self.assertEqual(patch["thread_id"], "rare_earth_magnets")
        self.assertEqual(patch["live_store_mutations"], [])
        self.assertIn("decisions", patch["append"])
        self.assertIn("failure_modes", patch["append"])
        self.assertIn("next_actions", patch["append"])
        self.assertIn("last_evidence_matrix", patch["metadata"])

    def test_preview_does_not_write_and_execute_writes_local_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            write_research_thread(_thread_with_evidence_matrix_inputs(), artifacts_dir=artifacts)

            preview = preview_or_write_evidence_matrix(
                thread_id="rare_earth_magnets",
                trigger_type="on_demand",
                trigger_summary="matrix review",
                artifacts_dir=artifacts,
                execute=False,
                created_at=FIXED_NOW,
            )
            self.assertTrue(preview["dry_run"])
            self.assertTrue(preview["read_only"])
            self.assertEqual(preview["status"], "would_write")
            self.assertFalse((artifacts / "evidence_matrices").exists())

            written = preview_or_write_evidence_matrix(
                thread_id="rare_earth_magnets",
                trigger_type="on_demand",
                trigger_summary="matrix review",
                artifacts_dir=artifacts,
                execute=True,
                created_at=FIXED_NOW,
            )
            self.assertFalse(written["dry_run"])
            self.assertEqual(written["status"], "written")
            self.assertTrue(Path(written["json_path"]).exists())
            self.assertTrue(Path(written["markdown_path"]).exists())
            self.assertTrue(Path(written["patch_preview_path"]).exists())
            stored = json.loads(Path(written["json_path"]).read_text(encoding="utf-8"))
            self.assertEqual(stored["live_store_mutations"], [])

    def test_markdown_is_korean_first_review_surface(self):
        matrix = build_evidence_matrix(
            research_thread=_thread_with_evidence_matrix_inputs(),
            trigger_type="on_demand",
            trigger_summary="matrix review",
            created_at=FIXED_NOW,
        )

        markdown = render_evidence_matrix_markdown(matrix)

        self.assertIn("# Evidence Matrix Review Surface", markdown)
        self.assertIn("라이브 저장소 변경: 없음", markdown)
        self.assertIn("검토 경계", markdown)
        self.assertIn("근거", markdown)
        self.assertIn("Recommended Thread Patch", markdown)


if __name__ == "__main__":
    unittest.main()
