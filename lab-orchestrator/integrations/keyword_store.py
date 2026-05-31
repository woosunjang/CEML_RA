"""
Lab Orchestrator — BM25 Keyword Store

In-memory BM25 index for keyword-based retrieval.
Ported from lab-research-agents with adapted imports.
"""

import logging
import re
from typing import Optional

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Store:
    """Singleton-style BM25 index over Qdrant chunk payloads."""

    def __init__(self):
        self._index: Optional[BM25Okapi] = None
        self._chunks: list[dict] = []

    @property
    def is_ready(self) -> bool:
        return self._index is not None and len(self._chunks) > 0

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        text = text.lower()
        tokens = re.findall(r"[a-z0-9\u3131-\u3163\uac00-\ud7a3_.]+", text)
        return [t for t in tokens if len(t) > 1 or t.isdigit()]

    def build(self, chunks: list[dict]) -> None:
        if not chunks:
            logger.warning("BM25: No chunks to index.")
            self._index = None
            self._chunks = []
            return

        self._chunks = chunks
        corpus = [self._tokenize(c.get("text", "")) for c in chunks]
        self._index = BM25Okapi(corpus)
        logger.info(f"BM25: Indexed {len(chunks)} chunks.")

    def reload_from_qdrant(self) -> None:
        """Reload by scrolling all points from Qdrant."""
        from integrations.qdrant import scroll_all_chunks, QDRANT_COLLECTION

        try:
            all_chunks = []
            for point in scroll_all_chunks():
                payload = point.payload or {}
                payload["_point_id"] = point.id
                all_chunks.append(payload)
            self.build(all_chunks)
        except Exception as e:
            logger.error(f"BM25: Failed to reload from Qdrant: {e}")
            self._index = None
            self._chunks = []

    def search(
        self,
        query: str,
        limit: int = 10,
        project: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> list[dict]:
        if not self.is_ready:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores = self._index.get_scores(query_tokens)

        scored = []
        for idx, score in enumerate(scores):
            if score <= 0:
                continue
            chunk = self._chunks[idx]
            if project and chunk.get("project") != project:
                continue
            if document_type and chunk.get("document_type") != document_type:
                continue

            result = dict(chunk)
            result["_bm25_score"] = float(score)
            scored.append(result)

        scored.sort(key=lambda x: x["_bm25_score"], reverse=True)
        return scored[:limit]


bm25_store = BM25Store()
