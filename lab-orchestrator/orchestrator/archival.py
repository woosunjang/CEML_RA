"""
Lab Orchestrator — Archival Memory (Graphiti + FalkorDB)

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
            from graphiti_core import Graphiti
            from graphiti_core.llm_client import LLMConfig, OpenAIClient
            from graphiti_core.embedder.openai import (
                OpenAIEmbedder, OpenAIEmbedderConfig,
            )
            from graphiti_core.driver.falkordb_driver import FalkorDriver
            from orchestrator.config import (
                OPENAI_EMBEDDING_MODEL,
            )

            # Parse FalkorDB host/port from config
            falkor_host = "localhost"
            falkor_port = 6379

            # Use Nano model for extraction (cost-efficient)
            from orchestrator.model_profiles import profile_manager
            extraction_model = "gpt-5.4-nano"
            if profile_manager.active_profile == "cost":
                extraction_model = "gpt-4.1-nano"

            llm_config = LLMConfig(
                model=extraction_model,
                small_model=extraction_model,
                temperature=0.0,
            )
            # Graphiti defaults reasoning_effort='minimal' which gpt-5.4 doesn't support.
            # gpt-5.4 series accepts: 'none', 'low', 'medium', 'high', 'xhigh'.
            # gpt-4.1 series ignores reasoning param (non-reasoning model).
            reasoning = "low" if extraction_model.startswith("gpt-5") else None
            llm_client = OpenAIClient(config=llm_config, reasoning=reasoning)

            embedder = OpenAIEmbedder(
                config=OpenAIEmbedderConfig(
                    model=OPENAI_EMBEDDING_MODEL,
                )
            )

            # Create FalkorDB driver directly
            graph_driver = FalkorDriver(
                host=falkor_host,
                port=falkor_port,
            )

            _graphiti_instance = Graphiti(
                graph_driver=graph_driver,
                llm_client=llm_client,
                embedder=embedder,
            )
            await _graphiti_instance.build_indices_and_constraints()

            _initialized = True
            logger.info(
                f"Graphiti initialized: FalkorDB={falkor_host}:{falkor_port}, "
                f"extraction_model={extraction_model}"
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
    ):
        """Ingest a conversation turn as a Graphiti episode.

        Graphiti automatically extracts:
          - Entities (people, materials, methods, etc.)
          - Relationships (decided, uses, compared_with, etc.)
          - Temporal facts (when decisions were made)
        """
        graphiti = await _get_graphiti()
        if not graphiti:
            return

        try:
            from graphiti_core.nodes import EpisodeType

            ts = datetime.now(timezone.utc)
            # Remove hyphens from IDs (RediSearch treats them as operators)
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

        except Exception as e:
            logger.warning(f"Archival ingestion failed: {e}")

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
            from falkordb import FalkorDB

            db = FalkorDB(host="localhost", port=6379)
            graph = db.select_graph("graphiti")

            # Get entities (nodes)
            node_result = graph.query(
                f"MATCH (n:Entity) "
                f"OPTIONAL MATCH (n)-[r]-() "
                f"WITH n, count(r) as degree "
                f"RETURN n.name, n.summary, n.group_id, degree "
                f"ORDER BY degree DESC LIMIT {limit}"
            )
            nodes = []
            node_set = set()
            for row in node_result.result_set:
                name = row[0]
                if name and name not in node_set:
                    node_set.add(name)
                    nodes.append({
                        "id": name,
                        "summary": row[1] or "",
                        "group": row[2] or "default",
                        "degree": row[3] or 0,
                    })

            # Get relationships (edges)
            edge_result = graph.query(
                f"MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) "
                f"RETURN a.name, b.name, r.name, r.fact "
                f"LIMIT {limit * 2}"
            )
            edges = []
            for row in edge_result.result_set:
                if row[0] in node_set and row[1] in node_set:
                    edges.append({
                        "source": row[0],
                        "target": row[1],
                        "relation": row[2] or "",
                        "fact": row[3] or "",
                    })

            logger.info(
                f"Graph data: {len(nodes)} nodes, {len(edges)} edges"
            )
            return {"nodes": nodes, "edges": edges}

        except Exception as e:
            logger.warning(f"Graph data extraction failed: {e}")
            return {"nodes": [], "edges": []}


# Module-level singleton
archival_memory = ArchivalMemory()
