"""Unit tests for proactive Knowledge Brief generation."""

import asyncio
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import integrations.knowledge_brief as kb
from integrations.knowledge_brief import generate_knowledge_brief


class KnowledgeBriefTests(unittest.TestCase):
    def _make_db(self, root: Path) -> Path:
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
                pdf_url TEXT,
                year INTEGER,
                abstract TEXT,
                topics_json TEXT DEFAULT '[]',
                relevance_score REAL DEFAULT 0.0,
                status TEXT DEFAULT 'collected',
                summary TEXT,
                analysis_json TEXT,
                collected_at TEXT,
                processed_at TEXT,
                analyzed_at TEXT,
                exclude_report INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                chased INTEGER DEFAULT 0,
                venue TEXT DEFAULT ''
            )
            """
        )
        papers = [
            (
                "p1",
                "Materials knowledge graph for battery discovery",
                json.dumps(["Kim", "Lee", "Park"]),
                "semantic_scholar",
                "https://example.com/p1",
                2026,
                "Knowledge graphs for materials discovery.",
                json.dumps(["materials_ontology_kg"]),
                95,
                "KG summary",
                json.dumps({
                    "summary_kr": "재료 지식그래프를 활용한 탐색 논문입니다.",
                    "key_contribution": "재료 탐색에서 ontology-guided reasoning을 입증했습니다.",
                    "methodology": "Knowledge graph + ontology reasoning",
                    "key_results": "후보 재료 탐색 정확도가 개선되었습니다.",
                    "tags": ["Knowledge Graph", "Ontology"],
                }),
                "2026-05-31T03:00:00",
                "2026-05-31T03:10:00",
                "Journal A",
            ),
            (
                "p2",
                "Ontology-guided semantic materials data",
                json.dumps(["Choi"]),
                "backfill",
                "https://example.com/p2",
                2025,
                "Semantic materials data.",
                json.dumps(["materials_ontology_kg"]),
                82,
                "Ontology summary",
                json.dumps({
                    "summary_kr": "재료 데이터 의미론 정리 논문입니다.",
                    "key_contribution": "FAIR materials data schema를 제안했습니다.",
                    "methodology": "Ontology alignment",
                    "key_results": "데이터 재사용성이 개선되었습니다.",
                    "tags": ["Knowledge Graph", "FAIR Data"],
                }),
                "2026-05-31T04:00:00",
                "2026-05-31T04:10:00",
                "Journal B",
            ),
        ]
        conn.executemany(
            """
            INSERT INTO papers (
                id, title, authors, source, url, year, abstract, topics_json,
                relevance_score, summary, analysis_json, collected_at,
                analyzed_at, venue, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'analyzed')
            """,
            papers,
        )
        conn.commit()
        conn.close()
        return db_path

    def test_generate_brief_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = self._make_db(root)
            brief = generate_knowledge_brief(
                date="2026-05-31",
                days=1,
                query="materials",
                promote=False,
                db_path=db_path,
                data_dir=root / "briefs",
                report_dir=root / "reports",
                log_action=False,
            )

            self.assertEqual(brief["period_label"], "2026-05-31")
            self.assertEqual(len(brief["evidence_items"]), 2)
            self.assertIn("Proactive Research Brief", brief["markdown"])
            self.assertIn("모델 추론/가설", brief["markdown"])
            self.assertTrue(Path(brief["json_path"]).exists())
            self.assertTrue(Path(brief["markdown_path"]).exists())
            self.assertTrue(brief["connections"])
            self.assertTrue(brief["proposed_actions"])

    def test_load_latest_brief_normalizes_stored_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            briefs_dir = root / "briefs"
            reports_dir = root / "reports"
            briefs_dir.mkdir()
            reports_dir.mkdir()
            json_path = briefs_dir / "brief_20260531.json"
            json_path.write_text(
                json.dumps({
                    "date": "2026-05-31",
                    "start_date": "2026-05-31",
                    "end_date": "2026-05-31",
                    "period_label": "2026-05-31",
                    "query": "",
                    "evidence_items": [{"title": "Stored evidence"}],
                    "json_path": "/old-machine/data/knowledge_briefs/brief_20260531.json",
                    "markdown_path": "/old-machine/generated/reports/brief_20260531.md",
                }),
                encoding="utf-8",
            )

            old_brief_dir = kb.BRIEF_DATA_DIR
            old_report_dir = kb.GENERATED_REPORTS_DIR
            try:
                kb.BRIEF_DATA_DIR = briefs_dir
                kb.GENERATED_REPORTS_DIR = reports_dir
                latest = kb.load_latest_brief()
            finally:
                kb.BRIEF_DATA_DIR = old_brief_dir
                kb.GENERATED_REPORTS_DIR = old_report_dir

            self.assertEqual(latest["json_path"], str(json_path))
            self.assertEqual(latest["markdown_path"], str(reports_dir / "brief_20260531.md"))

    def test_generate_reuses_existing_brief_when_source_period_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            briefs_dir = root / "briefs"
            reports_dir = root / "reports"
            briefs_dir.mkdir()
            reports_dir.mkdir()
            json_path = briefs_dir / "brief_20260531.json"
            json_path.write_text(
                json.dumps({
                    "date": "2026-05-31",
                    "start_date": "2026-05-31",
                    "end_date": "2026-05-31",
                    "period_label": "2026-05-31",
                    "query": "",
                    "papers": [{"title": "Existing paper"}],
                    "evidence_items": [{"title": "Existing evidence"}],
                    "markdown": "# Existing brief",
                    "metadata": {"evidence_count": 1},
                }),
                encoding="utf-8",
            )

            brief = generate_knowledge_brief(
                date="2026-05-31",
                days=1,
                promote=False,
                write_files=False,
                db_path=root / "missing.db",
                data_dir=briefs_dir,
                report_dir=reports_dir,
                log_action=False,
            )

            self.assertEqual(len(brief["evidence_items"]), 1)
            self.assertTrue(brief["metadata"]["reused_existing_due_to_empty_source"])
            self.assertEqual(brief["json_path"], str(json_path))
            self.assertEqual(brief["markdown_path"], str(reports_dir / "brief_20260531.md"))

    def test_search_knowledge_returns_partial_results_on_source_failure(self):
        class FailingScout:
            def search_papers(self, query, limit=5):
                raise sqlite3.OperationalError("disk I/O error")

        class RagResult:
            score = 0.91
            payload = {
                "title": "RAG paper",
                "document_type": "paper",
                "source": "qdrant",
                "text": "materials search result",
            }

        class FakeArchivalMemory:
            async def search(self, query, limit=5):
                return [{"fact": "archival fact"}]

        with patch("integrations.scout_reader.ScoutReader", return_value=FailingScout()), \
             patch("integrations.hybrid_retriever.hybrid_search", return_value=[RagResult()]), \
             patch("orchestrator.archival.archival_memory", FakeArchivalMemory()):
            result = asyncio.run(kb.search_knowledge("materials", limit=1))

        self.assertEqual(result["query"], "materials")
        self.assertEqual(result["scout"], [])
        self.assertEqual(len(result["rag"]), 1)
        self.assertEqual(len(result["archival"]), 1)
        self.assertEqual(result["errors"][0]["source"], "scout")


if __name__ == "__main__":
    unittest.main()
