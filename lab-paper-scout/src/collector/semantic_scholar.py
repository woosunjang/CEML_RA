"""
lab-paper-scout: Semantic Scholar paper collector
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import re

import requests

from src.processor.document_store import DocumentStore

logger = logging.getLogger(__name__)

S2_API_BASE = "https://api.semanticscholar.org/graph/v1"


class SemanticScholarCollector:
    """Collects papers from Semantic Scholar API."""

    def __init__(self, config: Dict, store: DocumentStore):
        self.config = config
        self.store = store
        self.max_results = config.get("api", {}).get("max_papers_per_run", 20)
        self.throttle = config.get("api", {}).get("throttle_seconds", 2)

        # Load optional API key for higher rate limits
        api_key_env = config.get("api", {}).get("semantic_scholar_api_key_env", "S2_API_KEY")
        api_key = os.environ.get(api_key_env, "")
        self.headers = {"x-api-key": api_key} if api_key else {}

    def collect(self, topics: List[Dict]) -> List[Dict]:
        if not topics:
            logger.info("No topics configured, skipping S2 collection.")
            return []

        all_new = []
        for topic in topics:
            new_papers = self._collect_topic(topic)
            all_new.extend(new_papers)
            time.sleep(self.throttle)

        logger.info(f"Semantic Scholar collection complete: {len(all_new)} new papers.")
        return all_new

    def _collect_topic(self, topic: Dict) -> List[Dict]:
        keywords = topic.get("keywords", [])
        if not keywords:
            return []

        query = " ".join(keywords[:3])
        logger.info(f"S2 search: topic='{topic['name']}', query='{query}'")

        params = {
            "query": query,
            "limit": min(self.max_results, 100),
            "fields": "paperId,title,authors,year,abstract,url,openAccessPdf,citationCount,publicationDate,venue,externalIds",
            "year": f"{self._min_year()}-",
        }

        fields_of_study = topic.get("semantic_scholar_fields")
        if fields_of_study:
            params["fieldsOfStudy"] = ",".join(fields_of_study)

        try:
            resp = requests.get(
                f"{S2_API_BASE}/paper/search",
                params=params,
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"S2 API error: {e}")
            return []

        new_papers = []
        for item in data.get("data", []):
            paper = self._item_to_paper(item, topic)
            if paper and self.store.add_paper(paper):
                new_papers.append(paper)
                logger.info(f"  New: {paper['title'][:80]}...")

        return new_papers

    def _item_to_paper(self, item: Dict, topic: Dict) -> Optional[Dict]:
        paper_id = item.get("paperId")
        title = item.get("title")
        if not paper_id or not title:
            return None

        oa = item.get("openAccessPdf") or {}
        pdf_url = oa.get("url", "")

        # Prefer DOI link > ArXiv > OA PDF > S2 page
        ext_ids = item.get("externalIds") or {}
        doi = ext_ids.get("DOI", "")
        arxiv_id = ext_ids.get("ArXiv", "")
        if doi:
            url = f"https://doi.org/{doi}"
        elif arxiv_id:
            url = f"https://arxiv.org/abs/{arxiv_id}"
        elif pdf_url:
            url = pdf_url
        else:
            url = item.get("url", f"https://www.semanticscholar.org/paper/{paper_id}")

        venue = item.get("venue", "") or ""

        return {
            "id": f"s2_{paper_id}",
            "title": re.sub(r'\s+', ' ', title).strip(),
            "authors": [a.get("name", "") for a in (item.get("authors") or [])],
            "source": "semantic_scholar",
            "url": url,
            "pdf_url": pdf_url,
            "year": item.get("year"),
            "abstract": item.get("abstract", ""),
            "topics": [topic["name"]],
            "venue": venue,
        }

    def _min_year(self) -> int:
        days = self.config.get("api", {}).get("days_lookback", 7)
        return (datetime.now() - timedelta(days=days)).year
