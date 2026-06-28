"""Weekly Useful Research Loop for research_thread memory.

This loop is intentionally product-facing: it reads accumulated memory, writes
weekly brief/memory-note artifacts, updates the research_thread, and attempts
live Graphiti/Qdrant memory writes when executed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Union

from orchestrator.research_thread import (
    load_research_thread,
    normalize_research_thread,
    resolve_artifacts_dir,
    utc_now,
    validate_research_thread,
)
from orchestrator.research_thread_patch import preview_or_apply_research_thread_patch


SCHEMA_VERSION = 1
BUILDER_NAME = "research_weekly_loop_v0"
DEFAULT_THREAD_ID = "materials_ontology_kg"
WEEKLY_LOOPS_DIR = "research_weekly_loops"
MEMORY_NOTES_DIR = "research_memory_notes"
DEFAULT_QUERY = "materials ontology knowledge graph provenance RAG research memory"

SourceSearch = Callable[[str, int, int], list[dict[str, Any]]]
KgSearch = Callable[[str, int], Awaitable[list[dict[str, Any]]]]
GraphitiIngest = Callable[[str, str, str, str], Awaitable[Union[bool, dict[str, Any]]]]
QdrantUpsert = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class WeeklyLoopPaths:
    run_json_path: Path
    run_markdown_path: Path
    memory_json_path: Path
    memory_markdown_path: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "run_json_path": str(self.run_json_path),
            "run_markdown_path": str(self.run_markdown_path),
            "memory_json_path": str(self.memory_json_path),
            "memory_markdown_path": str(self.memory_markdown_path),
        }


def weekly_loop_thread_dir(thread_id: str, artifacts_dir: Path | None = None) -> Path:
    return resolve_artifacts_dir(artifacts_dir) / WEEKLY_LOOPS_DIR / thread_id


def memory_note_thread_dir(thread_id: str, artifacts_dir: Path | None = None) -> Path:
    return resolve_artifacts_dir(artifacts_dir) / MEMORY_NOTES_DIR / thread_id


def weekly_loop_paths(
    *,
    thread_id: str,
    run_id: str,
    memory_note_id: str,
    artifacts_dir: Path | None = None,
) -> WeeklyLoopPaths:
    return WeeklyLoopPaths(
        run_json_path=weekly_loop_thread_dir(thread_id, artifacts_dir) / f"{run_id}.json",
        run_markdown_path=weekly_loop_thread_dir(thread_id, artifacts_dir) / f"{run_id}.md",
        memory_json_path=memory_note_thread_dir(thread_id, artifacts_dir) / f"{memory_note_id}.json",
        memory_markdown_path=memory_note_thread_dir(thread_id, artifacts_dir) / f"{memory_note_id}.md",
    )


async def preview_or_run_weekly_loop(
    *,
    thread_id: str = DEFAULT_THREAD_ID,
    query: str | None = None,
    days: int = 7,
    artifacts_dir: Path | None = None,
    execute: bool = False,
    use_live_memory: bool = True,
    created_at: str | None = None,
    scout_limit: int = 5,
    rag_limit: int = 5,
    kg_limit: int = 5,
    scout_search: SourceSearch | None = None,
    rag_search: SourceSearch | None = None,
    kg_search: KgSearch | None = None,
    graphiti_ingest: GraphitiIngest | None = None,
    qdrant_upsert: QdrantUpsert | None = None,
) -> dict[str, Any]:
    """Run or preview the v0 weekly loop.

    v0 is intentionally constrained to materials_ontology_kg. Later phases can
    promote the same contract to multiple threads.
    """
    if thread_id != DEFAULT_THREAD_ID:
        raise ValueError(f"Weekly Useful Research Loop v0 supports only {DEFAULT_THREAD_ID}")
    if days < 1 or days > 31:
        raise ValueError("days must be between 1 and 31")
    if scout_limit < 0 or rag_limit < 0 or kg_limit < 0:
        raise ValueError("source limits must be non-negative")

    created_at = created_at or utc_now()
    query = (query or DEFAULT_QUERY).strip()
    if not query:
        raise ValueError("query must be a non-empty string")

    thread = normalize_research_thread(load_research_thread(thread_id, artifacts_dir=artifacts_dir))
    validate_research_thread(thread)
    preflight_report = await run_memory_preflight(thread_id=thread_id, artifacts_dir=artifacts_dir)

    run_id = build_run_id(thread_id=thread_id, query=query, created_at=created_at)
    memory_note_id = build_memory_note_id(thread_id=thread_id, run_id=run_id)
    paths = weekly_loop_paths(
        thread_id=thread_id,
        run_id=run_id,
        memory_note_id=memory_note_id,
        artifacts_dir=artifacts_dir,
    )

    prior_notes = load_previous_memory_notes(thread_id=thread_id, artifacts_dir=artifacts_dir, limit=5)
    thread_memory = collect_thread_memory(thread, limit=8)
    source_bundle = await collect_weekly_sources(
        query=query,
        days=days,
        scout_limit=scout_limit,
        rag_limit=rag_limit,
        kg_limit=kg_limit,
        scout_search=scout_search,
        rag_search=rag_search,
        kg_search=kg_search,
    )
    memory_note = build_memory_note(
        thread=thread,
        run_id=run_id,
        memory_note_id=memory_note_id,
        query=query,
        created_at=created_at,
        days=days,
        prior_notes=prior_notes,
        thread_memory=thread_memory,
        source_bundle=source_bundle,
        artifact_ref=str(paths.memory_markdown_path),
    )
    memory_markdown = render_memory_note_markdown(memory_note)

    live_write_results = build_skipped_live_write_results(use_live_memory=use_live_memory, execute=execute)
    if execute and use_live_memory:
        live_write_results = await write_live_memory(
            thread_id=thread_id,
            memory_note=memory_note,
            memory_markdown=memory_markdown,
            memory_artifact_ref=str(paths.memory_markdown_path),
            graphiti_ingest=graphiti_ingest,
            qdrant_upsert=qdrant_upsert,
        )

    brief = build_weekly_brief(
        thread=thread,
        run_id=run_id,
        query=query,
        created_at=created_at,
        days=days,
        prior_notes=prior_notes,
        thread_memory=thread_memory,
        source_bundle=source_bundle,
        memory_note=memory_note,
        live_write_results=live_write_results,
        preflight_report=preflight_report,
    )
    source_availability = build_source_availability(
        source_bundle=source_bundle,
        live_write_results=live_write_results,
        preflight_report=preflight_report,
    )
    brief_markdown = render_weekly_brief_markdown(brief)
    patch = build_thread_patch(
        thread_id=thread_id,
        run_id=run_id,
        memory_note=memory_note,
        brief=brief,
        paths=paths,
        live_write_results=live_write_results,
    )

    thread_patch_result = preview_or_apply_research_thread_patch(
        thread_id=thread_id,
        patch=patch,
        artifacts_dir=artifacts_dir,
        execute=execute,
        created_at=created_at,
    )

    status = status_from_live_writes(live_write_results) if execute else "would_run"
    artifact_mutations: list[dict[str, str]] = []
    if execute:
        paths.run_json_path.parent.mkdir(parents=True, exist_ok=True)
        paths.memory_json_path.parent.mkdir(parents=True, exist_ok=True)
        paths.memory_json_path.write_text(
            json.dumps(memory_note, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths.memory_markdown_path.write_text(memory_markdown, encoding="utf-8")
        paths.run_json_path.write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "builder": BUILDER_NAME,
                    "status": status,
                    "brief": brief,
                    "memory_note": memory_note,
                    "thread_patch": patch,
                    "thread_patch_result": thread_patch_result,
                    "source_availability": source_availability,
                    "preflight_summary": preflight_report["summary"],
                    "preflight_report": preflight_report,
                    "live_write_results": live_write_results,
                    "live_store_mutations": collect_live_store_mutations(live_write_results),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        paths.run_markdown_path.write_text(brief_markdown, encoding="utf-8")
        artifact_mutations.extend([
            {"type": "weekly_loop_json", "path": str(paths.run_json_path)},
            {"type": "weekly_loop_markdown", "path": str(paths.run_markdown_path)},
            {"type": "weekly_memory_note_json", "path": str(paths.memory_json_path)},
            {"type": "weekly_memory_note_markdown", "path": str(paths.memory_markdown_path)},
        ])

    return {
        "schema_version": SCHEMA_VERSION,
        "builder": BUILDER_NAME,
        "status": status,
        "dry_run": not execute,
        "thread_id": thread_id,
        "run_id": run_id,
        "memory_note_id": memory_note_id,
        "query": query,
        "days": days,
        **paths.as_dict(),
        "brief": brief,
        "preview_markdown": brief_markdown,
        "memory_note": memory_note,
        "memory_note_markdown": memory_markdown,
        "thread_patch": patch,
        "thread_patch_result": thread_patch_result,
        "source_availability": source_availability,
        "preflight_summary": preflight_report["summary"],
        "preflight_report": preflight_report,
        "source_errors": source_bundle["errors"],
        "live_write_results": live_write_results,
        "artifact_mutations": artifact_mutations,
        "live_store_mutations": collect_live_store_mutations(live_write_results),
    }


async def collect_weekly_sources(
    *,
    query: str,
    days: int,
    scout_limit: int,
    rag_limit: int,
    kg_limit: int,
    scout_search: SourceSearch | None = None,
    rag_search: SourceSearch | None = None,
    kg_search: KgSearch | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    scout = normalize_source_items("scout", _safe_collect_sync(
        "scout",
        scout_search or default_scout_search,
        query,
        scout_limit,
        days,
        errors,
    ))
    rag = normalize_source_items("rag", _safe_collect_sync(
        "rag",
        rag_search or default_rag_search,
        query,
        rag_limit,
        days,
        errors,
    ))
    kg = normalize_source_items("kg", await _safe_collect_kg(
        kg_search or default_kg_search,
        query,
        kg_limit,
        errors,
    ))
    return {
        "scout": scout,
        "rag": rag,
        "kg": kg,
        "errors": errors,
    }


def default_scout_search(query: str, limit: int, days: int) -> list[dict[str, Any]]:
    if limit == 0:
        return []
    from integrations.scout_reader import ScoutReader

    reader = ScoutReader()
    try:
        papers = reader.search_papers(query, limit=limit)
    finally:
        reader.close()
    return [source_from_scout_paper(paper, idx) for idx, paper in enumerate(papers, start=1)]


def default_rag_search(query: str, limit: int, days: int) -> list[dict[str, Any]]:
    if limit == 0:
        return []
    from integrations.hybrid_retriever import hybrid_search

    results = hybrid_search(query=query, limit=limit)
    return [source_from_rag_result(result, idx) for idx, result in enumerate(results, start=1)]


async def default_kg_search(query: str, limit: int) -> list[dict[str, Any]]:
    if limit == 0:
        return []
    from orchestrator.archival import archival_memory

    results = await archival_memory.search(query, limit=limit)
    return [source_from_kg_result(result, idx) for idx, result in enumerate(results, start=1)]


def normalize_source_items(label: str, items: list[Any]) -> list[dict[str, Any]]:
    normalized = []
    for idx, item in enumerate(items, start=1):
        if isinstance(item, dict) and item.get("citation"):
            normalized.append(item)
        elif label == "scout" and isinstance(item, dict):
            normalized.append(source_from_scout_paper(item, idx))
        elif label == "rag":
            normalized.append(source_from_rag_result(item, idx))
        elif label == "kg" and isinstance(item, dict):
            normalized.append(source_from_kg_result(item, idx))
        else:
            normalized.append({
                "source": label,
                "id": str(idx),
                "title": f"{label} result {idx}",
                "text": str(item)[:500],
                "citation": f"{label}:{idx}",
            })
    return normalized


def collect_thread_memory(thread: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for section in ("decisions", "claims", "evidence", "idea_candidates", "next_actions"):
        for item in thread.get(section, []):
            if len(selected) >= limit:
                return selected
            if item.get("status") in {"accepted", "completed", "reviewed_signal", "selected_for_review", "open"}:
                selected.append({
                    "source": "research_thread",
                    "section": section,
                    "id": item["id"],
                    "title": f"{section}:{item['id']}",
                    "text": item["text"],
                    "citation": f"research_thread:{thread['thread_id']}:{section}:{item['id']}",
                    "artifact_refs": list(item.get("artifact_refs", []) or []),
                    "source_refs": list(item.get("source_refs", []) or []),
                })
    return selected


def load_previous_memory_notes(
    *,
    thread_id: str,
    artifacts_dir: Path | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    base = memory_note_thread_dir(thread_id, artifacts_dir)
    if not base.exists():
        return []
    notes: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json"), reverse=True):
        try:
            note = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        note["artifact_ref"] = str(path)
        notes.append(note)
        if len(notes) >= limit:
            break
    return notes


def build_memory_note(
    *,
    thread: dict[str, Any],
    run_id: str,
    memory_note_id: str,
    query: str,
    created_at: str,
    days: int,
    prior_notes: list[dict[str, Any]],
    thread_memory: list[dict[str, Any]],
    source_bundle: dict[str, Any],
    artifact_ref: str,
) -> dict[str, Any]:
    evidence_sources = source_bundle["scout"] + source_bundle["rag"] + source_bundle["kg"]
    citations = build_citations(prior_notes, thread_memory, evidence_sources)
    top_evidence = evidence_sources[0]["title"] if evidence_sources else "새 외부 근거 없음"
    next_questions = build_next_questions(thread, evidence_sources, prior_notes)
    claim_id = f"{memory_note_id}.claim.1"
    claim_text = (
        f"`{thread['thread_id']}`의 이번 주 루프는 이전 기억 {len(prior_notes)}개와 "
        f"새 근거 {len(evidence_sources)}개를 연결했다. 다음 검토 초점은 `{next_questions[0]}`이며, "
        f"가장 앞선 새 근거 신호는 `{top_evidence}`이다."
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "builder": BUILDER_NAME,
        "memory_note_id": memory_note_id,
        "run_id": run_id,
        "thread_id": thread["thread_id"],
        "topic": thread["topic"],
        "created_at": created_at,
        "period_days": days,
        "query": query,
        "artifact_ref": artifact_ref,
        "summary": claim_text,
        "claims": [
            {
                "id": claim_id,
                "text": claim_text,
                "source_refs": [citation["id"] for citation in citations[:8]],
            }
        ],
        "next_questions": next_questions,
        "citations": citations,
        "reused_memory_count": len(prior_notes) + len(thread_memory),
        "new_evidence_count": len(evidence_sources),
        "live_store_mutations": [],
    }


def build_weekly_brief(
    *,
    thread: dict[str, Any],
    run_id: str,
    query: str,
    created_at: str,
    days: int,
    prior_notes: list[dict[str, Any]],
    thread_memory: list[dict[str, Any]],
    source_bundle: dict[str, Any],
    memory_note: dict[str, Any],
    live_write_results: dict[str, Any],
    preflight_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "builder": BUILDER_NAME,
        "run_id": run_id,
        "thread_id": thread["thread_id"],
        "topic": thread["topic"],
        "created_at": created_at,
        "period_days": days,
        "query": query,
        "reused_memory": {
            "previous_memory_notes": compact_previous_notes(prior_notes),
            "thread_memory": thread_memory,
        },
        "new_evidence": {
            "scout": source_bundle["scout"],
            "rag": source_bundle["rag"],
            "kg": source_bundle["kg"],
            "errors": source_bundle["errors"],
        },
        "new_memory": memory_note,
        "next_week_questions": memory_note["next_questions"],
        "live_write_results": live_write_results,
        "preflight_summary": preflight_report["summary"],
    }


def build_thread_patch(
    *,
    thread_id: str,
    run_id: str,
    memory_note: dict[str, Any],
    brief: dict[str, Any],
    paths: WeeklyLoopPaths,
    live_write_results: dict[str, Any],
) -> dict[str, Any]:
    artifact_refs = [str(paths.run_markdown_path), str(paths.memory_markdown_path)]
    claim = memory_note["claims"][0]
    source_refs = claim["source_refs"]
    live_summary = json.dumps(
        {
            "graphiti": live_write_results["graphiti"]["status"],
            "qdrant": live_write_results["qdrant"]["status"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return {
        "schema_version": 2,
        "thread_id": thread_id,
        "research_state": "weekly_useful_loop_updated",
        "append": {
            "claims": [
                {
                    "id": f"weekly_loop.{run_id}.claim",
                    "text": claim["text"],
                    "status": "accepted",
                    "authority_state": "reviewed_artifact",
                    "review_state": "reviewed",
                    "support_state": "artifact_synthesis",
                    "source_refs": source_refs,
                    "artifact_refs": artifact_refs,
                    "metadata": {"weekly_loop_run_id": run_id},
                }
            ],
            "evidence": [
                {
                    "id": f"weekly_loop.{run_id}.evidence",
                    "text": (
                        f"Weekly loop `{run_id}` reused "
                        f"{len(brief['reused_memory']['previous_memory_notes']) + len(brief['reused_memory']['thread_memory'])} "
                        f"memory item(s) and collected "
                        f"{len(brief['new_evidence']['scout']) + len(brief['new_evidence']['rag']) + len(brief['new_evidence']['kg'])} "
                        "new evidence signal(s)."
                    ),
                    "status": "reviewed_signal",
                    "authority_state": "reviewed_artifact",
                    "review_state": "reviewed",
                    "support_state": "artifact_synthesis",
                    "source_refs": source_refs,
                    "artifact_refs": artifact_refs,
                    "metadata": {"weekly_loop_run_id": run_id},
                }
            ],
            "decisions": [
                {
                    "id": f"weekly_loop.{run_id}.decision.stored",
                    "text": f"Weekly Useful Research Loop `{run_id}`를 실행하고 reusable memory note를 저장했다. Live memory write 결과: {live_summary}",
                    "status": "accepted",
                    "authority_state": "reviewed_artifact",
                    "review_state": "reviewed",
                    "support_state": "artifact_synthesis",
                    "artifact_refs": artifact_refs,
                    "metadata": {"weekly_loop_run_id": run_id, "live_write_results": live_write_results},
                }
            ],
            "next_actions": [
                {
                    "id": f"weekly_loop.{run_id}.next_question",
                    "text": memory_note["next_questions"][0],
                    "status": "open",
                    "authority_state": "thread_local",
                    "review_state": "reviewed",
                    "support_state": "artifact_synthesis",
                    "artifact_refs": artifact_refs,
                    "metadata": {"weekly_loop_run_id": run_id},
                }
            ],
        },
        "metadata": {
            "last_weekly_useful_loop": {
                "run_id": run_id,
                "memory_note_id": memory_note["memory_note_id"],
                "run_markdown_path": str(paths.run_markdown_path),
                "memory_markdown_path": str(paths.memory_markdown_path),
                "live_write_results": live_write_results,
            }
        },
        "live_store_mutations": [],
    }


async def run_memory_preflight(*, thread_id: str, artifacts_dir: Path | None) -> dict[str, Any]:
    try:
        from orchestrator.research_memory_healthcheck import async_run_research_memory_healthcheck

        return await async_run_research_memory_healthcheck(
            thread_id=thread_id,
            artifacts_dir=artifacts_dir,
            deep=False,
        )
    except Exception as exc:
        return {
            "schema_version": 1,
            "thread_id": thread_id,
            "status": "degraded",
            "deep": False,
            "checks": {},
            "summary": {"ok": [], "failing": {"preflight": str(exc)}},
        }


def build_source_availability(
    *,
    source_bundle: dict[str, Any],
    live_write_results: dict[str, Any],
    preflight_report: dict[str, Any],
) -> dict[str, Any]:
    checks = preflight_report.get("checks", {}) or {}
    return {
        "scout": _source_status(
            count=len(source_bundle.get("scout", [])),
            check=checks.get("scout", {}),
            errors=[e for e in source_bundle.get("errors", []) if e.get("source") == "scout"],
        ),
        "rag": _source_status(
            count=len(source_bundle.get("rag", [])),
            check=checks.get("qdrant", {}),
            errors=[e for e in source_bundle.get("errors", []) if e.get("source") == "rag"],
        ),
        "kg": _source_status(
            count=len(source_bundle.get("kg", [])),
            check=checks.get("graphiti", {}),
            errors=[e for e in source_bundle.get("errors", []) if e.get("source") == "kg"],
        ),
        "qdrant_write": {
            "status": live_write_results.get("qdrant", {}).get("status"),
            "error": live_write_results.get("qdrant", {}).get("error"),
        },
        "graphiti_write": {
            "status": live_write_results.get("graphiti", {}).get("status"),
            "error": live_write_results.get("graphiti", {}).get("error"),
        },
    }


def _source_status(*, count: int, check: dict[str, Any], errors: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "available": count > 0,
        "count": count,
        "preflight_ok": bool(check.get("ok")),
        "preflight_error": check.get("error"),
        "errors": errors,
    }


async def write_live_memory(
    *,
    thread_id: str,
    memory_note: dict[str, Any],
    memory_markdown: str,
    memory_artifact_ref: str,
    graphiti_ingest: GraphitiIngest | None = None,
    qdrant_upsert: QdrantUpsert | None = None,
) -> dict[str, Any]:
    graphiti_result = await _write_graphiti_memory(
        thread_id=thread_id,
        memory_note=memory_note,
        memory_markdown=memory_markdown,
        graphiti_ingest=graphiti_ingest,
    )
    qdrant_result = _write_qdrant_memory(
        thread_id=thread_id,
        memory_note=memory_note,
        memory_markdown=memory_markdown,
        memory_artifact_ref=memory_artifact_ref,
        qdrant_upsert=qdrant_upsert,
    )
    return {"graphiti": graphiti_result, "qdrant": qdrant_result}


async def _write_graphiti_memory(
    *,
    thread_id: str,
    memory_note: dict[str, Any],
    memory_markdown: str,
    graphiti_ingest: GraphitiIngest | None = None,
) -> dict[str, Any]:
    try:
        if graphiti_ingest is None:
            from orchestrator.archival import archival_memory

            async def graphiti_ingest(conversation_id: str, user_message: str, assistant_message: str, agent_name: str):
                if hasattr(archival_memory, "ingest_turn_result"):
                    return await archival_memory.ingest_turn_result(conversation_id, user_message, assistant_message, agent_name)
                return await archival_memory.ingest_turn(conversation_id, user_message, assistant_message, agent_name)

        result = await graphiti_ingest(
            memory_note["memory_note_id"],
            f"Accumulate weekly research memory for {thread_id}.",
            memory_markdown,
            BUILDER_NAME,
        )
        if isinstance(result, dict):
            return result
        if result:
            return {
                "status": "ingested",
                "conversation_id": memory_note["memory_note_id"],
                "live_store_mutations": [{"type": "graphiti_ingest", "conversation_id": memory_note["memory_note_id"]}],
            }
        return {
            "status": "failed",
            "conversation_id": memory_note["memory_note_id"],
            "live_store_mutations": [],
            "error": "Graphiti ingest returned false",
        }
    except Exception as exc:
        return {
            "status": "failed",
            "conversation_id": memory_note["memory_note_id"],
            "live_store_mutations": [],
            "error": str(exc),
        }


def _write_qdrant_memory(
    *,
    thread_id: str,
    memory_note: dict[str, Any],
    memory_markdown: str,
    memory_artifact_ref: str,
    qdrant_upsert: QdrantUpsert | None = None,
) -> dict[str, Any]:
    try:
        if qdrant_upsert is None:
            from integrations.qdrant import upsert_memory_note

            qdrant_upsert = upsert_memory_note
        return qdrant_upsert(
            thread_id=thread_id,
            memory_note_id=memory_note["memory_note_id"],
            artifact_ref=memory_artifact_ref,
            text=memory_markdown,
            created_at=memory_note["created_at"],
            claim_refs=[claim["id"] for claim in memory_note["claims"]],
            source_refs=[citation["id"] for citation in memory_note["citations"]],
        )
    except Exception as exc:
        return {
            "status": "failed",
            "live_store_mutations": [],
            "error": str(exc),
        }


def build_skipped_live_write_results(*, use_live_memory: bool, execute: bool) -> dict[str, Any]:
    reason = "dry_run" if not execute else "disabled_by_request"
    if execute and use_live_memory:
        reason = "not_started"
    return {
        "graphiti": {"status": "skipped", "reason": reason, "live_store_mutations": []},
        "qdrant": {"status": "skipped", "reason": reason, "live_store_mutations": []},
    }


def status_from_live_writes(live_write_results: dict[str, Any]) -> str:
    failing = {"failed", "unavailable", "embedding_unavailable"}
    statuses = {
        live_write_results.get("graphiti", {}).get("status"),
        live_write_results.get("qdrant", {}).get("status"),
    }
    return "partial_failure" if statuses & failing else "completed"


def collect_live_store_mutations(live_write_results: dict[str, Any]) -> list[dict[str, Any]]:
    mutations: list[dict[str, Any]] = []
    for result in live_write_results.values():
        mutations.extend(result.get("live_store_mutations", []) or [])
    return mutations


def render_weekly_brief_markdown(brief: dict[str, Any]) -> str:
    lines = [
        f"# Weekly Useful Research Loop: {brief['thread_id']}",
        "",
        f"- Run ID: `{brief['run_id']}`",
        f"- 생성 시각: `{brief['created_at']}`",
        f"- Query: `{brief['query']}`",
        f"- 기간: 최근 `{brief['period_days']}`일 기준",
        "",
        "## 이번 주 판단",
        "",
        f"- {brief['new_memory']['summary']}",
        "",
        "## 기존 기억 재사용",
        "",
    ]
    previous = brief["reused_memory"]["previous_memory_notes"]
    if previous:
        for note in previous:
            lines.append(f"- `{note['memory_note_id']}`: {note.get('summary', '')}")
    else:
        lines.append("- 이전 weekly memory note 없음")
    thread_memory = brief["reused_memory"]["thread_memory"]
    for item in thread_memory[:5]:
        lines.append(f"- `{item['citation']}`: {item['text']}")

    lines.extend(["", "## 새 근거", ""])
    for label in ("scout", "rag", "kg"):
        items = brief["new_evidence"][label]
        lines.append(f"### {label.upper()}")
        if not items:
            lines.append("- 새 근거 없음")
        for item in items:
            lines.append(f"- `{item['citation']}` **{item['title']}**: {item['text']}")
        lines.append("")

    lines.extend(["## 새로 기억한 내용", ""])
    for claim in brief["new_memory"]["claims"]:
        lines.append(f"- `{claim['id']}`: {claim['text']}")

    lines.extend(["", "## 다음 주 질문", ""])
    lines.extend(f"- {question}" for question in brief["next_week_questions"])

    lines.extend(["", "## Live Memory Write", ""])
    for store, result in brief["live_write_results"].items():
        text = result.get("error") or result.get("reason") or ""
        suffix = f" — {text}" if text else ""
        lines.append(f"- {store}: `{result.get('status')}`{suffix}")

    failing = brief.get("preflight_summary", {}).get("failing", {})
    if failing:
        lines.extend(["", "## Preflight", ""])
        for name, error in failing.items():
            lines.append(f"- {name}: {error}")
    return "\n".join(lines) + "\n"


def render_memory_note_markdown(memory_note: dict[str, Any]) -> str:
    lines = [
        f"# Research Memory Note: {memory_note['thread_id']}",
        "",
        f"- Memory note ID: `{memory_note['memory_note_id']}`",
        f"- Run ID: `{memory_note['run_id']}`",
        f"- 생성 시각: `{memory_note['created_at']}`",
        f"- Query: `{memory_note['query']}`",
        "",
        "## Summary",
        "",
        memory_note["summary"],
        "",
        "## Claims",
        "",
    ]
    for claim in memory_note["claims"]:
        lines.append(f"- `{claim['id']}`: {claim['text']}")
    lines.extend(["", "## Next Questions", ""])
    lines.extend(f"- {question}" for question in memory_note["next_questions"])
    lines.extend(["", "## Citations", ""])
    if not memory_note["citations"]:
        lines.append("- 없음")
    for citation in memory_note["citations"]:
        lines.append(f"- `{citation['id']}` {citation['title']} — {citation['ref']}")
    return "\n".join(lines) + "\n"


def source_from_scout_paper(paper: dict[str, Any], idx: int) -> dict[str, Any]:
    paper_id = str(paper.get("id") or paper.get("paper_id") or idx)
    title = str(paper.get("title") or "Untitled Scout paper")
    text = str(paper.get("summary") or paper.get("abstract") or "")[:500]
    return {
        "source": "scout",
        "id": paper_id,
        "title": title,
        "text": text or "요약 없음",
        "citation": f"scout:{paper_id}",
        "url": str(paper.get("url") or ""),
        "score": paper.get("relevance_score"),
    }


def source_from_rag_result(result: Any, idx: int) -> dict[str, Any]:
    payload = getattr(result, "payload", {}) or {}
    chunk_id = str(payload.get("chunk_id") or payload.get("memory_note_id") or f"rag_{idx}")
    title = str(payload.get("title") or "RAG result")
    text = str(payload.get("text") or "")[:500]
    return {
        "source": "rag",
        "id": chunk_id,
        "title": title,
        "text": text or "검색 payload에 text 없음",
        "citation": f"rag:{chunk_id}",
        "score": getattr(result, "score", None),
        "artifact_ref": str(payload.get("artifact_ref") or ""),
    }


def source_from_kg_result(result: dict[str, Any], idx: int) -> dict[str, Any]:
    uuid = str(result.get("uuid") or f"kg_{idx}")
    fact = str(result.get("fact") or "")
    return {
        "source": "kg",
        "id": uuid,
        "title": f"Graphiti fact {idx}",
        "text": fact or "KG fact text 없음",
        "citation": f"kg:{uuid}",
        "score": result.get("score"),
    }


def build_citations(
    prior_notes: list[dict[str, Any]],
    thread_memory: list[dict[str, Any]],
    evidence_sources: list[dict[str, Any]],
) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    for note in prior_notes:
        citations.append({
            "id": f"memory_note:{note.get('memory_note_id', '')}",
            "title": str(note.get("memory_note_id", "previous memory note")),
            "ref": str(note.get("artifact_ref", "")),
        })
    for item in thread_memory:
        citations.append({
            "id": item["citation"],
            "title": item["title"],
            "ref": item["citation"],
        })
    for item in evidence_sources:
        citations.append({
            "id": item["citation"],
            "title": item["title"],
            "ref": item.get("url") or item.get("artifact_ref") or item["citation"],
        })
    return citations


def build_next_questions(
    thread: dict[str, Any],
    evidence_sources: list[dict[str, Any]],
    prior_notes: list[dict[str, Any]],
) -> list[str]:
    open_actions = [
        item["text"]
        for item in thread.get("next_actions", [])
        if item.get("status") == "open"
    ]
    questions = open_actions[:2]
    if evidence_sources:
        questions.append(f"이번 주 새 근거 `{evidence_sources[0]['title']}`가 materials KG/RAG benchmark 설계를 어떻게 바꾸는가?")
    if prior_notes:
        questions.append("지난 weekly memory note의 결론 중 이번 근거로 수정하거나 폐기해야 할 것은 무엇인가?")
    if not questions:
        questions.append("materials ontology KG가 plain RAG보다 실제 연구 판단을 더 좋게 만드는 최소 benchmark는 무엇인가?")
    return questions[:4]


def compact_previous_notes(notes: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "memory_note_id": str(note.get("memory_note_id", "")),
            "summary": str(note.get("summary", "")),
            "artifact_ref": str(note.get("artifact_ref", "")),
        }
        for note in notes
    ]


def _safe_collect_sync(
    label: str,
    fn: SourceSearch,
    query: str,
    limit: int,
    days: int,
    errors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    try:
        return fn(query, limit, days)
    except Exception as exc:
        errors.append({"source": label, "error": str(exc)})
        return []


async def _safe_collect_kg(
    fn: KgSearch,
    query: str,
    limit: int,
    errors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    try:
        return await fn(query, limit)
    except Exception as exc:
        errors.append({"source": "kg", "error": str(exc)})
        return []


def build_run_id(*, thread_id: str, query: str, created_at: str) -> str:
    return _safe_id(f"weekly_{thread_id}_{created_at}_{query}")[:96]


def build_memory_note_id(*, thread_id: str, run_id: str) -> str:
    return _safe_id(f"memory_note_{thread_id}_{run_id}")[:120]


def _safe_id(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("._") or "weekly_loop"
