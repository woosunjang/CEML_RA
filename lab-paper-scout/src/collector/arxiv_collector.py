"""
lab-paper-scout: ArXiv paper collector
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import arxiv

from src.processor.document_store import DocumentStore

logger = logging.getLogger(__name__)


class ArxivCollector:
    """Collects papers from ArXiv based on configured topics."""

    def __init__(self, config: Dict, store: DocumentStore):
        self.config = config
        self.store = store
        self.max_results = config.get("api", {}).get("max_papers_per_run", 20)
        self.days_lookback = config.get("api", {}).get("days_lookback", 7)

    def collect(self, topics: List[Dict]) -> List[Dict]:
        if not topics:
            logger.info("No topics configured, skipping ArXiv collection.")
            return []

        all_new = []
        for topic in topics:
            new_papers = self._collect_topic(topic)
            all_new.extend(new_papers)

        logger.info(f"ArXiv collection complete: {len(all_new)} new papers.")
        return all_new

    def _collect_topic(self, topic: Dict) -> List[Dict]:
        query = self._build_query(topic)
        if not query:
            return []

        logger.info(f"ArXiv search: topic='{topic['name']}', query='{query}'")

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=self.max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        new_papers = []
        for result in client.results(search):
            cutoff = datetime.now(result.published.tzinfo) - timedelta(
                days=self.days_lookback
            )
            if result.published < cutoff:
                continue

            paper = self._result_to_paper(result, topic)

            if self.store.add_paper(paper):
                new_papers.append(paper)
                logger.info(f"  New: {paper['title'][:80]}...")

        return new_papers

    def _build_query(self, topic: Dict) -> str:
        parts = []

        keywords = topic.get("keywords", [])
        if keywords:
            kw_query = " OR ".join(f'all:"{kw}"' for kw in keywords)
            parts.append(f"({kw_query})")

        categories = topic.get("arxiv_categories", [])
        if categories:
            cat_query = " OR ".join(f"cat:{cat}" for cat in categories)
            parts.append(f"({cat_query})")

        return " AND ".join(parts) if parts else ""

    def _result_to_paper(self, result: arxiv.Result, topic: Dict) -> Dict:
        return {
            "id": f"arxiv_{result.entry_id.split('/')[-1]}",
            "title": result.title,
            "authors": [a.name for a in result.authors],
            "source": "arxiv",
            "url": result.entry_id,
            "pdf_url": result.pdf_url,
            "year": result.published.year,
            "abstract": result.summary,
            "topics": [topic["name"]],
        }

    def download_pdf(self, paper: Dict, download_dir: str) -> Optional[str]:
        try:
            client = arxiv.Client()
            search = arxiv.Search(id_list=[paper["id"].replace("arxiv_", "")])
            result = next(client.results(search))
            path = result.download_pdf(dirpath=download_dir)
            logger.info(f"  Downloaded: {path}")
            return str(path)
        except Exception as e:
            logger.error(f"  PDF download failed for {paper['id']}: {e}")
            return None
