"""
Lab Research Agents — BM25 Keyword Store

In-memory BM25 index for keyword-based document retrieval.
Complements vector search by catching exact term matches
(chemical formulas, acronyms, proper nouns) that embeddings may miss.
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
        self._chunks: list[dict] = []  # payload dicts, parallel to _index corpus

    @property
    def is_ready(self) -> bool:
        return self._index is not None and len(self._chunks) > 0

    # ── Tokenizer ────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace + punctuation tokenizer.

        Handles both English and Korean adequately for BM25.
        Chemical formulas like Li7La3Zr2O12 are kept as single tokens.
        """
        text = text.lower()
        # Split on whitespace and common punctuation, keep alphanumeric+dots
        tokens = re.findall(r"[a-z0-9\u3131-\u3163\uac00-\ud7a3_.]+", text)
        # Filter very short tokens (single chars except digits/Korean)
        return [t for t in tokens if len(t) > 1 or t.isdigit()]

    # ── Build index ──────────────────────────────────────────

    def build(self, chunks: list[dict]) -> None:
        """Build BM25 index from a list of chunk payload dicts.

        Each dict must have at least a 'text' key.
        """
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
        """Reload the BM25 index by scrolling all points from Qdrant.

        This is called at app startup and after each document ingest.
        """
        from app.retrieval.vector_store import _client, QDRANT_COLLECTION

        try:
            # Check if collection exists
            collections = _client.get_collections().collections
            if not any(c.name == QDRANT_COLLECTION for c in collections):
                logger.info("BM25: Qdrant collection not found — index empty.")
                self._index = None
                self._chunks = []
                return

            # Scroll all points
            all_chunks = []
            offset = None
            while True:
                result = _client.scroll(
                    collection_name=QDRANT_COLLECTION,
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                points, next_offset = result
                for point in points:
                    payload = point.payload or {}
                    payload["_point_id"] = point.id  # preserve Qdrant point ID
                    all_chunks.append(payload)

                if next_offset is None:
                    break
                offset = next_offset

            self.build(all_chunks)
        except Exception as e:
            logger.error(f"BM25: Failed to reload from Qdrant: {e}")
            self._index = None
            self._chunks = []

    # ── Search ───────────────────────────────────────────────

    def search(
        self,
        query: str,
        limit: int = 10,
        project: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> list[dict]:
        """Search using BM25 keyword matching.

        Args:
            query: Search query text.
            limit: Maximum results to return.
            project: Filter by project (None = no filter).
            document_type: Filter by document type (None = no filter).

        Returns:
            List of chunk payload dicts with added '_bm25_score' key,
            sorted by score descending.
        """
        if not self.is_ready:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores = self._index.get_scores(query_tokens)

        # Build scored list with filters
        scored = []
        for idx, score in enumerate(scores):
            if score <= 0:
                continue
            chunk = self._chunks[idx]

            # Apply filters
            if project and chunk.get("project") != project:
                continue
            if document_type and chunk.get("document_type") != document_type:
                continue

            result = dict(chunk)
            result["_bm25_score"] = float(score)
            scored.append(result)

        # Sort by score descending and return top-K
        scored.sort(key=lambda x: x["_bm25_score"], reverse=True)
        return scored[:limit]


# ── Module-level singleton ───────────────────────────────────

bm25_store = BM25Store()
