"""Tests for On-demand Research Question Loop v0."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

import orchestrator.research_thread as research_thread  # noqa: E402
from api.server import app  # noqa: E402
from integrations.qdrant import memory_note_chunk_id  # noqa: E402
from orchestrator.research_question_loop import preview_or_run_question_loop  # noqa: E402
from orchestrator.research_thread import load_research_thread, seed_research_threads  # noqa: E402
from orchestrator.research_weekly_loop import preview_or_run_weekly_loop  # noqa: E402


FIXED_NOW = "2026-07-01T09:00:00Z"


class _RagMemoryResult:
    score = 0.55
    payload = {
        "chunk_id": "research_memory_note:materials_ontology_kg:prior_question_chunk",
        "title": "Weekly research memory note: materials_ontology_kg",
        "text": "이전 on-demand memory note가 RAG에서 검색되었다.",
        "artifact_ref": "research_memory_notes/materials_ontology_kg/prior.md",
        "document_type": "research_memory_note",
        "memory_note_id": "prior_question_chunk",
    }


def _scout_search(query: str, limit: int, days: int) -> list[dict]:
    return [
        {
            "id": "paper-1",
            "title": "Question-driven materials ontology KG evaluation",
            "summary": "질문 기반 KG/RAG 평가에서는 provenance와 benchmark 경계가 중요하다.",
            "url": "https://example.com/question-paper",
            "relevance_score": 88,
        }
    ][:limit]


def _rag_memory_search(query: str, limit: int, days: int) -> list[_RagMemoryResult]:
    return [_RagMemoryResult()][:limit]


async def _kg_search(query: str, limit: int) -> list[dict]:
    return [{"uuid": "kg-1", "fact": "질문 기반 루프는 기억 재사용과 새 근거를 분리해야 한다.", "score": 0.7}][:limit]


async def _kg_memory_search(query: str, limit: int) -> list[dict]:
    return [
        {
            "uuid": "kg-memory-1",
            "title": "Weekly research memory note: materials_ontology_kg",
            "fact": "Graphiti에서 이전 memory note가 검색되었다.",
            "document_type": "research_memory_note",
            "score": 0.7,
        }
    ][:limit]


async def _answer_success(**kwargs) -> str:
    return (
        "## 현재 답변\n"
        "제공된 citation 기준으로 질문 기반 루프는 기존 기억을 재사용해 다음 실행 단위를 좁힐 수 있다.\n\n"
        "## 근거\n- `scout:paper-1`와 thread memory를 함께 사용한다.\n\n"
        "## 보류할 주장\n- benchmark 우위는 아직 보류한다.\n\n"
        "## 다음 행동\n- work package draft를 실행한다."
    )


async def _work_package_success(**kwargs) -> str:
    return (
        "1. 질문의 claim boundary를 한 문단으로 정리한다.\n"
        "2. citation refs를 원문 또는 memory note와 대조한다.\n"
        "3. 다음 question loop에서 재사용할 next action을 남긴다."
    )


async def _llm_failure(**kwargs) -> str:
    raise RuntimeError("model timeout")


async def _graphiti_success(conversation_id: str, user_message: str, assistant_message: str, agent_name: str):
    return {
        "status": "ingested",
        "conversation_id": conversation_id,
        "agent_name": agent_name,
        "live_store_mutations": [{"type": "graphiti_ingest", "conversation_id": conversation_id}],
    }


async def _graphiti_failure(conversation_id: str, user_message: str, assistant_message: str, agent_name: str):
    return False


def _qdrant_success(**kwargs):
    return {
        "status": "upserted",
        "point_id": "point-1",
        "chunk_id": memory_note_chunk_id(thread_id=kwargs["thread_id"], memory_note_id=kwargs["memory_note_id"]),
        "live_store_mutations": [{"type": "qdrant_upsert", "point_id": "point-1"}],
    }


def _qdrant_failure(**kwargs):
    return {"status": "failed", "error": "qdrant down", "live_store_mutations": []}


class ResearchQuestionLoopTests(unittest.TestCase):
    def _seeded_artifacts(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        tmp = tempfile.TemporaryDirectory()
        artifacts = Path(tmp.name) / "artifacts"
        seed_research_threads(artifacts_dir=artifacts, execute=True, created_at=FIXED_NOW)
        return tmp, artifacts

    def test_preview_does_not_write_artifacts_or_thread(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)

        before = load_research_thread("materials_ontology_kg", artifacts_dir=artifacts)
        payload = asyncio.run(preview_or_run_question_loop(
            thread_id="materials_ontology_kg",
            question="지금 materials ontology KG에서 다음 실행 질문은 무엇인가?",
            artifacts_dir=artifacts,
            execute=False,
            use_llm=False,
            scout_search=lambda query, limit, days: [],
            rag_search=lambda query, limit, days: [],
            kg_search=lambda query, limit: _kg_search(query, 0),
            created_at=FIXED_NOW,
        ))
        after = load_research_thread("materials_ontology_kg", artifacts_dir=artifacts)

        self.assertEqual(payload["status"], "would_run")
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["answer"]["synthesis_mode"], "fallback")
        self.assertEqual(before, after)
        self.assertFalse((artifacts / "research_question_runs").exists())
        self.assertFalse((artifacts / "research_memory_notes").exists())

    def test_execute_writes_answer_memory_work_package_thread_and_live_memory(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)

        payload = asyncio.run(preview_or_run_question_loop(
            thread_id="materials_ontology_kg",
            question="기존 기억을 바탕으로 다음 work package는 무엇인가?",
            artifacts_dir=artifacts,
            execute=True,
            use_live_memory=True,
            scout_search=_scout_search,
            rag_search=_rag_memory_search,
            kg_search=_kg_search,
            graphiti_ingest=_graphiti_success,
            qdrant_upsert=_qdrant_success,
            answer_synthesizer=_answer_success,
            work_package_synthesizer=_work_package_success,
            created_at=FIXED_NOW,
        ))

        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["answer"]["synthesis_mode"], "llm")
        self.assertEqual(payload["work_package_draft"]["synthesis"]["synthesis_mode"], "llm")
        self.assertTrue(Path(payload["run_json_path"]).exists())
        self.assertTrue(Path(payload["memory_json_path"]).exists())
        self.assertTrue(Path(payload["work_package_json_path"]).exists())
        self.assertEqual(payload["live_write_results"]["graphiti"]["status"], "ingested")
        self.assertEqual(payload["live_write_results"]["qdrant"]["status"], "upserted")
        self.assertEqual(len(payload["live_store_mutations"]), 2)

        thread = load_research_thread("materials_ontology_kg", artifacts_dir=artifacts)
        self.assertEqual(thread["research_state"], "on_demand_question_loop_updated")
        self.assertTrue(any(item["id"].endswith(".decision.stored") for item in thread["decisions"]))

    def test_llm_failure_falls_back_without_failing_run(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)

        payload = asyncio.run(preview_or_run_question_loop(
            thread_id="materials_ontology_kg",
            question="LLM이 실패하면 어떻게 저장되는가?",
            artifacts_dir=artifacts,
            execute=False,
            scout_search=_scout_search,
            rag_search=lambda query, limit, days: [],
            kg_search=lambda query, limit: _kg_search(query, 0),
            answer_synthesizer=_llm_failure,
            work_package_synthesizer=_llm_failure,
            created_at=FIXED_NOW,
        ))

        self.assertEqual(payload["status"], "would_run")
        self.assertEqual(payload["answer"]["synthesis_mode"], "fallback")
        self.assertIn("model timeout", payload["answer"]["synthesis_error"])
        self.assertEqual(payload["work_package_draft"]["synthesis"]["synthesis_mode"], "fallback")
        self.assertIn("model timeout", payload["work_package_draft"]["synthesis"]["synthesis_error"])

    def test_live_memory_failure_is_partial_failure(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)

        payload = asyncio.run(preview_or_run_question_loop(
            thread_id="materials_ontology_kg",
            question="live memory 실패를 어떻게 기록하는가?",
            artifacts_dir=artifacts,
            execute=True,
            scout_search=_scout_search,
            rag_search=lambda query, limit, days: [],
            kg_search=_kg_search,
            graphiti_ingest=_graphiti_failure,
            qdrant_upsert=_qdrant_failure,
            answer_synthesizer=_answer_success,
            work_package_synthesizer=_work_package_success,
            created_at=FIXED_NOW,
        ))

        self.assertEqual(payload["status"], "partial_failure")
        self.assertEqual(payload["live_write_results"]["graphiti"]["status"], "failed")
        self.assertEqual(payload["live_write_results"]["qdrant"]["status"], "failed")
        run_json = json.loads(Path(payload["run_json_path"]).read_text(encoding="utf-8"))
        self.assertEqual(run_json["status"], "partial_failure")

    def test_memory_note_retrieval_is_memory_reuse_not_fresh_evidence(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)

        first = asyncio.run(preview_or_run_question_loop(
            thread_id="materials_ontology_kg",
            question="첫 번째 질문 기억을 남겨라.",
            artifacts_dir=artifacts,
            execute=True,
            use_live_memory=False,
            use_llm=False,
            scout_search=lambda query, limit, days: [],
            rag_search=lambda query, limit, days: [],
            kg_search=lambda query, limit: _kg_search(query, 0),
            created_at="2026-07-01T09:00:00Z",
        ))
        second = asyncio.run(preview_or_run_question_loop(
            thread_id="materials_ontology_kg",
            question="두 번째 질문에서 이전 기억을 재사용하라.",
            artifacts_dir=artifacts,
            execute=True,
            use_live_memory=False,
            use_llm=False,
            scout_search=lambda query, limit, days: [],
            rag_search=_rag_memory_search,
            kg_search=_kg_memory_search,
            created_at="2026-07-08T09:00:00Z",
        ))

        self.assertEqual(second["answer"]["fresh_evidence"]["rag"], [])
        self.assertEqual(second["answer"]["fresh_evidence"]["kg"], [])
        self.assertTrue(second["memory_note"]["memory_reuse_sources"]["rag"])
        self.assertTrue(second["memory_note"]["memory_reuse_sources"]["kg"])
        self.assertEqual(second["source_availability"]["memory_reuse_count"], 2)
        self.assertTrue(any(
            item["memory_note_id"] == first["memory_note_id"]
            for item in second["memory_note"]["reuse_provenance"]
        ))

    def test_both_seed_threads_support_question_loop_contract(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)

        for idx, thread_id in enumerate(("materials_ontology_kg", "rare_earth_magnets"), start=1):
            payload = asyncio.run(preview_or_run_question_loop(
                thread_id=thread_id,
                question=f"{thread_id}의 다음 실행 패키지는 무엇인가?",
                artifacts_dir=artifacts,
                execute=True,
                use_live_memory=False,
                use_llm=False,
                scout_search=_scout_search,
                rag_search=lambda query, limit, days: [],
                kg_search=_kg_search,
                created_at=f"2026-07-0{idx}T09:00:00Z",
            ))
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["thread_id"], thread_id)
            self.assertTrue(Path(payload["work_package_markdown_path"]).exists())

    def test_weekly_loop_now_supports_rare_earth_thread(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)

        payload = asyncio.run(preview_or_run_weekly_loop(
            thread_id="rare_earth_magnets",
            artifacts_dir=artifacts,
            execute=False,
            scout_search=lambda query, limit, days: [],
            rag_search=lambda query, limit, days: [],
            kg_search=lambda query, limit: _kg_search(query, 0),
            created_at=FIXED_NOW,
        ))

        self.assertEqual(payload["status"], "would_run")
        self.assertEqual(payload["thread_id"], "rare_earth_magnets")
        self.assertIn("rare earth", payload["query"])

    def test_api_question_loop_execute_writes_without_live_memory_or_llm(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)
        patcher = patch.object(research_thread, "ARTIFACTS_DIR", artifacts)
        patcher.start()
        self.addCleanup(patcher.stop)
        client = TestClient(app)

        response = client.post(
            "/research/threads/rare_earth_magnets/questions/run",
            json={
                "question": "rare earth magnets의 다음 질문 기반 work package는?",
                "execute": True,
                "use_live_memory": False,
                "use_llm": False,
                "scout_limit": 0,
                "rag_limit": 0,
                "kg_limit": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertTrue(Path(payload["run_json_path"]).exists())
        self.assertTrue(Path(payload["memory_json_path"]).exists())
        self.assertTrue(Path(payload["work_package_json_path"]).exists())


if __name__ == "__main__":
    unittest.main()
