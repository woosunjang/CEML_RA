"""Graphiti client construction for Neo4j-backed archival memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GraphitiConnectionConfig:
    neo4j_uri: str
    neo4j_user: str
    neo4j_database: str
    embedding_model: str
    extraction_model: str


class GraphitiConfigError(RuntimeError):
    """Raised when Graphiti cannot be configured safely."""


def graphiti_connection_config() -> GraphitiConnectionConfig:
    from orchestrator.config import (
        NEO4J_DATABASE,
        NEO4J_PASSWORD,
        NEO4J_URI,
        NEO4J_USER,
        OPENAI_EMBEDDING_MODEL,
    )

    if not NEO4J_PASSWORD:
        raise GraphitiConfigError("NEO4J_PASSWORD is not set")

    from orchestrator.model_profiles import profile_manager

    extraction_model = "gpt-5.4-nano"
    if profile_manager.active_profile == "cost":
        extraction_model = "gpt-4.1-nano"

    return GraphitiConnectionConfig(
        neo4j_uri=NEO4J_URI,
        neo4j_user=NEO4J_USER,
        neo4j_database=NEO4J_DATABASE,
        embedding_model=OPENAI_EMBEDDING_MODEL,
        extraction_model=extraction_model,
    )


def create_graphiti_client() -> tuple[Any, GraphitiConnectionConfig]:
    """Create a Graphiti client using the canonical Neo4j backend."""
    cfg = graphiti_connection_config()

    from graphiti_core import Graphiti
    try:
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.llm_client.openai_client import OpenAIClient
    except ImportError:
        from graphiti_core.llm_client import LLMConfig, OpenAIClient
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

    llm_config = LLMConfig(
        model=cfg.extraction_model,
        small_model=cfg.extraction_model,
        temperature=0.0,
    )
    reasoning = "low" if cfg.extraction_model.startswith("gpt-5") else None
    try:
        llm_client = OpenAIClient(config=llm_config, reasoning=reasoning)
    except TypeError:
        llm_client = OpenAIClient(config=llm_config)

    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(model=cfg.embedding_model)
    )

    try:
        graphiti = Graphiti(
            cfg.neo4j_uri,
            cfg.neo4j_user,
            graphiti_connection_password(),
            llm_client=llm_client,
            embedder=embedder,
        )
    except TypeError:
        from graphiti_core.driver.neo4j_driver import Neo4jDriver

        graph_driver = Neo4jDriver(
            uri=cfg.neo4j_uri,
            user=cfg.neo4j_user,
            password=graphiti_connection_password(),
            database=cfg.neo4j_database,
        )
        graphiti = Graphiti(
            graph_driver=graph_driver,
            llm_client=llm_client,
            embedder=embedder,
        )
    return graphiti, cfg


def graphiti_connection_password() -> str:
    from orchestrator.config import NEO4J_PASSWORD

    return NEO4J_PASSWORD
