"""
lab-paper-scout: Backfill Collector
Systematically collects older papers by sliding a time window backwards,
gradually building a comprehensive literature corpus.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import requests

from src.processor.document_store import DocumentStore

logger = logging.getLogger(__name__)

S2_API_BASE = "https://api.semanticscholar.org/graph/v1"
STATE_FILE = "backfill_state.json"


class BackfillCollector:
    """Collects older papers by sliding a date window backwards."""

    def __init__(self, config: Dict, store: DocumentStore, data_dir: Path):
        self.config = config
        self.store = store
        self.data_dir = data_dir

        bf = config.get("backfill", {})
        self.enabled = bf.get("enabled", False)
        self.window_days = bf.get("window_days", 30)
        self.max_age_days = bf.get("max_age_days", 730)
        self.max_per_topic = bf.get("max_papers_per_topic", 10)

        api_cfg = config.get("api", {})
        self.throttle = api_cfg.get("throttle_seconds", 2)
        api_key_env = api_cfg.get("semantic_scholar_api_key_env", "S2_API_KEY")
        api_key = os.environ.get(api_key_env, "")
        self.headers = {"x-api-key": api_key} if api_key else {}

        self.state_path = data_dir / STATE_FILE

    # ─── Public API ────────────────────────────────────────────

    def collect(self, topics: List[Dict]) -> List[Dict]:
        """Run one backfill batch. Returns newly collected papers."""
        if not self.enabled or not topics:
            return []

        state = self._load_state()
        offset = state.get("current_offset_days", 7)

        # Calculate date range
        end_date = datetime.now() - timedelta(days=offset)
        start_date = end_date - timedelta(days=self.window_days)

        # Check if we've gone past max age
        if offset >= self.max_age_days:
            logger.info("Backfill: reached max age, cycling back to start.")
            offset = 7  # reset
            end_date = datetime.now() - timedelta(days=offset)
            start_date = end_date - timedelta(days=self.window_days)

        date_range = f"{start_date.strftime('%Y-%m-%d')}:{end_date.strftime('%Y-%m-%d')}"
        logger.info(
            f"Backfill: collecting papers from {date_range} "
            f"(offset={offset} days)"
        )

        all_new = []
        for topic in topics:
            new = self._collect_topic(topic, start_date, end_date)
            all_new.extend(new)
            time.sleep(self.throttle)

        # Advance window for next run
        next_offset = offset + self.window_days
        self._save_state({"current_offset_days": next_offset, "last_run": datetime.now().isoformat()})

        logger.info(f"Backfill complete: {len(all_new)} new papers from {date_range}.")
        return all_new

    # ─── Private ───────────────────────────────────────────────

    def _collect_topic(self, topic: Dict, start_date: datetime, end_date: datetime) -> List[Dict]:
        keywords = topic.get("keywords", [])
        if not keywords:
            return []

        query = " ".join(keywords[:3])
        logger.info(f"  Backfill S2: topic='{topic['name']}', query='{query}'")

        params = {
            "query": query,
            "limit": min(self.max_per_topic, 100),
            "fields": "paperId,title,authors,year,abstract,url,openAccessPdf,citationCount,publicationDate,venue,externalIds",
            "publicationDateOrYear": f"{start_date.strftime('%Y-%m-%d')}:{end_date.strftime('%Y-%m-%d')}",
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
            logger.error(f"  Backfill S2 error: {e}")
            return []

        import re
        new_papers = []
        relevance_threshold = self.config.get("backfill", {}).get("report_min_score", 70)

        for item in data.get("data", []):
            paper_id = item.get("paperId")
            title = item.get("title")
            if not paper_id or not title:
                continue

            pid = f"s2_{paper_id}"
            if self.store.paper_exists(pid):
                continue

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

            paper = {
                "id": pid,
                "title": re.sub(r'\s+', ' ', title).strip(),
                "authors": [a.get("name", "") for a in (item.get("authors") or [])],
                "source": "backfill",
                "url": url,
                "pdf_url": pdf_url,
                "year": item.get("year"),
                "abstract": item.get("abstract", ""),
                "topics": [topic["name"]],
                "venue": venue,
                "exclude_report": True,
            }

            if self.store.add_paper(paper):
                new_papers.append(paper)
                logger.info(f"    Backfill: {paper['title'][:70]}...")

        return new_papers

    def _load_state(self) -> Dict:
        if self.state_path.exists():
            with open(self.state_path, "r") as f:
                return json.load(f)
        return {"current_offset_days": 7}

    def _save_state(self, state: Dict):
        with open(self.state_path, "w") as f:
            json.dump(state, f, indent=2)
