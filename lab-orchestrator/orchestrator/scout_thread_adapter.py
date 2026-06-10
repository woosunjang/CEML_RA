"""Read-only Scout evidence adapter for research_thread artifacts.

The adapter converts Scout paper metadata into research_thread source signals
and evidence previews. It never writes to Scout DB, Qdrant, Neo4j, Graphiti,
Slack, or runtime services.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from integrations.scout_reader import ScoutReader
from orchestrator.research_thread import (
    DEFAULT_SEED_TOPICS,
    GROUND_CONTRACT_REF,
    load_research_thread,
    make_section_item,
    render_research_thread_markdown,
    research_thread_paths,
    utc_now,
    validate_research_thread,
    write_research_thread,
)


DEFAULT_SCOUT_QUERIES = {
    "materials_ontology_kg": "materials ontology knowledge graph",
    "rare_earth_magnets": "rare earth magnets",
}

ADAPTER_NAME = "scout_thread_adapter"


def _safe_item_id(prefix: str, raw: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", raw).strip("._-").lower()
    if slug:
        return f"{prefix}.{slug[:64]}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}.{digest}"


def _parse_json(raw: Any, fallback: Any) -> Any:
    if raw is None:
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _paper_source_ref(paper: dict[str, Any]) -> str:
    if paper.get("url"):
        return str(paper["url"])
    if paper.get("id"):
        return f"scout:{paper['id']}"
    return "scout:unknown"


def _paper_summary(paper: dict[str, Any]) -> str:
    analysis = _parse_json(paper.get("analysis_json"), {})
    for key in ("summary", "one_line_summary", "summary_kr", "key_contribution"):
        value = paper.get(key) or analysis.get(key)
        if value:
            return str(value)
    return ""


def _paper_tags(paper: dict[str, Any]) -> list[str]:
    analysis = _parse_json(paper.get("analysis_json"), {})
    tags = paper.get("tags") or analysis.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list):
        return []
    return [str(tag) for tag in tags if str(tag).strip()]


def _paper_score(paper: dict[str, Any]) -> float:
    try:
        return float(paper.get("relevance_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _paper_metadata(paper: dict[str, Any], *, query: str) -> dict[str, Any]:
    return {
        "adapter": ADAPTER_NAME,
        "query": query,
        "paper_id": paper.get("id", ""),
        "title": paper.get("title", ""),
        "authors": paper.get("authors", ""),
        "source": paper.get("source", ""),
        "url": paper.get("url", ""),
        "year": paper.get("year", ""),
        "relevance_score": _paper_score(paper),
        "status": paper.get("status", ""),
    }


def scout_paper_to_thread_items(
    paper: dict[str, Any],
    *,
    thread_id: str,
    query: str,
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    paper_key = str(paper.get("id") or paper.get("url") or paper.get("title") or "unknown")
    source_ref = _paper_source_ref(paper)
    title = str(paper.get("title") or "Untitled")
    year = paper.get("year") or "unknown year"
    score = _paper_score(paper)
    summary = _paper_summary(paper)
    metadata = _paper_metadata(paper, query=query)
    tags = ["scout", thread_id] + _paper_tags(paper)

    source_signal = make_section_item(
        _safe_item_id("scout_signal", paper_key),
        f"Scout returned `{title}` ({year}) for query `{query}` with relevance score {score:.1f}.",
        status="needs_review",
        created_at=created_at,
        source_refs=[source_ref],
        confidence="scout_metadata",
        tags=tags,
        metadata=metadata,
    )
    evidence_text = f"Review Scout paper `{title}` as possible evidence for `{thread_id}`."
    if summary:
        evidence_text += f" Scout summary: {summary}"
    evidence = make_section_item(
        _safe_item_id("scout_evidence", paper_key),
        evidence_text,
        status="needs_review",
        created_at=created_at,
        source_refs=[source_ref],
        confidence="candidate_evidence",
        tags=tags,
        metadata=metadata,
    )
    return source_signal, evidence


def _existing_ids(thread: dict[str, Any], section: str) -> set[str]:
    return {str(item.get("id")) for item in thread.get(section, [])}


def _filter_new_items(thread: dict[str, Any], section: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = _existing_ids(thread, section)
    return [item for item in items if item["id"] not in existing]


def build_scout_thread_patch(
    thread: dict[str, Any],
    papers: list[dict[str, Any]],
    *,
    query: str,
    min_score: float,
    created_at: str | None = None,
) -> dict[str, Any]:
    validate_research_thread(thread)
    now = created_at or utc_now()
    source_signals = []
    evidence = []
    skipped_low_score = 0

    for paper in papers:
        if _paper_score(paper) < min_score:
            skipped_low_score += 1
            continue
        source_signal, evidence_item = scout_paper_to_thread_items(
            paper,
            thread_id=thread["thread_id"],
            query=query,
            created_at=now,
        )
        source_signals.append(source_signal)
        evidence.append(evidence_item)

    new_source_signals = _filter_new_items(thread, "source_signals", source_signals)
    new_evidence = _filter_new_items(thread, "evidence", evidence)
    return {
        "created_at": now,
        "query": query,
        "min_score": min_score,
        "papers_seen": len(papers),
        "skipped_low_score": skipped_low_score,
        "source_signals": new_source_signals,
        "evidence": new_evidence,
        "duplicates": {
            "source_signals": len(source_signals) - len(new_source_signals),
            "evidence": len(evidence) - len(new_evidence),
        },
    }


def apply_scout_thread_patch(thread: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    validate_research_thread(thread)
    updated = copy.deepcopy(thread)
    updated["source_signals"].extend(patch["source_signals"])
    updated["evidence"].extend(patch["evidence"])
    if patch["source_signals"] or patch["evidence"]:
        updated["research_state"] = "scout_evidence_previewed"
        updated["updated_at"] = patch["created_at"]
        metadata = dict(updated.get("metadata", {}))
        metadata["last_scout_adapter_run"] = {
            "adapter": ADAPTER_NAME,
            "query": patch["query"],
            "min_score": patch["min_score"],
            "papers_seen": patch["papers_seen"],
            "source_signals_added": len(patch["source_signals"]),
            "evidence_added": len(patch["evidence"]),
            "created_at": patch["created_at"],
            "live_store_mutations": [],
        }
        updated["metadata"] = metadata
    validate_research_thread(updated)
    return updated


def preview_or_apply_scout_evidence(
    *,
    thread_id: str,
    artifacts_dir: Path | None = None,
    db_path: Path | None = None,
    query: str | None = None,
    limit: int = 10,
    min_score: float = 70.0,
    execute: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    query = query or DEFAULT_SCOUT_QUERIES.get(thread_id, thread_id.replace("_", " "))
    paths = research_thread_paths(thread_id, artifacts_dir)
    if not paths.json_path.exists():
        return {
            "status": "missing_thread",
            "dry_run": not execute,
            "thread_id": thread_id,
            "query": query,
            **paths.as_dict(),
            "error": "research_thread JSON does not exist; seed the thread before adapting Scout evidence",
        }

    thread = load_research_thread(thread_id, artifacts_dir=artifacts_dir)
    reader = ScoutReader(db_path=db_path)
    try:
        papers = reader.search_papers(query, limit=limit)
    except FileNotFoundError as exc:
        return {
            "status": "scout_unavailable",
            "dry_run": not execute,
            "thread_id": thread_id,
            "query": query,
            **paths.as_dict(),
            "error": str(exc),
        }
    finally:
        reader.close()

    patch = build_scout_thread_patch(
        thread,
        papers,
        query=query,
        min_score=min_score,
        created_at=created_at,
    )
    updated = apply_scout_thread_patch(thread, patch)
    status = "no_changes"
    if patch["source_signals"] or patch["evidence"]:
        status = "updated" if execute else "would_update"

    result = {
        "status": status,
        "dry_run": not execute,
        "thread_id": thread_id,
        "query": query,
        "limit": limit,
        "min_score": min_score,
        **paths.as_dict(),
        "patch": patch,
        "preview_markdown": render_research_thread_markdown(updated),
        "live_store_mutations": [],
    }
    if execute and status == "updated":
        write_result = write_research_thread(updated, artifacts_dir=artifacts_dir, overwrite=True)
        result["write"] = write_result
    return result


def adapt_default_threads_from_scout(
    *,
    artifacts_dir: Path | None = None,
    db_path: Path | None = None,
    limit: int = 10,
    min_score: float = 70.0,
    execute: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    results = [
        preview_or_apply_scout_evidence(
            thread_id=thread_id,
            artifacts_dir=artifacts_dir,
            db_path=db_path,
            limit=limit,
            min_score=min_score,
            execute=execute,
            created_at=created_at,
        )
        for thread_id in DEFAULT_SEED_TOPICS
    ]
    return {
        "dry_run": not execute,
        "adapter": ADAPTER_NAME,
        "threads": results,
        "live_store_mutations": [],
    }
