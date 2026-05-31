"""
lab-paper-scout: Citation Chaser
For high-relevance papers, fetches their references and cited-by papers
from Semantic Scholar, expanding the knowledge network.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Dict, List

import requests

from src.processor.document_store import DocumentStore

logger = logging.getLogger(__name__)

S2_API_BASE = "https://api.semanticscholar.org/graph/v1"


class CitationChaser:
    """Chases citations (references + cited-by) of high-relevance papers."""

    def __init__(self, config: Dict, store: DocumentStore):
        self.config = config
        self.store = store

        cc = config.get("citation_chasing", {})
        self.enabled = cc.get("enabled", False)
        self.min_score = cc.get("min_relevance_score", 70)
        self.batch_size = cc.get("batch_size", 10)
        self.max_references = cc.get("max_references", 10)
        self.max_cited_by = cc.get("max_cited_by", 10)

        api_cfg = config.get("api", {})
        self.throttle = api_cfg.get("throttle_seconds", 2)
        api_key_env = api_cfg.get("semantic_scholar_api_key_env", "S2_API_KEY")
        api_key = os.environ.get(api_key_env, "")
        self.headers = {"x-api-key": api_key} if api_key else {}

    # ─── Public API ────────────────────────────────────────────

    def chase(self) -> List[Dict]:
        """Find high-relevance papers and chase their citations."""
        if not self.enabled:
            return []

        # Get papers eligible for citation chasing
        candidates = self.store.get_chaseable_papers(self.min_score)
        if not candidates:
            logger.info("Citation chase: no eligible papers.")
            return []

        logger.info(f"Citation chase: {len(candidates)} eligible, processing up to {self.batch_size}.")
        all_new = []
        batch = candidates[:self.batch_size]

        for paper in batch:
            paper_id = paper["id"]

            # Extract S2 paper ID (strip prefix)
            s2_id = paper_id
            if s2_id.startswith("s2_"):
                s2_id = s2_id[3:]
            elif s2_id.startswith("arxiv_") or s2_id.startswith("inbox_"):
                # For non-S2 papers, resolve via title search
                resolved = self._resolve_arxiv_to_s2(paper.get("title", ""))
                if not resolved:
                    self.store.mark_chased(paper_id)
                    continue
                s2_id = resolved
            else:
                # Unknown prefix — skip
                self.store.mark_chased(paper_id)
                continue

            # Fetch references
            refs = self._fetch_references(s2_id)
            for ref in refs:
                if self.store.add_paper(ref):
                    all_new.append(ref)

            time.sleep(self.throttle)

            # Fetch cited-by
            cited = self._fetch_citations(s2_id)
            for c in cited:
                if self.store.add_paper(c):
                    all_new.append(c)

            time.sleep(self.throttle)

            # Mark as chased so we don't re-process
            self.store.mark_chased(paper_id)
            logger.info(
                f"  Chased '{paper.get('title', '')[:50]}...': "
                f"{len(refs)} refs, {len(cited)} citations"
            )

        logger.info(f"Citation chase complete: {len(all_new)} new papers.")
        return all_new

    # ─── Private ───────────────────────────────────────────────

    def _fetch_references(self, s2_id: str) -> List[Dict]:
        """Fetch papers referenced by this paper."""
        try:
            resp = requests.get(
                f"{S2_API_BASE}/paper/{s2_id}/references",
                params={
                    "fields": "paperId,title,authors,year,abstract,url,openAccessPdf,citationCount,venue,externalIds",
                    "limit": self.max_references,
                },
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"  References fetch error: {e}")
            return []

        return self._parse_related(data.get("data") or [], key="citedPaper")

    def _fetch_citations(self, s2_id: str) -> List[Dict]:
        """Fetch papers that cite this paper."""
        try:
            resp = requests.get(
                f"{S2_API_BASE}/paper/{s2_id}/citations",
                params={
                    "fields": "paperId,title,authors,year,abstract,url,openAccessPdf,citationCount,venue,externalIds",
                    "limit": self.max_cited_by,
                },
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"  Citations fetch error: {e}")
            return []

        return self._parse_related(data.get("data") or [], key="citingPaper")

    def _parse_related(self, items: List[Dict], key: str) -> List[Dict]:
        """Parse S2 reference/citation response into paper dicts."""
        if not items:
            return []
        papers = []
        for item in items:
            if not item:
                continue
            paper_data = item.get(key) or {}
            if not paper_data:
                continue

            paper_id = paper_data.get("paperId")
            title = paper_data.get("title")
            if not paper_id or not title:
                continue

            pid = f"s2_{paper_id}"
            if self.store.paper_exists(pid):
                continue

            oa = paper_data.get("openAccessPdf") or {}
            pdf_url = oa.get("url", "")

            # Prefer DOI link > ArXiv > OA PDF > S2 page
            ext_ids = paper_data.get("externalIds") or {}
            doi = ext_ids.get("DOI", "")
            arxiv_id = ext_ids.get("ArXiv", "")
            if doi:
                url = f"https://doi.org/{doi}"
            elif arxiv_id:
                url = f"https://arxiv.org/abs/{arxiv_id}"
            elif pdf_url:
                url = pdf_url
            else:
                url = paper_data.get("url", f"https://www.semanticscholar.org/paper/{paper_id}")

            venue = paper_data.get("venue", "") or ""

            papers.append({
                "id": pid,
                "title": re.sub(r'\s+', ' ', title).strip(),
                "authors": [a.get("name", "") for a in (paper_data.get("authors") or [])],
                "source": "citation_chase",
                "url": url,
                "pdf_url": pdf_url,
                "year": paper_data.get("year"),
                "abstract": paper_data.get("abstract", ""),
                "topics": [],
                "venue": venue,
                "exclude_report": True,
            })

        return papers

    def _resolve_arxiv_to_s2(self, title: str) -> str | None:
        """Try to find S2 paper ID by title search."""
        if not title:
            return None
        try:
            resp = requests.get(
                f"{S2_API_BASE}/paper/search",
                params={"query": title, "limit": 1, "fields": "paperId"},
                headers=self.headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if data:
                return data[0].get("paperId")
        except Exception:
            pass
        return None
