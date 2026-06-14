"""Deterministic Research Coordinator dry-run loop.

This Phase 2/Chunk 3 coordinator advances research_thread artifacts through a
local-only loop: Scout preview, evidence synthesis, idea candidate, critique,
and next action. It does not call LLMs, Slack, KG/RAG stores, or runtime
services.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from orchestrator.research_context_bundle import build_research_context_bundle
from orchestrator.research_loop_packet import build_research_loop_packet
from orchestrator.subagent_output_envelope import build_subagent_output_envelope
from orchestrator.research_thread import (
    DEFAULT_SEED_TOPICS,
    load_research_thread,
    make_section_item,
    render_research_thread_markdown,
    research_thread_paths,
    utc_now,
    validate_research_thread,
    write_research_thread,
)
from orchestrator.scout_thread_adapter import (
    DEFAULT_SCOUT_QUERIES,
    apply_scout_thread_patch,
    build_scout_thread_patch,
)
from integrations.scout_reader import ScoutReader


COORDINATOR_NAME = "research_coordinator_dry_run"
STAGE_ORDER = (
    "scout",
    "evidence_synthesis",
    "idea_candidate",
    "critique",
    "next_action",
)


def _item_exists(thread: dict[str, Any], section: str, item_id: str) -> bool:
    return any(item.get("id") == item_id for item in thread.get(section, []))


def _append_once(thread: dict[str, Any], section: str, item: dict[str, Any]) -> bool:
    if _item_exists(thread, section, item["id"]):
        return False
    thread[section].append(item)
    return True


def _thread_evidence_items(thread: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in thread.get("evidence", [])
        if item.get("metadata", {}).get("adapter") == "scout_thread_adapter"
    ]


def _topic_idea_text(thread_id: str, evidence_count: int) -> str:
    if thread_id == "materials_ontology_kg":
        return (
            "Compare ontology-guided materials KG memory against plain document "
            f"RAG using the {evidence_count} Scout evidence preview item(s) now attached to this thread."
        )
    if thread_id == "rare_earth_magnets":
        return (
            "Build an evidence matrix that links composition, processing, "
            f"microstructure, properties, and application constraints from the {evidence_count} Scout evidence preview item(s)."
        )
    return f"Use the {evidence_count} Scout evidence preview item(s) to define the next research comparison."


def _topic_failure_text(thread_id: str) -> str:
    if thread_id == "materials_ontology_kg":
        return "A graph could become ontology bookkeeping unless each entity and relation changes a research decision."
    if thread_id == "rare_earth_magnets":
        return "The thread could mix supply-chain, processing, and property claims without separating evidence types."
    return "The thread could accumulate evidence without a decision-relevant comparison."


def _topic_next_action_text(thread_id: str) -> str:
    if thread_id == "materials_ontology_kg":
        return "Draft a two-column comparison: what this thread can answer with ontology/KG memory versus document RAG alone."
    if thread_id == "rare_earth_magnets":
        return "Create the first evidence matrix row for one magnet bottleneck and mark whether it supports calculation, experiment, or proposal review."
    return "Turn the current evidence preview into one decision-relevant comparison."


def _coordinator_items(thread: dict[str, Any], *, created_at: str) -> dict[str, dict[str, Any]]:
    thread_id = thread["thread_id"]
    evidence_count = len(_thread_evidence_items(thread))
    common_metadata = {
        "coordinator": COORDINATOR_NAME,
        "evidence_preview_count": evidence_count,
        "live_store_mutations": [],
    }
    return {
        "claims": make_section_item(
            "coordinator.claim.evidence_preview_ready",
            (
                f"This thread has {evidence_count} Scout-derived candidate evidence item(s) ready for human or agent review; "
                "no literature claim is accepted until source text is checked."
            ),
            status="candidate",
            created_at=created_at,
            confidence="artifact_synthesis",
            tags=["coordinator", "evidence-synthesis"],
            metadata=common_metadata,
        ),
        "idea_candidates": make_section_item(
            "coordinator.idea.first_comparison",
            _topic_idea_text(thread_id, evidence_count),
            status="candidate",
            created_at=created_at,
            confidence="requires_review",
            tags=["coordinator", "idea-candidate"],
            metadata=common_metadata,
        ),
        "counterarguments": make_section_item(
            "coordinator.counterargument.source_metadata_only",
            (
                "Scout metadata and summaries are not enough to accept the idea; source PDFs, methods, and boundary conditions still need review."
            ),
            status="open",
            created_at=created_at,
            confidence="evidence_critic",
            tags=["coordinator", "critique"],
            metadata=common_metadata,
        ),
        "failure_modes": make_section_item(
            "coordinator.failure_mode.thread_drift",
            _topic_failure_text(thread_id),
            status="open",
            created_at=created_at,
            confidence="evidence_critic",
            tags=["coordinator", "failure-mode"],
            metadata=common_metadata,
        ),
        "decisions": make_section_item(
            "coordinator.decision.dry_run_completed",
            "Complete a local-only coordinator dry-run for this thread; keep outputs in artifacts and do not mutate live KG/RAG/Scout/Slack state.",
            status="accepted",
            created_at=created_at,
            confidence="coordinator",
            tags=["coordinator", "dry-run"],
            metadata=common_metadata,
        ),
        "next_actions": make_section_item(
            "coordinator.next_action.first_review_step",
            _topic_next_action_text(thread_id),
            status="open",
            created_at=created_at,
            confidence="coordinator",
            tags=["coordinator", "next-action"],
            metadata=common_metadata,
        ),
    }


def _apply_coordinator_stages(thread: dict[str, Any], *, created_at: str) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_research_thread(thread)
    updated = copy.deepcopy(thread)
    added: dict[str, int] = {
        "claims": 0,
        "idea_candidates": 0,
        "counterarguments": 0,
        "failure_modes": 0,
        "decisions": 0,
        "next_actions": 0,
    }
    for section, item in _coordinator_items(updated, created_at=created_at).items():
        if _append_once(updated, section, item):
            added[section] += 1

    changed = any(added.values())
    if changed:
        updated["research_state"] = "coordinator_dry_run_completed"
        updated["updated_at"] = created_at
        metadata = dict(updated.get("metadata", {}))
        metadata["last_coordinator_dry_run"] = {
            "coordinator": COORDINATOR_NAME,
            "stage_order": list(STAGE_ORDER),
            "created_at": created_at,
            "added": added,
            "live_store_mutations": [],
        }
        updated["metadata"] = metadata
    validate_research_thread(updated)
    return updated, {"added": added, "changed": changed}


def _read_scout_papers(
    *,
    thread_id: str,
    db_path: Path | None,
    query: str,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reader = ScoutReader(db_path=db_path)
    try:
        papers = reader.search_papers(query, limit=limit)
        return papers, {"status": "ok", "query": query, "papers_seen": len(papers)}
    except FileNotFoundError as exc:
        return [], {"status": "scout_unavailable", "query": query, "papers_seen": 0, "error": str(exc)}
    finally:
        reader.close()


def run_coordinator_dry_run_for_thread(
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
    created_at = created_at or utc_now()
    query = query or DEFAULT_SCOUT_QUERIES.get(thread_id, thread_id.replace("_", " "))
    paths = research_thread_paths(thread_id, artifacts_dir)
    if not paths.json_path.exists():
        return {
            "status": "missing_thread",
            "dry_run": not execute,
            "thread_id": thread_id,
            "query": query,
            **paths.as_dict(),
            "error": "research_thread JSON does not exist; seed the thread before running the coordinator",
            "live_store_mutations": [],
        }

    original = load_research_thread(thread_id, artifacts_dir=artifacts_dir)
    papers, scout_stage = _read_scout_papers(
        thread_id=thread_id,
        db_path=db_path,
        query=query,
        limit=limit,
    )
    scout_patch = build_scout_thread_patch(
        original,
        papers,
        query=query,
        min_score=min_score,
        created_at=created_at,
    )
    after_scout = apply_scout_thread_patch(original, scout_patch)
    updated, coordinator_patch = _apply_coordinator_stages(after_scout, created_at=created_at)
    context_bundle = build_research_context_bundle(
        research_thread=original,
        trigger_type="automatic",
        trigger_summary=f"Coordinator dry-run: {query}",
        created_at=created_at,
    )
    loop_packet = build_research_loop_packet(
        research_thread=original,
        trigger_type="automatic",
        trigger_summary=f"Coordinator dry-run: {query}",
        created_at=created_at,
    )
    evidence_critic_envelope = build_subagent_output_envelope(
        loop_packet=loop_packet,
        role="Evidence Critic",
        output_type="evidence_boundary_preview",
        summary=(
            "Coordinator dry-run 결과는 source metadata와 deterministic synthesis를 검토 대상으로만 다루며, "
            "확정 claim이나 KG fact로 승격하지 않는다."
        ),
        loop_packet_ref=f"inline:{loop_packet['packet_id']}",
        missing_evidence=[
            "Scout metadata 또는 deterministic summary만으로는 문헌 claim, 수치, citation을 확정할 수 없다."
        ],
        counterarguments=[
            "Coordinator dry-run이 만든 idea candidate는 연구 가치 후보일 뿐 계산, 실험, 제안서 준비 완료 신호가 아니다."
        ],
        failure_modes=[
            "dry-run output을 승인 없이 live KG/RAG/Slack state로 승격하면 실패한다."
        ],
        artifact_candidates=[
            "Coordinator review note와 thread patch preview를 같은 research_thread 검토 흐름에 남긴다."
        ],
        created_at=created_at,
    )

    changed = bool(scout_patch["source_signals"] or scout_patch["evidence"] or coordinator_patch["changed"])
    status = "updated" if execute and changed else "would_update" if changed else "no_changes"
    result = {
        "status": status,
        "dry_run": not execute,
        "thread_id": thread_id,
        "query": query,
        "limit": limit,
        "min_score": min_score,
        **paths.as_dict(),
        "stages": {
            "scout": {
                **scout_stage,
                "source_signals_added": len(scout_patch["source_signals"]),
                "evidence_added": len(scout_patch["evidence"]),
                "duplicates": scout_patch["duplicates"],
                "skipped_low_score": scout_patch["skipped_low_score"],
            },
            "evidence_synthesis": {"claims_added": coordinator_patch["added"]["claims"]},
            "idea_candidate": {"idea_candidates_added": coordinator_patch["added"]["idea_candidates"]},
            "critique": {
                "counterarguments_added": coordinator_patch["added"]["counterarguments"],
                "failure_modes_added": coordinator_patch["added"]["failure_modes"],
            },
            "next_action": {"next_actions_added": coordinator_patch["added"]["next_actions"]},
        },
        "context_bundle": context_bundle,
        "loop_packet": loop_packet,
        "evidence_critic_envelope": evidence_critic_envelope,
        "merged_thread_patch_preview": evidence_critic_envelope["recommended_thread_patch"],
        "preview_markdown": render_research_thread_markdown(updated),
        "live_store_mutations": [],
    }
    if execute and changed:
        result["write"] = write_research_thread(updated, artifacts_dir=artifacts_dir, overwrite=True)
    return result


def run_coordinator_dry_run(
    *,
    artifacts_dir: Path | None = None,
    db_path: Path | None = None,
    limit: int = 10,
    min_score: float = 70.0,
    execute: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    created_at = created_at or utc_now()
    results = [
        run_coordinator_dry_run_for_thread(
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
        "coordinator": COORDINATOR_NAME,
        "stage_order": list(STAGE_ORDER),
        "threads": results,
        "live_store_mutations": [],
    }
