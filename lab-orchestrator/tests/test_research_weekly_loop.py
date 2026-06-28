"""Tests for Weekly Useful Research Loop v0."""

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
from integrations.qdrant import build_memory_note_payload, memory_note_chunk_id  # noqa: E402
from orchestrator.research_thread import load_research_thread, seed_research_threads  # noqa: E402
from orchestrator.research_weekly_loop import preview_or_run_weekly_loop  # noqa: E402


FIXED_NOW = "2026-06-28T09:00:00Z"


class _RagResult:
    score = 0.42
    payload = {
        "chunk_id": "prior_memory_chunk",
        "title": "Prior memory note",
        "text": "이전 materials ontology KG memory note가 RAG에서 검색되었다.",
        "artifact_ref": "research_memory_notes/materials_ontology_kg/prior.md",
    }


def _scout_search(query: str, limit: int, days: int) -> list[dict]:
    return [
        {
            "id": "paper-1",
            "title": "Provenance-aware materials knowledge graph",
            "summary": "재료 지식그래프에서 provenance가 의사결정 품질을 좌우한다.",
            "url": "https://example.com/paper-1",
            "relevance_score": 91,
        }
    ][:limit]


def _rag_search(query: str, limit: int, days: int) -> list[_RagResult]:
    return [_RagResult()][:limit]


async def _kg_search(query: str, limit: int) -> list[dict]:
    return [{"uuid": "kg-1", "fact": "Graphiti에 저장된 이전 KG/RAG benchmark 논의가 있다.", "score": 0.7}][:limit]


async def _graphiti_success(conversation_id: str, user_message: str, assistant_message: str, agent_name: str):
    return True


async def _graphiti_structured_success(conversation_id: str, user_message: str, assistant_message: str, agent_name: str):
    return {
        "status": "ingested",
        "conversation_id": conversation_id,
        "episode_name": "weekly_episode",
        "live_store_mutations": [{"type": "graphiti_ingest", "episode_name": "weekly_episode"}],
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


class ResearchWeeklyLoopTests(unittest.TestCase):
    def _seeded_artifacts(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        tmp = tempfile.TemporaryDirectory()
        artifacts = Path(tmp.name) / "artifacts"
        seed_research_threads(artifacts_dir=artifacts, execute=True, created_at=FIXED_NOW)
        return tmp, artifacts

    def test_preview_generates_brief_from_artifacts_even_when_sources_are_empty(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)

        payload = asyncio.run(preview_or_run_weekly_loop(
            artifacts_dir=artifacts,
            execute=False,
            scout_search=lambda query, limit, days: [],
            rag_search=lambda query, limit, days: [],
            kg_search=lambda query, limit: _kg_search(query, 0),
            created_at=FIXED_NOW,
        ))

        self.assertEqual(payload["status"], "would_run")
        self.assertTrue(payload["dry_run"])
        self.assertIn("Weekly Useful Research Loop", payload["preview_markdown"])
        self.assertTrue(payload["brief"]["reused_memory"]["thread_memory"])
        self.assertIn("preflight_summary", payload)
        self.assertIn("source_availability", payload)
        self.assertEqual(payload["live_store_mutations"], [])
        self.assertFalse((artifacts / "research_weekly_loops").exists())

    def test_execute_writes_artifacts_updates_thread_and_records_live_mutations(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)

        payload = asyncio.run(preview_or_run_weekly_loop(
            artifacts_dir=artifacts,
            execute=True,
            scout_search=_scout_search,
            rag_search=_rag_search,
            kg_search=_kg_search,
            graphiti_ingest=_graphiti_success,
            qdrant_upsert=_qdrant_success,
            created_at=FIXED_NOW,
        ))

        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["live_write_results"]["graphiti"]["status"], "ingested")
        self.assertEqual(payload["source_availability"]["scout"]["count"], 1)
        self.assertEqual(payload["source_availability"]["rag"]["count"], 1)
        self.assertEqual(payload["source_availability"]["kg"]["count"], 1)
        self.assertTrue(Path(payload["run_json_path"]).exists())
        self.assertTrue(Path(payload["run_markdown_path"]).exists())
        self.assertTrue(Path(payload["memory_json_path"]).exists())
        self.assertTrue(Path(payload["memory_markdown_path"]).exists())
        self.assertEqual(len(payload["live_store_mutations"]), 2)

        thread = load_research_thread("materials_ontology_kg", artifacts_dir=artifacts)
        self.assertEqual(thread["research_state"], "weekly_useful_loop_updated")
        self.assertTrue(any(item["id"].endswith(".decision.stored") for item in thread["decisions"]))

    def test_live_memory_failures_are_partial_failure_not_silent_success(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)

        payload = asyncio.run(preview_or_run_weekly_loop(
            artifacts_dir=artifacts,
            execute=True,
            scout_search=_scout_search,
            rag_search=_rag_search,
            kg_search=_kg_search,
            graphiti_ingest=_graphiti_failure,
            qdrant_upsert=_qdrant_failure,
            created_at=FIXED_NOW,
        ))

        self.assertEqual(payload["status"], "partial_failure")
        self.assertEqual(payload["live_write_results"]["graphiti"]["status"], "failed")
        self.assertEqual(payload["live_write_results"]["qdrant"]["status"], "failed")
        run_json = json.loads(Path(payload["run_json_path"]).read_text(encoding="utf-8"))
        self.assertEqual(run_json["status"], "partial_failure")
        self.assertEqual(run_json["source_availability"]["qdrant_write"]["status"], "failed")

    def test_structured_graphiti_result_is_preserved(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)

        payload = asyncio.run(preview_or_run_weekly_loop(
            artifacts_dir=artifacts,
            execute=True,
            scout_search=_scout_search,
            rag_search=_rag_search,
            kg_search=_kg_search,
            graphiti_ingest=_graphiti_structured_success,
            qdrant_upsert=_qdrant_success,
            created_at=FIXED_NOW,
        ))

        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["live_write_results"]["graphiti"]["episode_name"], "weekly_episode")
        self.assertIn(
            {"type": "graphiti_ingest", "episode_name": "weekly_episode"},
            payload["live_store_mutations"],
        )

    def test_preflight_reports_scout_unavailable_when_db_is_missing(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)

        payload = asyncio.run(preview_or_run_weekly_loop(
            artifacts_dir=artifacts,
            execute=False,
            scout_search=lambda query, limit, days: [],
            rag_search=lambda query, limit, days: [],
            kg_search=lambda query, limit: _kg_search(query, 0),
            created_at=FIXED_NOW,
        ))

        self.assertIn("scout", payload["preflight_summary"]["failing"])
        self.assertFalse(payload["source_availability"]["scout"]["available"])

    def test_second_run_reuses_first_memory_note(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)

        first = asyncio.run(preview_or_run_weekly_loop(
            artifacts_dir=artifacts,
            execute=True,
            use_live_memory=False,
            scout_search=lambda query, limit, days: [],
            rag_search=lambda query, limit, days: [],
            kg_search=lambda query, limit: _kg_search(query, 0),
            created_at="2026-06-21T09:00:00Z",
        ))
        second = asyncio.run(preview_or_run_weekly_loop(
            artifacts_dir=artifacts,
            execute=True,
            use_live_memory=False,
            scout_search=lambda query, limit, days: [],
            rag_search=lambda query, limit, days: [],
            kg_search=lambda query, limit: _kg_search(query, 0),
            created_at="2026-06-28T09:00:00Z",
        ))

        previous = second["brief"]["reused_memory"]["previous_memory_notes"]
        self.assertEqual(previous[0]["memory_note_id"], first["memory_note_id"])
        self.assertIn(first["memory_note_id"], second["preview_markdown"])

    def test_qdrant_memory_note_payload_is_deterministic(self):
        payload = build_memory_note_payload(
            thread_id="materials_ontology_kg",
            memory_note_id="note-1",
            artifact_ref="/tmp/note.md",
            text="memory text",
            created_at=FIXED_NOW,
            claim_refs=["claim-1"],
            source_refs=["source-1"],
        )

        self.assertEqual(
            payload["chunk_id"],
            memory_note_chunk_id(thread_id="materials_ontology_kg", memory_note_id="note-1"),
        )
        self.assertEqual(payload["document_type"], "research_memory_note")
        self.assertEqual(payload["artifact_ref"], "/tmp/note.md")

    def test_api_weekly_loop_execute_writes_without_live_memory(self):
        tmp, artifacts = self._seeded_artifacts()
        self.addCleanup(tmp.cleanup)
        patcher = patch.object(research_thread, "ARTIFACTS_DIR", artifacts)
        patcher.start()
        self.addCleanup(patcher.stop)
        client = TestClient(app)

        response = client.post(
            "/research/threads/materials_ontology_kg/weekly-loop/run",
            json={
                "execute": True,
                "use_live_memory": False,
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


if __name__ == "__main__":
    unittest.main()
