"""
Lab Orchestrator — Qdrant Vector Store

Ported from lab-research-agents with adapted imports.
"""

from __future__ import annotations

import uuid
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


MEMORY_NOTE_DOCUMENT_TYPE = "research_memory_note"


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


def _ensure_collection_for_vector(client: QdrantClient, vector_size: int) -> None:
    collections = client.get_collections().collections
    if any(collection.name == QDRANT_COLLECTION for collection in collections):
        return
    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def memory_note_chunk_id(*, thread_id: str, memory_note_id: str) -> str:
    return f"research_memory_note:{thread_id}:{memory_note_id}"


def build_memory_note_payload(
    *,
    thread_id: str,
    memory_note_id: str,
    artifact_ref: str,
    text: str,
    created_at: str,
    claim_refs: list[str] | None = None,
    source_refs: list[str] | None = None,
) -> dict:
    return {
        "chunk_id": memory_note_chunk_id(thread_id=thread_id, memory_note_id=memory_note_id),
        "title": f"Weekly research memory note: {thread_id}",
        "text": text,
        "thread_id": thread_id,
        "memory_note_id": memory_note_id,
        "artifact_ref": artifact_ref,
        "claim_refs": list(claim_refs or []),
        "source_refs": list(source_refs or []),
        "created_at": created_at,
        "document_type": MEMORY_NOTE_DOCUMENT_TYPE,
        "section": "weekly_memory_note",
        "source": "research_weekly_loop_v0",
    }


def upsert_memory_note(
    *,
    thread_id: str,
    memory_note_id: str,
    artifact_ref: str,
    text: str,
    created_at: str,
    claim_refs: list[str] | None = None,
    source_refs: list[str] | None = None,
) -> dict:
    """Upsert a durable research memory note into Qdrant.

    This is intentionally separate from Scout paper ingestion so weekly memory
    notes can be searched as user-reviewed research memory, not paper chunks.
    """
    chunk_id = memory_note_chunk_id(thread_id=thread_id, memory_note_id=memory_note_id)
    payload = build_memory_note_payload(
        thread_id=thread_id,
        memory_note_id=memory_note_id,
        artifact_ref=artifact_ref,
        text=text,
        created_at=created_at,
        claim_refs=claim_refs,
        source_refs=source_refs,
    )
    client = _get_client()
    if not client:
        return {
            "status": "unavailable",
            "collection": QDRANT_COLLECTION,
            "chunk_id": chunk_id,
            "point_id": None,
            "payload": payload,
            "live_store_mutations": [],
            "error": "Qdrant client is unavailable",
        }

    vectors = embed_texts([text])
    if not vectors:
        return {
            "status": "embedding_unavailable",
            "collection": QDRANT_COLLECTION,
            "chunk_id": chunk_id,
            "point_id": None,
            "payload": payload,
            "live_store_mutations": [],
            "error": "Embedding generation returned no vectors",
        }

    point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))
    try:
        _ensure_collection_for_vector(client, len(vectors[0]))
        client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vectors[0],
                    payload=payload,
                )
            ],
        )
    except Exception as exc:
        return {
            "status": "failed",
            "collection": QDRANT_COLLECTION,
            "chunk_id": chunk_id,
            "point_id": point_id,
            "payload": payload,
            "live_store_mutations": [],
            "error": str(exc),
        }

    return {
        "status": "upserted",
        "collection": QDRANT_COLLECTION,
        "chunk_id": chunk_id,
        "point_id": point_id,
        "payload": payload,
        "live_store_mutations": [
            {
                "type": "qdrant_upsert",
                "collection": QDRANT_COLLECTION,
                "point_id": point_id,
                "chunk_id": chunk_id,
            }
        ],
    }


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
