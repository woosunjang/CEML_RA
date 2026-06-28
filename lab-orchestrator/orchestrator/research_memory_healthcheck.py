"""Preflight checks for Weekly Useful Research Loop memory surfaces."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import httpx

from orchestrator.config import (
    NEO4J_DATABASE,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_MODEL,
    QDRANT_COLLECTION,
    QDRANT_URL,
    SCOUT_DB_PATH,
)
from orchestrator.research_thread import (
    load_research_thread,
    resolve_artifacts_dir,
    research_thread_paths,
)


def run_research_memory_healthcheck(
    *,
    thread_id: str = "materials_ontology_kg",
    artifacts_dir: Path | None = None,
    deep: bool = False,
) -> dict[str, Any]:
    return asyncio.run(async_run_research_memory_healthcheck(
        thread_id=thread_id,
        artifacts_dir=artifacts_dir,
        deep=deep,
    ))


async def async_run_research_memory_healthcheck(
    *,
    thread_id: str = "materials_ontology_kg",
    artifacts_dir: Path | None = None,
    deep: bool = False,
) -> dict[str, Any]:
    """Return a JSON-serializable preflight report.

    Deep mode initializes Graphiti, which may create Neo4j indices/constraints.
    Shallow mode only checks importability and direct service connections.
    """
    resolved_artifacts = resolve_artifacts_dir(artifacts_dir)
    checks = {
        "artifact_root": check_artifact_root(resolved_artifacts),
        "research_thread": check_research_thread(thread_id, artifacts_dir),
        "scout": check_scout_db(),
        "qdrant": check_qdrant(),
        "neo4j": check_neo4j(),
        "graphiti": await check_graphiti(deep=deep),
        "openai_embedding": check_openai_embedding(),
    }
    status = "ok" if all(check["ok"] for check in checks.values()) else "degraded"
    return {
        "schema_version": 1,
        "thread_id": thread_id,
        "status": status,
        "deep": deep,
        "checks": checks,
        "summary": summarize_checks(checks),
    }


def check_artifact_root(artifacts_dir: Path) -> dict[str, Any]:
    return {
        "ok": artifacts_dir.exists(),
        "path": str(artifacts_dir),
        "writable": _is_writable_dir(artifacts_dir),
    }


def check_research_thread(thread_id: str, artifacts_dir: Path | None) -> dict[str, Any]:
    paths = research_thread_paths(thread_id, artifacts_dir)
    try:
        thread = load_research_thread(thread_id, artifacts_dir=artifacts_dir)
        return {
            "ok": True,
            "thread_id": thread.get("thread_id"),
            "json_path": str(paths.json_path),
            "markdown_path": str(paths.markdown_path),
            "research_state": thread.get("research_state"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "thread_id": thread_id,
            "json_path": str(paths.json_path),
            "markdown_path": str(paths.markdown_path),
            "error": str(exc),
        }


def check_scout_db() -> dict[str, Any]:
    path = SCOUT_DB_PATH
    if not path.exists():
        return {"ok": False, "path": str(path), "error": "Scout DB file does not exist"}
    try:
        uri = f"file:{path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2)
        try:
            conn.row_factory = sqlite3.Row
            total = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
            analyzed = conn.execute(
                "SELECT COUNT(*) FROM papers WHERE status='analyzed'"
            ).fetchone()[0]
            topic_hits = conn.execute(
                """
                SELECT COUNT(*) FROM papers
                WHERE status='analyzed'
                  AND (
                    title LIKE '%materials%'
                    OR abstract LIKE '%materials%'
                    OR title LIKE '%ontology%'
                    OR abstract LIKE '%ontology%'
                    OR title LIKE '%knowledge graph%'
                    OR abstract LIKE '%knowledge graph%'
                  )
                """
            ).fetchone()[0]
        finally:
            conn.close()
        return {
            "ok": analyzed > 0,
            "path": str(path),
            "total": total,
            "analyzed": analyzed,
            "materials_ontology_hits": topic_hits,
        }
    except Exception as exc:
        return {"ok": False, "path": str(path), "error": str(exc)}


def check_qdrant() -> dict[str, Any]:
    try:
        response = httpx.get(f"{QDRANT_URL.rstrip('/')}/collections", timeout=2.0)
        response.raise_for_status()
        data = response.json()
        collections = [
            item.get("name")
            for item in data.get("result", {}).get("collections", [])
            if isinstance(item, dict)
        ]
        return {
            "ok": True,
            "url": QDRANT_URL,
            "collection": QDRANT_COLLECTION,
            "collection_exists": QDRANT_COLLECTION in collections,
            "collections": collections,
        }
    except Exception as exc:
        return {"ok": False, "url": QDRANT_URL, "collection": QDRANT_COLLECTION, "error": str(exc)}


def check_neo4j() -> dict[str, Any]:
    if not NEO4J_PASSWORD:
        return {
            "ok": False,
            "uri": NEO4J_URI,
            "database": NEO4J_DATABASE,
            "error": "NEO4J_PASSWORD is not set",
        }
    if importlib.util.find_spec("neo4j") is None:
        return {
            "ok": False,
            "uri": NEO4J_URI,
            "database": NEO4J_DATABASE,
            "error": "neo4j package is not installed",
        }
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            connection_timeout=2,
        )
        try:
            with driver.session(database=NEO4J_DATABASE) as session:
                value = session.run("RETURN 1 AS ok").single()["ok"]
        finally:
            driver.close()
        return {"ok": value == 1, "uri": NEO4J_URI, "database": NEO4J_DATABASE}
    except Exception as exc:
        return {"ok": False, "uri": NEO4J_URI, "database": NEO4J_DATABASE, "error": str(exc)}


async def check_graphiti(*, deep: bool = False) -> dict[str, Any]:
    if importlib.util.find_spec("graphiti_core") is None:
        return {"ok": False, "backend": "neo4j", "error": "graphiti_core package is not installed"}
    if not deep:
        return {"ok": True, "backend": "neo4j", "mode": "import_only"}
    try:
        from orchestrator.archival import archival_memory

        result = await archival_memory.healthcheck()
        return {
            "ok": result.get("status") == "ok",
            "backend": "neo4j",
            **result,
        }
    except Exception as exc:
        return {"ok": False, "backend": "neo4j", "error": str(exc)}


def check_openai_embedding() -> dict[str, Any]:
    return {
        "ok": bool(OPENAI_API_KEY),
        "model": OPENAI_EMBEDDING_MODEL,
        "api_key_present": bool(OPENAI_API_KEY),
    }


def summarize_checks(checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ok = sorted(name for name, check in checks.items() if check.get("ok"))
    failing = {
        name: check.get("error", "not ready")
        for name, check in checks.items()
        if not check.get("ok")
    }
    return {"ok": ok, "failing": failing}


def _is_writable_dir(path: Path) -> bool:
    return path.exists() and os.access(path, os.W_OK)


def render_healthcheck_text(report: dict[str, Any]) -> str:
    lines = [
        f"Research memory healthcheck: {report['status']}",
        f"thread_id: {report['thread_id']}",
        "",
    ]
    for name, check in report["checks"].items():
        status = "ok" if check.get("ok") else "failed"
        detail = check.get("error") or check.get("path") or check.get("url") or check.get("uri") or ""
        lines.append(f"- {name}: {status} {detail}".rstrip())
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check CEML_RA research memory surfaces.")
    parser.add_argument("--thread-id", default="materials_ontology_kg")
    parser.add_argument("--artifacts-dir", type=Path, default=None)
    parser.add_argument("--deep", action="store_true", help="Initialize Graphiti and create Neo4j indices if needed.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = run_research_memory_healthcheck(
        thread_id=args.thread_id,
        artifacts_dir=args.artifacts_dir,
        deep=args.deep,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_healthcheck_text(report), end="")
    return 0 if report["status"] == "ok" else 2
