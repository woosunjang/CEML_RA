"""
Lab Orchestrator — Qdrant Vector Store

Ported from lab-research-agents with adapted imports.
"""

from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from orchestrator.config import QDRANT_URL, QDRANT_COLLECTION
from llm.pool import embed_texts


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
try:
    _client = QdrantClient(url=QDRANT_URL, timeout=5)
    _client.get_collections()
except Exception:
    _client = None


def _get_client() -> Optional[QdrantClient]:
    """Get Qdrant client, reconnecting if needed."""
    global _client
    if _client is None:
        try:
            _client = QdrantClient(url=QDRANT_URL, timeout=5)
            _client.get_collections()
        except Exception:
            return None
    return _client


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_vector(
    query: str,
    limit: int = 10,
    project: Optional[str] = None,
    document_type: Optional[str] = None,
) -> list:
    """
    Vector search in Qdrant with optional metadata filters.

    Returns list of ScoredPoint objects with payloads.
    """
    client = _get_client()
    if not client:
        return []

    query_vector = embed_texts([query])
    if not query_vector:
        return []

    conditions = []
    if project and project != "all":
        conditions.append(
            FieldCondition(key="project", match=MatchValue(value=project))
        )
    if document_type and document_type != "all":
        conditions.append(
            FieldCondition(key="document_type", match=MatchValue(value=document_type))
        )

    search_filter = Filter(must=conditions) if conditions else None

    try:
        results = client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_vector[0],
            query_filter=search_filter,
            limit=limit,
            with_payload=True,
        ).points
    except Exception:
        return []

    return results


def scroll_all_chunks(batch_size: int = 100) -> list:
    """Scroll through all chunks in the collection. Used for BM25 index building."""
    client = _get_client()
    if not client:
        return []

    all_points = []
    offset = None

    try:
        while True:
            points, next_offset = client.scroll(
                collection_name=QDRANT_COLLECTION,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            all_points.extend(points)
            if next_offset is None:
                break
            offset = next_offset
    except Exception:
        pass

    return all_points
