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
THREAD_DEFAULT_QUERIES = {
    "materials_ontology_kg": DEFAULT_QUERY,
    "rare_earth_magnets": "rare earth magnets heavy rare earth reduction coercivity grain boundary diffusion recycling digital twin",
}

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

    v0 began with materials_ontology_kg and now supports the first two seeded
    research threads through thread-specific default queries.
    """
    if thread_id not in THREAD_DEFAULT_QUERIES:
        supported = ", ".join(sorted(THREAD_DEFAULT_QUERIES))
        raise ValueError(f"Weekly Useful Research Loop v0 supports only: {supported}")
    if days < 1 or days > 31:
        raise ValueError("days must be between 1 and 31")
    if scout_limit < 0 or rag_limit < 0 or kg_limit < 0:
        raise ValueError("source limits must be non-negative")

    created_at = created_at or utc_now()
    query = (query or default_query_for_thread(thread_id)).strip()
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
    raw_scout = normalize_source_items("scout", _safe_collect_sync(
        "scout",
        scout_search or default_scout_search,
        query,
        scout_limit,
        days,
        errors,
    ))
    raw_rag = normalize_source_items("rag", _safe_collect_sync(
        "rag",
        rag_search or default_rag_search,
        query,
        rag_limit,
        days,
        errors,
    ))
    raw_kg = normalize_source_items("kg", await _safe_collect_kg(
        kg_search or default_kg_search,
        query,
        kg_limit,
        errors,
    ))
    split_sources = split_fresh_evidence_and_memory_sources(
        scout=raw_scout,
        rag=raw_rag,
        kg=raw_kg,
    )
    return {
        "scout": split_sources["fresh_evidence"]["scout"],
        "rag": split_sources["fresh_evidence"]["rag"],
        "kg": split_sources["fresh_evidence"]["kg"],
        "memory_reuse_sources": split_sources["memory_reuse_sources"],
        "raw_sources": {
            "scout": raw_scout,
            "rag": raw_rag,
            "kg": raw_kg,
        },
        "scout_retrieval_mode": summarize_scout_retrieval_mode(raw_scout),
        "errors": errors,
    }


def default_scout_search(query: str, limit: int, days: int) -> list[dict[str, Any]]:
    if limit == 0:
        return []
    from integrations.scout_reader import ScoutReader

    reader = ScoutReader()
    try:
        papers = select_scout_papers_with_fallback(reader, query=query, limit=limit)
    finally:
        reader.close()
    return [source_from_scout_paper(paper, idx) for idx, paper in enumerate(papers, start=1)]


def select_scout_papers_with_fallback(reader: Any, *, query: str, limit: int) -> list[dict[str, Any]]:
    papers = reader.search_papers(query, limit=limit)
    if papers:
        for paper in papers:
            paper.setdefault("retrieval_mode", "exact_phrase")
            paper.setdefault("retrieval_reason", "Scout title/abstract matched the full weekly query.")
        return papers[:limit]

    fallback_limit = max(limit * 5, 20)
    candidates = reader.get_top_papers(min_score=0, limit=fallback_limit)
    return rank_scout_token_fallback_papers(query=query, papers=candidates, limit=limit)


def rank_scout_token_fallback_papers(*, query: str, papers: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    query_tokens = meaningful_query_tokens(query)
    ranked: list[tuple[int, float, dict[str, Any]]] = []
    for paper in papers:
        haystack = " ".join([
            str(paper.get("title", "")),
            str(paper.get("summary", "")),
            str(paper.get("abstract", "")),
            " ".join(str(tag) for tag in paper.get("tags", []) or []),
        ])
        overlap = sorted(query_tokens & meaningful_query_tokens(haystack))
        if not overlap:
            continue
        enriched = dict(paper)
        enriched["retrieval_mode"] = "token_fallback"
        enriched["retrieval_reason"] = "Full-query Scout search missed; matched topic token(s): " + ", ".join(overlap)
        enriched["token_overlap"] = overlap
        ranked.append((len(overlap), float(enriched.get("relevance_score") or 0), enriched))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [paper for _, _, paper in ranked[:limit]]


def meaningful_query_tokens(text: str) -> set[str]:
    stopwords = {"and", "or", "the", "for", "with", "this", "that", "research", "memory"}
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())
        if token not in stopwords
    }


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


def split_fresh_evidence_and_memory_sources(
    *,
    scout: list[dict[str, Any]],
    rag: list[dict[str, Any]],
    kg: list[dict[str, Any]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    memory_rag = [item for item in rag if is_memory_reuse_source(item)]
    fresh_rag = [item for item in rag if not is_memory_reuse_source(item)]
    memory_kg = [item for item in kg if is_memory_reuse_source(item)]
    fresh_kg = [item for item in kg if not is_memory_reuse_source(item)]
    return {
        "fresh_evidence": {
            "scout": scout,
            "rag": fresh_rag,
            "kg": fresh_kg,
        },
        "memory_reuse_sources": {
            "rag": memory_rag,
            "kg": memory_kg,
        },
    }


def summarize_scout_retrieval_mode(scout: list[dict[str, Any]]) -> str:
    modes = {str(item.get("retrieval_mode", "")) for item in scout}
    if "token_fallback" in modes:
        return "token_fallback"
    if "exact_phrase" in modes:
        return "exact_phrase"
    return "empty" if not scout else "custom"


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
    next_questions = build_next_questions(thread, evidence_sources, prior_notes)
    reuse_provenance = build_reuse_provenance(prior_notes, source_bundle)
    judgment_change = build_judgment_change(
        thread=thread,
        evidence_sources=evidence_sources,
        prior_notes=prior_notes,
        reuse_provenance=reuse_provenance,
    )
    weak_or_deferred_claims = build_weak_or_deferred_claims(source_bundle)
    recommended_checks = build_recommended_checks(thread, source_bundle)
    claim_id = f"{memory_note_id}.claim.1"
    claim_text = judgment_change["summary"]
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
        "judgment_change": judgment_change,
        "reuse_provenance": reuse_provenance,
        "memory_reuse_sources": source_bundle.get("memory_reuse_sources", {"rag": [], "kg": []}),
        "weak_or_deferred_claims": weak_or_deferred_claims,
        "recommended_checks": recommended_checks,
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
        "quality_version": "weekly_brief_quality_v1",
        "evidence_separation_version": "weekly_loop_evidence_separation_v1",
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
        "quality_version": "weekly_brief_quality_v1",
        "evidence_separation_version": "weekly_loop_evidence_separation_v1",
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
        "memory_reuse_sources": memory_note["memory_reuse_sources"],
        "new_evidence": {
            "scout": source_bundle["scout"],
            "rag": source_bundle["rag"],
            "kg": source_bundle["kg"],
            "errors": source_bundle["errors"],
        },
        "reuse_provenance": memory_note["reuse_provenance"],
        "judgment_change": memory_note["judgment_change"],
        "weak_or_deferred_claims": memory_note["weak_or_deferred_claims"],
        "recommended_checks": memory_note["recommended_checks"],
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
                        f"Weekly loop `{run_id}`는 "
                        f"{len(brief['reused_memory']['previous_memory_notes']) + len(brief['reused_memory']['thread_memory'])} "
                        f"개의 기존 기억과 "
                        f"{len(brief['new_evidence']['scout']) + len(brief['new_evidence']['rag']) + len(brief['new_evidence']['kg'])} "
                        f"개의 새 근거 신호를 연결했다. 판단 변화: {brief['judgment_change']['summary']}"
                    ),
                    "status": "reviewed_signal",
                    "authority_state": "reviewed_artifact",
                    "review_state": "reviewed",
                    "support_state": "artifact_synthesis",
                    "source_refs": source_refs,
                    "artifact_refs": artifact_refs,
                    "metadata": {
                        "weekly_loop_run_id": run_id,
                        "reuse_provenance": brief["reuse_provenance"],
                        "weak_or_deferred_claims": brief["weak_or_deferred_claims"],
                    },
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
    raw_sources = source_bundle.get("raw_sources", {}) or {}
    memory_sources = source_bundle.get("memory_reuse_sources", {}) or {}
    fresh_evidence_count = (
        len(source_bundle.get("scout", []))
        + len(source_bundle.get("rag", []))
        + len(source_bundle.get("kg", []))
    )
    memory_reuse_count = len(memory_sources.get("rag", [])) + len(memory_sources.get("kg", []))
    return {
        "scout": _source_status(
            count=len(raw_sources.get("scout", source_bundle.get("scout", []))),
            fresh_count=len(source_bundle.get("scout", [])),
            memory_reuse_count=0,
            check=checks.get("scout", {}),
            errors=[e for e in source_bundle.get("errors", []) if e.get("source") == "scout"],
        ),
        "rag": _source_status(
            count=len(raw_sources.get("rag", source_bundle.get("rag", []))),
            fresh_count=len(source_bundle.get("rag", [])),
            memory_reuse_count=len(memory_sources.get("rag", [])),
            check=checks.get("qdrant", {}),
            errors=[e for e in source_bundle.get("errors", []) if e.get("source") == "rag"],
        ),
        "kg": _source_status(
            count=len(raw_sources.get("kg", source_bundle.get("kg", []))),
            fresh_count=len(source_bundle.get("kg", [])),
            memory_reuse_count=len(memory_sources.get("kg", [])),
            check=checks.get("graphiti", {}),
            errors=[e for e in source_bundle.get("errors", []) if e.get("source") == "kg"],
        ),
        "fresh_evidence_count": fresh_evidence_count,
        "memory_reuse_count": memory_reuse_count,
        "scout_retrieval_mode": source_bundle.get("scout_retrieval_mode", "unknown"),
        "fresh_evidence_missing_reason": fresh_evidence_missing_reason(source_bundle),
        "qdrant_write": {
            "status": live_write_results.get("qdrant", {}).get("status"),
            "error": live_write_results.get("qdrant", {}).get("error"),
        },
        "graphiti_write": {
            "status": live_write_results.get("graphiti", {}).get("status"),
            "error": live_write_results.get("graphiti", {}).get("error"),
        },
    }


def _source_status(
    *,
    count: int,
    fresh_count: int,
    memory_reuse_count: int,
    check: dict[str, Any],
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "available": count > 0,
        "count": count,
        "fresh_count": fresh_count,
        "memory_reuse_count": memory_reuse_count,
        "preflight_ok": bool(check.get("ok")),
        "preflight_error": check.get("error"),
        "errors": errors,
    }


def fresh_evidence_missing_reason(source_bundle: dict[str, Any]) -> str:
    if source_bundle.get("scout") or source_bundle.get("rag") or source_bundle.get("kg"):
        return ""
    memory_sources = source_bundle.get("memory_reuse_sources", {}) or {}
    memory_count = len(memory_sources.get("rag", [])) + len(memory_sources.get("kg", []))
    if memory_count:
        return "retrieval_found_only_internal_memory_notes"
    if source_bundle.get("errors"):
        return "source_collection_errors"
    return "no_fresh_external_sources_found"


async def write_live_memory(
    *,
    thread_id: str,
    memory_note: dict[str, Any],
    memory_markdown: str,
    memory_artifact_ref: str,
    graphiti_ingest: GraphitiIngest | None = None,
    qdrant_upsert: QdrantUpsert | None = None,
    graphiti_agent_name: str = BUILDER_NAME,
    graphiti_user_message: str | None = None,
) -> dict[str, Any]:
    graphiti_result = await _write_graphiti_memory(
        thread_id=thread_id,
        memory_note=memory_note,
        memory_markdown=memory_markdown,
        graphiti_ingest=graphiti_ingest,
        graphiti_agent_name=graphiti_agent_name,
        graphiti_user_message=graphiti_user_message,
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
    graphiti_agent_name: str = BUILDER_NAME,
    graphiti_user_message: str | None = None,
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
            graphiti_user_message or f"Accumulate research memory for {thread_id}.",
            memory_markdown,
            graphiti_agent_name,
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
        "## 이번 주 새 근거",
        "",
    ]
    for label in ("scout", "rag", "kg"):
        items = brief["new_evidence"][label]
        lines.append(f"### {label.upper()}")
        if not items:
            lines.append("- 새 근거 없음")
        for item in items:
            lines.append(f"- `{item['citation']}` **{item['title']}**: {item['text']}")
        lines.append("")

    lines.extend(["## 기존 기억 재사용", ""])
    reuse_provenance = brief.get("reuse_provenance", [])
    if reuse_provenance:
        for item in reuse_provenance:
            stores = ", ".join(item.get("reused_from", []))
            supporting = ", ".join(item.get("supporting_source_refs", []))
            suffix = f" / 보조 refs: {supporting}" if supporting else ""
            lines.append(f"- `{item['citation']}` 출처 {stores}: {item.get('used_for', '')}{suffix}")
    else:
        lines.append("- 재사용된 weekly memory note 없음")
    previous = brief["reused_memory"]["previous_memory_notes"]
    if previous:
        for note in previous:
            lines.append(f"- `{note['memory_note_id']}`: {note.get('summary', '')}")
    else:
        lines.append("- 이전 weekly memory note 없음")
    thread_memory = brief["reused_memory"]["thread_memory"]
    for item in thread_memory[:5]:
        lines.append(f"- `{item['citation']}`: {item['text']}")
    memory_reuse_sources = brief.get("memory_reuse_sources", {}) or {}
    if memory_reuse_sources.get("rag") or memory_reuse_sources.get("kg"):
        lines.extend(["", "### Qdrant/Graphiti에서 회수된 내부 기억", ""])
        for label in ("rag", "kg"):
            for item in memory_reuse_sources.get(label, []):
                lines.append(f"- `{item['citation']}` **{item['title']}**: {item['text']}")

    judgment = brief["judgment_change"]
    lines.extend(["", "## 이번 주 판단 변화", ""])
    lines.append(f"- {judgment['summary']}")
    lines.append(f"- 판단 변화: {judgment['decision_delta']}")
    if judgment.get("memory_refs"):
        lines.append(f"- 사용한 기억: {', '.join(judgment['memory_refs'])}")
    if judgment.get("evidence_refs"):
        lines.append(f"- 사용한 새 근거: {', '.join(judgment['evidence_refs'])}")

    lines.extend(["", "## 약한 근거와 보류할 주장", ""])
    weak_claims = brief.get("weak_or_deferred_claims", [])
    if not weak_claims:
        lines.append("- 보류할 주장이 새로 식별되지 않음")
    for claim in weak_claims:
        refs = ", ".join(claim.get("source_refs", []))
        suffix = f" / refs: {refs}" if refs else ""
        lines.append(f"- `{claim['id']}` {claim['text']} ({claim['reason']}){suffix}")

    lines.extend(["", "## 다음 주 핵심 질문", ""])
    lines.extend(f"- {question}" for question in brief["next_week_questions"])

    lines.extend(["", "## 추천 읽기/확인 대상", ""])
    for check in brief.get("recommended_checks", []):
        lines.append(f"- `{check['id']}` {check['text']}")

    lines.extend(["", "## 새로 기억한 내용", ""])
    for claim in brief["new_memory"]["claims"]:
        lines.append(f"- `{claim['id']}`: {claim['text']}")

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
        "## 요약",
        "",
        memory_note["summary"],
        "",
        "## 판단 변화",
        "",
        f"- {memory_note['judgment_change']['summary']}",
        f"- 판단 변화: {memory_note['judgment_change']['decision_delta']}",
        "",
        "## 기억 재사용 출처",
        "",
    ]
    if not memory_note.get("reuse_provenance"):
        lines.append("- 재사용된 weekly memory note 없음")
    for item in memory_note.get("reuse_provenance", []):
        stores = ", ".join(item.get("reused_from", []))
        lines.append(f"- `{item['citation']}` 출처 {stores}: {item.get('used_for', '')}")
    memory_reuse_sources = memory_note.get("memory_reuse_sources", {}) or {}
    if memory_reuse_sources.get("rag") or memory_reuse_sources.get("kg"):
        lines.extend(["", "### 검색으로 회수된 내부 기억", ""])
        for label in ("rag", "kg"):
            for item in memory_reuse_sources.get(label, []):
                lines.append(f"- `{item['citation']}` {item['title']}")
    lines.extend([
        "",
        "## 기억할 주장",
        "",
    ])
    for claim in memory_note["claims"]:
        lines.append(f"- `{claim['id']}`: {claim['text']}")
    lines.extend(["", "## 보류할 주장", ""])
    for claim in memory_note.get("weak_or_deferred_claims", []):
        lines.append(f"- `{claim['id']}` {claim['text']} ({claim['reason']})")
    lines.extend(["", "## 다음 질문", ""])
    lines.extend(f"- {question}" for question in memory_note["next_questions"])
    lines.extend(["", "## 추천 확인 대상", ""])
    for check in memory_note.get("recommended_checks", []):
        lines.append(f"- `{check['id']}` {check['text']}")
    lines.extend(["", "## 인용", ""])
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
        "retrieval_mode": paper.get("retrieval_mode", "custom"),
        "retrieval_reason": paper.get("retrieval_reason", ""),
        "token_overlap": list(paper.get("token_overlap", []) or []),
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
        "document_type": str(payload.get("document_type") or ""),
        "memory_note_id": str(payload.get("memory_note_id") or ""),
        "payload_source": str(payload.get("source") or ""),
    }


def source_from_kg_result(result: dict[str, Any], idx: int) -> dict[str, Any]:
    uuid = str(result.get("uuid") or f"kg_{idx}")
    fact = str(result.get("fact") or result.get("text") or result.get("summary") or "")
    title = str(result.get("title") or result.get("name") or f"Graphiti fact {idx}")
    return {
        "source": "kg",
        "id": uuid,
        "title": title,
        "text": fact or "KG fact text 없음",
        "citation": f"kg:{uuid}",
        "score": result.get("score"),
        "artifact_ref": str(result.get("artifact_ref") or ""),
        "document_type": str(result.get("document_type") or ""),
        "episode_name": str(result.get("episode_name") or result.get("name") or ""),
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


def build_reuse_provenance(
    prior_notes: list[dict[str, Any]],
    source_bundle: dict[str, Any],
) -> list[dict[str, Any]]:
    """Explain which memory surfaces contributed reusable prior context."""
    provenance: list[dict[str, Any]] = []
    consumed_source_refs: set[str] = set()
    memory_sources = source_bundle.get("memory_reuse_sources", {}) or {}
    rag_sources = memory_sources.get("rag", []) or []
    kg_sources = memory_sources.get("kg", []) or []
    for note in prior_notes:
        note_id = str(note.get("memory_note_id", "previous_memory_note"))
        qdrant_refs = [
            item["citation"]
            for item in rag_sources
            if _source_matches_memory_note(item, note)
        ]
        graphiti_refs = [
            item["citation"]
            for item in kg_sources
            if _source_matches_memory_note(item, note)
        ]
        reused_from = ["RA_artifacts"]
        if qdrant_refs:
            reused_from.append("Qdrant")
        if graphiti_refs:
            reused_from.append("Graphiti")
        consumed_source_refs.update(qdrant_refs)
        consumed_source_refs.update(graphiti_refs)
        provenance.append({
            "memory_note_id": note_id,
            "citation": f"memory_note:{note_id}",
            "artifact_ref": str(note.get("artifact_ref", "")),
            "reused_from": reused_from,
            "supporting_source_refs": qdrant_refs + graphiti_refs,
            "used_for": "이번 주 판단 변화의 기준 기억으로 재사용했다.",
        })

    known_note_refs = {entry["citation"] for entry in provenance}
    for item in rag_sources:
        if (
            item["citation"] not in known_note_refs
            and item["citation"] not in consumed_source_refs
        ):
            provenance.append({
                "memory_note_id": _infer_memory_note_id(item),
                "citation": item["citation"],
                "artifact_ref": str(item.get("artifact_ref", "")),
                "reused_from": ["Qdrant"],
                "supporting_source_refs": [item["citation"]],
                "used_for": "Qdrant에서 검색된 이전 memory note 신호를 이번 주 판단의 보조 기억으로 재사용했다.",
            })
    for item in kg_sources:
        if (
            item["citation"] not in known_note_refs
            and item["citation"] not in consumed_source_refs
        ):
            provenance.append({
                "memory_note_id": _infer_memory_note_id(item),
                "citation": item["citation"],
                "artifact_ref": str(item.get("artifact_ref", "")),
                "reused_from": ["Graphiti"],
                "supporting_source_refs": [item["citation"]],
                "used_for": "Graphiti에서 검색된 이전 연구 맥락을 이번 주 판단의 보조 기억으로 재사용했다.",
            })
    return provenance


def build_judgment_change(
    *,
    thread: dict[str, Any],
    evidence_sources: list[dict[str, Any]],
    prior_notes: list[dict[str, Any]],
    reuse_provenance: list[dict[str, Any]],
) -> dict[str, Any]:
    memory_refs = [entry["citation"] for entry in reuse_provenance[:5]]
    evidence_refs = [item["citation"] for item in evidence_sources[:5]]
    focus = thread_focus_label(thread)
    if evidence_sources and prior_notes:
        summary = (
            f"이전 weekly memory note {len(prior_notes)}개를 기준 기억으로 삼고, "
            f"이번 주 새 근거 `{evidence_sources[0]['title']}`를 추가해 "
            f"{focus}의 다음 검토 초점을 근거 비교와 실행 가능한 검증 질문으로 좁혔다."
        )
        decision_delta = "기존 기억을 유지하되, 새 근거가 실제 비교 기준과 검증 요구사항을 더 명시하도록 만든다."
    elif evidence_sources:
        summary = (
            f"이전 weekly memory note는 없지만 새 근거 `{evidence_sources[0]['title']}`를 바탕으로 "
            f"{focus}의 즉시 검토 대상을 근거 비교와 다음 실행 질문으로 설정했다."
        )
        decision_delta = "새 근거를 첫 기준점으로 삼고, 다음 run에서 이 판단이 반복 재사용되는지 확인한다."
    elif prior_notes:
        summary = (
            f"새 외부 근거는 없지만 이전 weekly memory note {len(prior_notes)}개를 재사용해 "
            "열린 질문을 유지하고 다음 수집/비교 조건을 더 좁혔다."
        )
        decision_delta = "새 주장을 만들지 않고 기존 memory note의 미해결 질문을 다음 작업 기준으로 유지한다."
    else:
        summary = (
            f"`{thread['thread_id']}`의 기존 research_thread 기억만으로 이번 주 루프를 구성했다. "
            "새 주장은 보류하고, 다음 run에서 Scout/RAG/KG 근거를 확보하는 것을 우선한다."
        )
        decision_delta = "근거 부족으로 판단 확장은 보류한다."
    return {
        "summary": summary,
        "decision_delta": decision_delta,
        "support_level": "bounded_synthesis",
        "memory_refs": memory_refs,
        "evidence_refs": evidence_refs,
    }


def build_weak_or_deferred_claims(source_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    evidence_sources = source_bundle.get("scout", []) + source_bundle.get("rag", []) + source_bundle.get("kg", [])
    if not source_bundle.get("scout"):
        claims.append({
            "id": "deferred.scout_missing",
            "text": "이번 주 Scout 논문 신호가 없거나 제한적이므로 새 문헌 기반 일반화는 보류한다.",
            "reason": "Scout evidence unavailable or empty",
            "source_refs": [],
        })
    if not source_bundle.get("rag"):
        claims.append({
            "id": "deferred.rag_missing",
            "text": "Qdrant/RAG 검색 근거가 없거나 제한적이므로 기존 memory note 밖의 문헌 비교 주장은 보류한다.",
            "reason": "RAG evidence unavailable or empty",
            "source_refs": [],
        })
    if not source_bundle.get("kg"):
        claims.append({
            "id": "deferred.kg_missing",
            "text": "Fresh KG fact가 없거나 제한적이므로 장기 graph memory에 의해 검증된 새 주장으로 승격하지 않는다.",
            "reason": "KG evidence unavailable or empty",
            "source_refs": [],
        })
    if evidence_sources:
        claims.append({
            "id": "deferred.benchmark_superiority",
            "text": "새 근거 신호가 있어도 특정 접근이 대안보다 우수하다는 결론은 아직 보류한다.",
            "reason": "비교 benchmark와 반례 검토가 아직 충분하지 않다.",
            "source_refs": [item["citation"] for item in evidence_sources[:5]],
        })
    return claims[:5]


def build_recommended_checks(thread: dict[str, Any], source_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for idx, item in enumerate(source_bundle.get("scout", [])[:2], start=1):
        checks.append({
            "id": f"check.scout.{idx}",
            "kind": "read",
            "text": f"`{item['citation']}` {item['title']}를 먼저 읽고 provenance/benchmark 관련 주장만 추출한다.",
            "source_ref": item["citation"],
        })
    for idx, item in enumerate(source_bundle.get("rag", [])[:2], start=1):
        checks.append({
            "id": f"check.rag.{idx}",
            "kind": "verify_external_rag",
            "text": f"`{item['citation']}` RAG 검색 결과가 외부 근거인지, 기존 memory note의 재검색이 아닌지 원문과 대조한다.",
            "source_ref": item["citation"],
        })
    for idx, item in enumerate(source_bundle.get("kg", [])[:2], start=1):
        checks.append({
            "id": f"check.kg.{idx}",
            "kind": "verify_graph_context",
            "text": f"`{item['citation']}` Graphiti fact가 현재 research_thread의 claim/evidence와 충돌하지 않는지 확인한다.",
            "source_ref": item["citation"],
        })
    memory_sources = source_bundle.get("memory_reuse_sources", {}) or {}
    for idx, item in enumerate(memory_sources.get("rag", [])[:2], start=1):
        checks.append({
            "id": f"check.memory_rag.{idx}",
            "kind": "verify_memory",
            "text": f"`{item['citation']}` 내부 memory note 검색 결과가 원문 artifact와 일치하는지 확인한다.",
            "source_ref": item["citation"],
        })
    for idx, item in enumerate(memory_sources.get("kg", [])[:2], start=1):
        checks.append({
            "id": f"check.memory_kg.{idx}",
            "kind": "verify_graph_memory",
            "text": f"`{item['citation']}` Graphiti에서 회수된 내부 기억이 현재 판단에 과잉 반영되지 않았는지 확인한다.",
            "source_ref": item["citation"],
        })
    if not checks:
        open_actions = [
            item["text"]
            for item in thread.get("next_actions", [])
            if item.get("status") == "open"
        ]
        checks.append({
            "id": "check.thread.next_action",
            "kind": "thread_followup",
            "text": open_actions[0] if open_actions else "다음 run 전 materials ontology KG benchmark 질문을 하나로 좁힌다.",
            "source_ref": f"research_thread:{thread['thread_id']}",
        })
    return checks[:5]


def _source_matches_memory_note(source: dict[str, Any], note: dict[str, Any]) -> bool:
    haystack = _source_haystack(source)
    note_tokens = [
        str(note.get("memory_note_id", "")),
        Path(str(note.get("artifact_ref", ""))).name,
        Path(str(note.get("artifact_ref", ""))).stem,
    ]
    return any(token and token.lower() in haystack for token in note_tokens)


def is_memory_reuse_source(source: dict[str, Any]) -> bool:
    if str(source.get("document_type", "")) == "research_memory_note":
        return True
    if str(source.get("memory_note_id", "")):
        return True
    citation = str(source.get("citation", ""))
    if citation.startswith("memory_note:") or citation.startswith("rag:research_memory_note:"):
        return True
    haystack = _source_haystack(source)
    memory_markers = (
        "research_memory_note",
        "research memory note",
        "weekly research memory note",
        "weekly memory note",
        "research_memory_notes",
        "memory_note_",
        "memory note:",
        "# research memory note",
        "weekly_loop.",
    )
    return any(marker in haystack for marker in memory_markers)


def _looks_like_memory_source(source: dict[str, Any]) -> bool:
    return is_memory_reuse_source(source)


def _infer_memory_note_id(source: dict[str, Any]) -> str:
    artifact_ref = str(source.get("artifact_ref", ""))
    if artifact_ref:
        stem = Path(artifact_ref).stem
        if stem:
            return stem
    return str(source.get("id") or source.get("citation") or "unknown_memory_source")


def _source_haystack(source: dict[str, Any]) -> str:
    return " ".join(
        str(source.get(key, ""))
        for key in (
            "id",
            "title",
            "text",
            "citation",
            "artifact_ref",
            "url",
            "document_type",
            "memory_note_id",
            "payload_source",
            "episode_name",
        )
    ).lower()


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
    focus = thread_focus_label(thread)
    if evidence_sources:
        questions.append(f"이번 주 새 근거 `{evidence_sources[0]['title']}`가 {focus}의 다음 검증 설계를 어떻게 바꾸는가?")
    if prior_notes:
        questions.append("지난 weekly memory note의 결론 중 이번 근거로 수정하거나 폐기해야 할 것은 무엇인가?")
    if not questions:
        questions.append(f"{focus}에서 다음 주에 확인해야 할 최소 검증 질문은 무엇인가?")
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


def default_query_for_thread(thread_id: str) -> str:
    return THREAD_DEFAULT_QUERIES.get(thread_id, DEFAULT_QUERY)


def thread_focus_label(thread: dict[str, Any]) -> str:
    topic = str(thread.get("topic") or thread.get("thread_id") or "research thread")
    return topic.replace("_", " ")


def _safe_id(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("._") or "weekly_loop"
