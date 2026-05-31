"""
Lab Research Agents — Qdrant Vector Store

Collection management, chunk upsert with embeddings, and vector search
with metadata filters.
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

from app.config import QDRANT_URL, QDRANT_STORAGE_PATH, QDRANT_COLLECTION
from app.llm.openai_client import embed_texts
from app.schemas import ChunkMetadata

# ---------------------------------------------------------------------------
# Client (Docker server mode, local fallback)
# ---------------------------------------------------------------------------
try:
    _client = QdrantClient(url=QDRANT_URL, timeout=5)
    _client.get_collections()  # connection test
except Exception:
    # Fallback to local file mode for development
    _client = QdrantClient(path=str(QDRANT_STORAGE_PATH))


# ---------------------------------------------------------------------------
# Collection management
# ---------------------------------------------------------------------------

def ensure_collection(vector_size: int) -> None:
    """
    Create the Qdrant collection if it does not exist.

    Args:
        vector_size: Dimensionality of the embedding vectors.
    """
    collections = _client.get_collections().collections
    existing_names = {c.name for c in collections}

    if QDRANT_COLLECTION not in existing_names:
        _client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def upsert_chunks(chunks: list[ChunkMetadata], batch_size: int = 64) -> None:
    """
    Embed chunks and upsert them into Qdrant.

    Args:
        chunks: List of ChunkMetadata objects to store.
        batch_size: Number of chunks to embed per API call.
    """
    if not chunks:
        return

    # Process in batches to avoid API limits
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.text for c in batch]
        vectors = embed_texts(texts)

        # Ensure collection exists (detect vector size from first batch)
        if i == 0 and vectors:
            ensure_collection(vector_size=len(vectors[0]))

        points = []
        for chunk, vector in zip(batch, vectors):
            payload = chunk.model_dump()
            # Convert enum to string for Qdrant payload
            payload["document_type"] = str(payload["document_type"])
            points.append(
                PointStruct(
                    id=chunk.chunk_id,
                    vector=vector,
                    payload=payload,
                )
            )

        _client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=points,
        )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_vector(
    query: str,
    limit: int = 10,
    project: Optional[str] = None,
    document_type: Optional[str] = None,
):
    """
    Perform vector search in Qdrant with optional metadata filters.

    Args:
        query: The search query text (will be embedded).
        limit: Maximum number of results to return.
        project: Filter by project name. None or "all" = no filter.
        document_type: Filter by document type. None or "all" = no filter.

    Returns:
        List of Qdrant ScoredPoint objects with payloads.
    """
    # Embed the query
    query_vector = embed_texts([query])
    if not query_vector:
        return []

    # Build metadata filter
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
        results = _client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_vector[0],
            query_filter=search_filter,
            limit=limit,
            with_payload=True,
        ).points
    except Exception:
        # Collection does not exist yet (no documents ingested)
        return []

    return results
