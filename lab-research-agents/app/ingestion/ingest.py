"""
Lab Research Agents — Document Ingestion

Orchestrates: parse → chunk → embed → upsert into Qdrant.
"""

import uuid
from pathlib import Path
from typing import Optional, Union

from app.ingestion.parsers import parse_file
from app.ingestion.chunker import build_chunks
from app.retrieval.vector_store import ensure_collection, upsert_chunks
from app.retrieval.keyword_store import bm25_store


def ingest_document(
    file_path: Union[str, Path],
    title: Optional[str] = None,
    document_type: str = "other",
    project: str = "general",
    year: Optional[int] = None,
) -> dict:
    """
    Ingest a single document into the vector store.

    Pipeline:
        1. Generate a new document UUID.
        2. Parse the file into pages.
        3. Build text chunks with metadata.
        4. Upsert chunks (embedding + Qdrant storage).
        5. Rebuild BM25 keyword index.

    Args:
        file_path: Path to the file to ingest.
        title: Document title (defaults to filename if None).
        document_type: One of the DocumentType enum values.
        project: Project tag for metadata filtering.
        year: Optional publication year.

    Returns:
        dict with "document_id" and "num_chunks".
    """
    path = Path(file_path)
    if title is None:
        title = path.stem

    document_id = str(uuid.uuid4())

    # 1. Parse
    pages = parse_file(path)
    if not pages:
        return {"document_id": document_id, "num_chunks": 0}

    # 2. Chunk
    chunks = build_chunks(
        pages=pages,
        document_id=document_id,
        title=title,
        source_file=path.name,
        document_type=document_type,
        project=project,
        year=year,
    )
    if not chunks:
        return {"document_id": document_id, "num_chunks": 0}

    # 3. Embed + Upsert
    upsert_chunks(chunks)

    # 4. Rebuild BM25 keyword index
    bm25_store.reload_from_qdrant()

    return {"document_id": document_id, "num_chunks": len(chunks)}
