"""
Lab Orchestrator — Scout → Qdrant Ingest

Reads analyzed papers from Scout DB and indexes them into Qdrant
for RAG retrieval by the Literature Agent.
"""

import hashlib
import json
import logging
import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.config import (
    OPENAI_API_KEY, OPENAI_EMBEDDING_MODEL,
    QDRANT_URL, QDRANT_COLLECTION, SCOUT_DB_PATH, DATA_DIR,
)

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536  # text-embedding-3-small
BATCH_SIZE = 50
SYNC_STATE_PATH = DATA_DIR / "scout_sync_state.json"


def get_scout_papers() -> list[dict]:
    """Read analyzed papers from Scout DB."""
    if not SCOUT_DB_PATH.exists():
        logger.error(f"Scout DB not found: {SCOUT_DB_PATH}")
        return []

    conn = sqlite3.connect(str(SCOUT_DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, authors, source, url, year, abstract,
               topics_json, relevance_score, summary, analysis_json, venue,
               analyzed_at
        FROM papers
        WHERE status = 'analyzed' AND summary IS NOT NULL
        ORDER BY relevance_score DESC
    """)
    papers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    logger.info(f"Loaded {len(papers)} analyzed papers from Scout DB")
    return papers


def build_chunks(papers: list[dict]) -> list[dict]:
    """Build text chunks from papers for embedding."""
    chunks = []
    for paper in papers:
        paper_id = paper["id"]
        title = paper.get("title", "")
        summary = paper.get("summary", "")
        abstract = paper.get("abstract") or ""
        authors = paper.get("authors", "")
        year = paper.get("year", 0)
        venue = paper.get("venue", "")
        topics = paper.get("topics_json", "[]")
        score = paper.get("relevance_score", 0)

        # Parse analysis_json for extra content
        analysis = {}
        if paper.get("analysis_json"):
            try:
                analysis = json.loads(paper["analysis_json"])
            except json.JSONDecodeError:
                pass

        # Main chunk: summary
        if summary:
            text = f"Title: {title}\n\n{summary}"
            if abstract:
                text += f"\n\nAbstract: {abstract[:500]}"

            chunks.append({
                "chunk_id": f"{paper_id}_summary",
                "text": text,
                "title": title,
                "authors": authors,
                "year": year,
                "venue": venue,
                "source": paper.get("source", ""),
                "url": paper.get("url", ""),
                "topics": topics,
                "relevance_score": score,
                "document_type": "scout_paper",
                "section": "summary",
                "paper_id": paper_id,
                "analyzed_at": paper.get("analyzed_at", ""),
            })

        # Analysis chunk (if exists and different from summary)
        analysis_kr = analysis.get("summary_kr", "")
        if analysis_kr and analysis_kr != summary:
            chunks.append({
                "chunk_id": f"{paper_id}_analysis",
                "text": f"Title: {title}\n\n{analysis_kr}",
                "title": title,
                "authors": authors,
                "year": year,
                "venue": venue,
                "source": paper.get("source", ""),
                "url": paper.get("url", ""),
                "topics": topics,
                "relevance_score": score,
                "document_type": "scout_paper",
                "section": "analysis",
                "paper_id": paper_id,
                "analyzed_at": paper.get("analyzed_at", ""),
            })

    logger.info(f"Built {len(chunks)} chunks from {len(papers)} papers")
    return chunks


def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Embed texts using OpenAI."""
    response = client.embeddings.create(
        model=OPENAI_EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def _load_state() -> dict:
    if not SYNC_STATE_PATH.exists():
        return {"chunks": {}}
    try:
        return json.loads(SYNC_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"chunks": {}}


def _save_state(state: dict):
    SYNC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYNC_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _chunk_hash(chunk: dict) -> str:
    content = json.dumps(
        {
            "text": chunk.get("text", ""),
            "title": chunk.get("title", ""),
            "summary": chunk.get("summary", ""),
            "analyzed_at": chunk.get("analyzed_at", ""),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _ensure_collection(qdrant: QdrantClient, *, full_reset: bool = False):
    """Create collection if missing. Reset only when explicitly requested."""
    if full_reset:
        try:
            qdrant.delete_collection(QDRANT_COLLECTION)
            logger.info(f"Deleted existing collection: {QDRANT_COLLECTION}")
        except Exception:
            pass

    try:
        collections = qdrant.get_collections().collections
        if any(c.name == QDRANT_COLLECTION for c in collections):
            logger.info(f"Using existing collection: {QDRANT_COLLECTION}")
            return
    except Exception:
        pass

    qdrant.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(
            size=EMBEDDING_DIM,
            distance=Distance.COSINE,
        ),
    )
    logger.info(f"Created collection: {QDRANT_COLLECTION}")


def ingest_to_qdrant(chunks: list[dict], *, full_reset: bool = False):
    """Incrementally upsert Scout chunks into Qdrant."""
    qdrant = QdrantClient(url=QDRANT_URL)
    openai = OpenAI(api_key=OPENAI_API_KEY)

    _ensure_collection(qdrant, full_reset=full_reset)
    state = {"chunks": {}} if full_reset else _load_state()
    synced_chunks = state.setdefault("chunks", {})

    changed_chunks = []
    for chunk in chunks:
        content_hash = _chunk_hash(chunk)
        chunk["content_hash"] = content_hash
        if synced_chunks.get(chunk["chunk_id"]) != content_hash:
            changed_chunks.append(chunk)

    if not changed_chunks:
        logger.info("No Scout chunks changed; Qdrant is already up to date")
        return

    # Batch embed and upsert
    total_upserted = 0
    for i in range(0, len(changed_chunks), BATCH_SIZE):
        batch = changed_chunks[i:i + BATCH_SIZE]
        texts = [c["text"] for c in batch]

        logger.info(f"Embedding batch {i // BATCH_SIZE + 1} ({len(batch)} chunks)...")
        embeddings = embed_texts(openai, texts)

        points = []
        for chunk, embedding in zip(batch, embeddings):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"]))
            payload = {k: v for k, v in chunk.items() if k != "text"}
            payload["text"] = chunk["text"]

            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload,
            ))

        qdrant.upsert(
            collection_name=QDRANT_COLLECTION,
            points=points,
        )
        total_upserted += len(points)
        for chunk in batch:
            synced_chunks[chunk["chunk_id"]] = chunk["content_hash"]
        logger.info(f"  Upserted {total_upserted}/{len(changed_chunks)} changed chunks")

    from datetime import datetime, timezone
    state["last_sync_at"] = datetime.now(timezone.utc).isoformat()
    state["collection"] = QDRANT_COLLECTION
    state["total_known_chunks"] = len(synced_chunks)
    _save_state(state)

    logger.info(
        f"Ingestion complete: {total_upserted} changed chunks in {QDRANT_COLLECTION}"
    )

    # Verify
    info = qdrant.get_collection(QDRANT_COLLECTION)
    logger.info(f"Collection verified: {info.points_count} points")


def main():
    full_reset = "--full-reset" in sys.argv or "--reset" in sys.argv
    papers = get_scout_papers()
    if not papers:
        logger.error("No papers to ingest")
        return

    chunks = build_chunks(papers)
    if not chunks:
        logger.error("No chunks built")
        return

    ingest_to_qdrant(chunks, full_reset=full_reset)


if __name__ == "__main__":
    main()
