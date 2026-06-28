"""
Lab Orchestrator — Archival Memory (Graphiti + Neo4j)

Temporal knowledge graph for long-term memory.
Automatically extracts entities, relationships, and time-aware facts
from conversation turns.

Usage:
    from orchestrator.archival import archival_memory
    await archival_memory.ingest_turn(conv_id, user_msg, assistant_msg, agent)
    facts = await archival_memory.search("도핑 조건", limit=3)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_graphiti_instance = None
_initialized = False
_init_lock = asyncio.Lock()


async def _get_graphiti():
    """Lazy-initialize Graphiti client (singleton)."""
    global _graphiti_instance, _initialized

    if _initialized:
        return _graphiti_instance

    async with _init_lock:
        # Double-check after acquiring lock
        if _initialized:
            return _graphiti_instance

        try:
            from orchestrator.graphiti_client import create_graphiti_client

            _graphiti_instance, cfg = create_graphiti_client()
            await _graphiti_instance.build_indices_and_constraints()

            _initialized = True
            logger.info(
                f"Graphiti initialized: Neo4j={cfg.neo4j_uri}, "
                f"database={cfg.neo4j_database}, extraction_model={cfg.extraction_model}"
            )
            return _graphiti_instance

        except Exception as e:
            logger.error(f"Failed to initialize Graphiti: {e}", exc_info=True)
            # Allow retry on next call (don't set _initialized=True)
            _graphiti_instance = None
            return None


class ArchivalMemory:
    """Graphiti-backed long-term archival memory."""

    async def ingest_turn(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        agent_name: str = "orchestrator",
    ) -> bool:
        """Ingest a conversation turn as a Graphiti episode.

        Graphiti automatically extracts:
          - Entities (people, materials, methods, etc.)
          - Relationships (decided, uses, compared_with, etc.)
          - Temporal facts (when decisions were made)
        """
        result = await self.ingest_turn_result(
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=assistant_message,
            agent_name=agent_name,
        )
        return result["status"] == "ingested"

    async def ingest_turn_result(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        agent_name: str = "orchestrator",
    ) -> dict:
        """Ingest a conversation turn and return structured status details."""
        graphiti = await _get_graphiti()
        if not graphiti:
            return {
                "status": "failed",
                "conversation_id": conversation_id,
                "live_store_mutations": [],
                "error": "Graphiti client is unavailable",
            }

        try:
            from graphiti_core.nodes import EpisodeType

            ts = datetime.now(timezone.utc)
            # Keep episode names compact and backend-safe.
            safe_id = conversation_id.replace("-", "")
            episode_name = f"{safe_id[:12]}_{ts.strftime('%H%M%S')}"

            # Truncate long messages to prevent OOM during entity extraction
            MAX_INGEST_LEN = 2000
            user_text = user_message[:MAX_INGEST_LEN]
            assistant_text = assistant_message[:MAX_INGEST_LEN]
            if len(assistant_message) > MAX_INGEST_LEN:
                assistant_text += f"\n\n[... 이하 {len(assistant_message) - MAX_INGEST_LEN}자 생략]"

            episode_body = (
                f"[User]: {user_text}\n"
                f"[Assistant/{agent_name}]: {assistant_text}"
            )

            await graphiti.add_episode(
                name=episode_name,
                episode_body=episode_body,
                source=EpisodeType.text,
                source_description="lab_orchestrator_chat",
                reference_time=ts,
                group_id=f"session{safe_id[:12]}",
            )

            logger.info(
                f"Archival: ingested episode {episode_name} "
                f"({len(episode_body)} chars)"
            )
            return {
                "status": "ingested",
                "conversation_id": conversation_id,
                "episode_name": episode_name,
                "live_store_mutations": [
                    {"type": "graphiti_ingest", "conversation_id": conversation_id, "episode_name": episode_name}
                ],
            }

        except Exception as e:
            logger.warning(f"Archival ingestion failed: {e}")
            return {
                "status": "failed",
                "conversation_id": conversation_id,
                "live_store_mutations": [],
                "error": str(e),
            }

    async def search(
        self,
        query: str,
        limit: int = 5,
        group_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """Search archival memory for relevant facts.

        Returns list of dicts with keys: fact, created_at, source, score.
        """
        graphiti = await _get_graphiti()
        if not graphiti:
            return []

        try:
            results = await graphiti.search(
                query=query,
                num_results=limit,
                group_ids=group_ids,
            )

            facts = []
            for r in results:
                facts.append({
                    "fact": getattr(r, "fact", str(r)),
                    "created_at": getattr(r, "created_at", None),
                    "uuid": getattr(r, "uuid", None),
                    "score": getattr(r, "score", None),
                })

            logger.info(
                f"Archival: search '{query[:30]}...' → {len(facts)} results"
            )
            return facts

        except Exception as e:
            logger.warning(f"Archival search failed: {e}")
            return []

    async def get_graph_data(self, limit: int = 100) -> dict:
        """Get knowledge graph data for visualization.

        Returns dict with nodes and edges for force-graph rendering.
        """
        graphiti = await _get_graphiti()
        if not graphiti:
            return {"nodes": [], "edges": []}

        try:
            from neo4j import GraphDatabase
            from orchestrator.config import NEO4J_DATABASE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            nodes = []
            node_ids = set()
            edges = []
            with driver.session(database=NEO4J_DATABASE) as session:
                node_result = session.run(
                    """
                    MATCH (n)
                    OPTIONAL MATCH (n)-[r]-()
                    WITH n, count(r) AS degree
                    RETURN elementId(n) AS id,
                           coalesce(n.name, n.uuid, n.id, elementId(n)) AS name,
                           coalesce(n.summary, n.description, '') AS summary,
                           coalesce(n.group_id, '') AS group_id,
                           degree
                    ORDER BY degree DESC
                    LIMIT $limit
                    """,
                    limit=limit,
                )
                for record in node_result:
                    node_id = record["id"]
                    node_ids.add(node_id)
                    nodes.append({
                        "id": node_id,
                        "name": record["name"] or node_id,
                        "summary": record["summary"] or "",
                        "group": record["group_id"] or "default",
                        "degree": record["degree"] or 0,
                    })

                edge_result = session.run(
                    """
                    MATCH (a)-[r]->(b)
                    RETURN elementId(a) AS source,
                           elementId(b) AS target,
                           type(r) AS relation,
                           coalesce(r.fact, r.name, '') AS fact
                    LIMIT $limit
                    """,
                    limit=limit * 2,
                )
                for record in edge_result:
                    if record["source"] in node_ids and record["target"] in node_ids:
                        edges.append({
                            "source": record["source"],
                            "target": record["target"],
                            "relation": record["relation"] or "",
                            "fact": record["fact"] or "",
                        })
            driver.close()

            logger.info(
                f"Graph data: {len(nodes)} nodes, {len(edges)} edges"
            )
            return {"nodes": nodes, "edges": edges}

        except Exception as e:
            logger.warning(f"Graph data extraction failed: {e}")
            return {"nodes": [], "edges": []}

    async def healthcheck(self) -> dict:
        """Return whether Graphiti can initialize against Neo4j."""
        graphiti = await _get_graphiti()
        if not graphiti:
            return {"status": "failed", "backend": "neo4j", "error": "Graphiti client is unavailable"}
        return {"status": "ok", "backend": "neo4j"}


# Module-level singleton
archival_memory = ArchivalMemory()
