"""
Lab Research Agents — Hybrid Retriever

Combines vector search (Qdrant cosine) and BM25 keyword search
using Reciprocal Rank Fusion (RRF) for robust retrieval.

    RRF_score(d) = Σ  1 / (k + rank_i(d))

where k=60 (standard constant) and i iterates over each ranker.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from app.config import QDRANT_COLLECTION
from app.retrieval.vector_store import search_vector
from app.retrieval.keyword_store import bm25_store

logger = logging.getLogger(__name__)

# RRF constant — higher k reduces the influence of high-ranking items
RRF_K = 60


@dataclass
class _FusedResult:
    """Internal container for a fused search result."""
    chunk_id: str
    payload: dict = field(default_factory=dict)
    rrf_score: float = 0.0
    vector_rank: int = 0
    bm25_rank: int = 0


def hybrid_search(
    query: str,
    limit: int = 10,
    project: Optional[str] = None,
    document_type: Optional[str] = None,
) -> list:
    """Perform hybrid search combining vector and BM25 keyword results.

    Strategy:
        1. Fetch 2×limit results from both vector and BM25 searchers.
        2. Combine using Reciprocal Rank Fusion (RRF).
        3. Return top-limit results as Qdrant ScoredPoint-compatible objects.

    If BM25 index is not ready (empty DB), falls back to vector-only search.

    Args:
        query: The search query text.
        limit: Maximum number of results to return.
        project: Project filter (None = no filter).
        document_type: Document type filter (None = no filter).

    Returns:
        List of result objects compatible with _format_context() in runner.py.
        Each object has .payload dict and .score float attribute.
    """
    fetch_limit = limit * 2  # over-fetch for better fusion

    # ── 1. Vector search ─────────────────────────────────────
    vector_results = search_vector(
        query=query,
        limit=fetch_limit,
        project=project,
        document_type=document_type,
    )

    # ── 2. BM25 search ───────────────────────────────────────
    if bm25_store.is_ready:
        bm25_results = bm25_store.search(
            query=query,
            limit=fetch_limit,
            project=project,
            document_type=document_type,
        )
    else:
        bm25_results = []
        logger.debug("Hybrid: BM25 index not ready, vector-only search.")

    # ── 3. RRF Fusion ────────────────────────────────────────
    fused: dict[str, _FusedResult] = {}

    # Score vector results
    for rank, point in enumerate(vector_results, start=1):
        chunk_id = _get_chunk_id(point)
        if chunk_id not in fused:
            fused[chunk_id] = _FusedResult(
                chunk_id=chunk_id,
                payload=point.payload or {},
            )
        fused[chunk_id].rrf_score += 1.0 / (RRF_K + rank)
        fused[chunk_id].vector_rank = rank

    # Score BM25 results
    for rank, chunk in enumerate(bm25_results, start=1):
        chunk_id = chunk.get("chunk_id") or chunk.get("_point_id", f"bm25_{rank}")
        if chunk_id not in fused:
            fused[chunk_id] = _FusedResult(
                chunk_id=chunk_id,
                payload=chunk,
            )
        fused[chunk_id].rrf_score += 1.0 / (RRF_K + rank)
        fused[chunk_id].bm25_rank = rank

    # ── 4. Sort and return ───────────────────────────────────
    sorted_results = sorted(fused.values(), key=lambda r: r.rrf_score, reverse=True)
    top_results = sorted_results[:limit]

    if top_results:
        # Log fusion stats
        both = sum(1 for r in top_results if r.vector_rank > 0 and r.bm25_rank > 0)
        vec_only = sum(1 for r in top_results if r.vector_rank > 0 and r.bm25_rank == 0)
        bm25_only = sum(1 for r in top_results if r.bm25_rank > 0 and r.vector_rank == 0)
        logger.info(
            f"Hybrid: top-{limit} = {both} both + {vec_only} vector-only + {bm25_only} bm25-only "
            f"(from {len(vector_results)} vec + {len(bm25_results)} bm25)"
        )

    # Wrap as ScoredPoint-compatible objects
    return [_HybridResult(r.payload, r.rrf_score) for r in top_results]


def _get_chunk_id(point) -> str:
    """Extract chunk_id from a Qdrant ScoredPoint."""
    if hasattr(point, 'id'):
        return str(point.id)
    if hasattr(point, 'payload') and point.payload:
        return point.payload.get("chunk_id", str(id(point)))
    return str(id(point))


class _HybridResult:
    """Lightweight wrapper compatible with Qdrant ScoredPoint interface.

    runner.py's _format_context() accesses .payload dict,
    so this class provides that interface.
    """

    def __init__(self, payload: dict, score: float):
        self.payload = payload
        self.score = score

    def __repr__(self):
        title = self.payload.get("title", "?")[:40]
        return f"HybridResult(score={self.score:.4f}, title='{title}')"
