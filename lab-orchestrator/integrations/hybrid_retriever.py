"""
Lab Orchestrator — Hybrid Retriever

Combines vector search (Qdrant) + BM25 using Reciprocal Rank Fusion.
Ported from lab-research-agents.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from integrations.qdrant import search_vector
from integrations.keyword_store import bm25_store

logger = logging.getLogger(__name__)

RRF_K = 60


@dataclass
class _FusedResult:
    chunk_id: str
    payload: dict = field(default_factory=dict)
    rrf_score: float = 0.0
    vector_rank: int = 0
    bm25_rank: int = 0


class HybridResult:
    """Wrapper compatible with Qdrant ScoredPoint interface."""
    def __init__(self, payload: dict, score: float):
        self.payload = payload
        self.score = score

    def __repr__(self):
        title = self.payload.get("title", "?")[:40]
        return f"HybridResult(score={self.score:.4f}, title='{title}')"


def hybrid_search(
    query: str,
    limit: int = 10,
    project: Optional[str] = None,
    document_type: Optional[str] = None,
) -> list[HybridResult]:
    """Hybrid search using RRF fusion of vector + BM25."""
    fetch_limit = limit * 2

    vector_results = search_vector(
        query=query, limit=fetch_limit,
        project=project, document_type=document_type,
    )

    if bm25_store.is_ready:
        bm25_results = bm25_store.search(
            query=query, limit=fetch_limit,
            project=project, document_type=document_type,
        )
    else:
        bm25_results = []

    fused: dict[str, _FusedResult] = {}

    for rank, point in enumerate(vector_results, start=1):
        chunk_id = _get_chunk_id(point)
        if chunk_id not in fused:
            fused[chunk_id] = _FusedResult(
                chunk_id=chunk_id, payload=point.payload or {},
            )
        fused[chunk_id].rrf_score += 1.0 / (RRF_K + rank)
        fused[chunk_id].vector_rank = rank

    for rank, chunk in enumerate(bm25_results, start=1):
        chunk_id = chunk.get("chunk_id") or chunk.get("_point_id", f"bm25_{rank}")
        if chunk_id not in fused:
            fused[chunk_id] = _FusedResult(chunk_id=chunk_id, payload=chunk)
        fused[chunk_id].rrf_score += 1.0 / (RRF_K + rank)
        fused[chunk_id].bm25_rank = rank

    sorted_results = sorted(fused.values(), key=lambda r: r.rrf_score, reverse=True)
    top_results = sorted_results[:limit]

    if top_results:
        both = sum(1 for r in top_results if r.vector_rank > 0 and r.bm25_rank > 0)
        vec_only = sum(1 for r in top_results if r.vector_rank > 0 and r.bm25_rank == 0)
        bm25_only = sum(1 for r in top_results if r.bm25_rank > 0 and r.vector_rank == 0)
        logger.info(
            f"Hybrid: top-{limit} = {both} both + {vec_only} vector-only + {bm25_only} bm25-only"
        )

    return [HybridResult(r.payload, r.rrf_score) for r in top_results]


def _get_chunk_id(point) -> str:
    if hasattr(point, "id"):
        return str(point.id)
    if hasattr(point, "payload") and point.payload:
        return point.payload.get("chunk_id", str(id(point)))
    return str(id(point))
