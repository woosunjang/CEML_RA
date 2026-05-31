"""
lab-paper-scout: RAG Bridge
Syncs analyzed papers from Scout's SQLite into the shared Qdrant vector store,
making them available to lab-research-agents for RAG queries.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

import openai

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_COLLECTION = "lab_research_chunks"


class RAGBridge:
    """Bridges paper-scout analyzed papers → Qdrant vector store."""

    def __init__(self, config: dict):
        """
        Args:
            config: The 'rag' section from config.yaml.
        """
        self.enabled = config.get("enabled", False)
        if not self.enabled:
            return

        self.qdrant_url = config.get("qdrant_url", "http://localhost:6333")
        self.collection = config.get("collection", DEFAULT_COLLECTION)
        self.chunk_size = config.get("chunk_size", DEFAULT_CHUNK_SIZE)
        self.chunk_overlap = config.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP)
        self.embedding_model = config.get("embedding_model", DEFAULT_EMBEDDING_MODEL)

        # OpenAI API key
        api_key_env = config.get("openai_api_key_env", "OPENAI_API_KEY")
        api_key = os.environ.get(api_key_env, "")
        if not api_key:
            logger.warning(f"RAG bridge: {api_key_env} not set, bridge disabled.")
            self.enabled = False
            return

        self.openai_client = openai.OpenAI(api_key=api_key)

        # Qdrant client
        try:
            self.client = QdrantClient(url=self.qdrant_url, timeout=10)
            self.client.get_collections()  # connection test
            logger.info(f"RAG bridge connected to Qdrant at {self.qdrant_url}")
            # Check if collection already exists
            existing = {c.name for c in self.client.get_collections().collections}
            self._collection_ready = self.collection in existing
        except Exception as e:
            logger.warning(f"RAG bridge: Qdrant unavailable ({e}), bridge disabled.")
            self.enabled = False

    # ─── Public API ────────────────────────────────────────────

    def sync_paper(
        self,
        paper_id: str,
        paper: dict,
        extracted_path: Path,
        analysis: dict,
    ) -> int:
        """
        Embed and upsert a single paper's text into Qdrant.

        Returns:
            Number of chunks upserted.
        """
        if not self.enabled:
            return 0

        # Skip if already synced
        if self._paper_exists_in_qdrant(paper_id):
            return 0

        # Load extracted text
        if not extracted_path.exists():
            logger.debug(f"RAG bridge: no extracted text for {paper_id}, skipping.")
            return 0

        with open(extracted_path, "r", encoding="utf-8") as f:
            extracted = json.load(f)

        full_text = extracted.get("full_text", "")
        if not full_text or len(full_text) < 100:
            return 0

        # Chunk
        chunks = self._chunk_text(full_text)
        if not chunks:
            return 0

        # Build metadata
        topics = json.loads(paper.get("topics_json", "[]")) if isinstance(
            paper.get("topics_json"), str
        ) else paper.get("topics_json", [])
        tags = analysis.get("tags", [])

        # Embed + upsert
        texts = [c["text"] for c in chunks]
        vectors = self._embed_texts(texts)
        if not vectors:
            return 0

        self._ensure_collection(len(vectors[0]))

        points = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            point_id = self._make_chunk_id(paper_id, i)
            payload = {
                "chunk_id": point_id,
                "document_id": paper_id,
                "title": paper.get("title", ""),
                "source_file": paper_id,
                "document_type": "paper",
                "project": "paper-scout",
                "topic": topics[0] if topics else "unknown",
                "year": paper.get("year"),
                "relevance_score": analysis.get("relevance_score", 0),
                "tags": tags,
                "chunk_index": i,
                "text": chunk["text"],
            }
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        self.client.upsert(collection_name=self.collection, points=points)
        logger.info(f"RAG bridge: synced {paper['title'][:60]}... ({len(points)} chunks)")
        return len(points)

    def sync_all_pending(self, store, processed_dir: Path) -> int:
        """
        Sync all analyzed papers that haven't been embedded yet.

        Returns:
            Total number of chunks upserted.
        """
        if not self.enabled:
            return 0

        papers = store.get_papers_by_status("analyzed")
        total_chunks = 0

        for paper in papers:
            paper_id = paper["id"]
            extracted_path = processed_dir / f"{paper_id}.json"

            analysis_json = paper.get("analysis_json", "{}")
            if isinstance(analysis_json, str):
                try:
                    analysis = json.loads(analysis_json)
                except json.JSONDecodeError:
                    analysis = {}
            else:
                analysis = analysis_json or {}

            n = self.sync_paper(paper_id, paper, extracted_path, analysis)
            total_chunks += n

        if total_chunks > 0:
            logger.info(f"RAG bridge: total {total_chunks} chunks synced.")
        return total_chunks

    # ─── Private helpers ───────────────────────────────────────

    def _chunk_text(self, text: str) -> List[Dict]:
        """Split text into overlapping chunks."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end]
            if chunk_text.strip():
                chunks.append({"text": chunk_text, "start": start, "end": end})
            start += self.chunk_size - self.chunk_overlap
        return chunks

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed texts using OpenAI API."""
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"RAG bridge embedding error: {e}")
            return []

    def _ensure_collection(self, vector_size: int):
        """Create collection if it doesn't exist."""
        collections = self.client.get_collections().collections
        existing = {c.name for c in collections}
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"RAG bridge: created collection '{self.collection}'")
            self._collection_ready = True

    def _paper_exists_in_qdrant(self, paper_id: str) -> bool:
        """Check if paper chunks already exist in Qdrant."""
        if not getattr(self, '_collection_ready', False):
            return False
        try:
            results = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=paper_id),
                        )
                    ]
                ),
                limit=1,
            )
            return len(results[0]) > 0
        except Exception:
            return False

    @staticmethod
    def _make_chunk_id(paper_id: str, chunk_index: int) -> str:
        """Generate a deterministic UUID-like string for a chunk."""
        raw = f"{paper_id}::{chunk_index}"
        return hashlib.md5(raw.encode()).hexdigest()
