"""Shared read-only context bundles for automatic and on-demand research loops.

This module converts a research_thread into the common context shape used by
Coordinator planning. It does not create research claims, mutate artifacts, or
touch Slack/Scout/KG/RAG/runtime stores.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.research_thread import (
    SECTION_NAMES,
    load_research_thread,
    normalize_research_thread,
    resolve_artifacts_dir,
    utc_now,
    validate_research_thread,
)


SCHEMA_VERSION = 1
BUILDER_NAME = "research_context_bundle_v1"
CONTEXT_BUNDLES_DIR = "research_context_bundles"
VALID_TRIGGER_TYPES = ("automatic", "on_demand")

RELEVANT_STATUSES = {
    "open",
    "candidate",
    "proposed",
    "unresolved",
    "blocked_until_evidence",
}


@dataclass(frozen=True)
class ResearchContextBundlePaths:
    json_path: Path
    markdown_path: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "json_path": str(self.json_path),
            "markdown_path": str(self.markdown_path),
        }


def research_context_bundles_dir(artifacts_dir: Path | None = None) -> Path:
    return resolve_artifacts_dir(artifacts_dir) / CONTEXT_BUNDLES_DIR


def research_context_bundle_paths(
    *,
    thread_id: str,
    bundle_id: str,
    artifacts_dir: Path | None = None,
) -> ResearchContextBundlePaths:
    base = research_context_bundles_dir(artifacts_dir)
    stem = f"{thread_id}_{bundle_id}"
    return ResearchContextBundlePaths(
        json_path=base / f"{stem}.json",
        markdown_path=base / f"{stem}.md",
    )


def build_research_context_bundle(
    *,
    research_thread: dict[str, Any],
    trigger_type: str,
    trigger_summary: str,
    created_at: str | None = None,
    max_objects: int = 12,
) -> dict[str, Any]:
    thread = normalize_research_thread(research_thread)
    validate_research_thread(thread)
    trigger = _build_trigger(trigger_type=trigger_type, trigger_summary=trigger_summary)
    generated_at = created_at or utc_now()
    bundle_id = build_bundle_id(
        thread_id=thread["thread_id"],
        trigger_type=trigger["type"],
        trigger_summary=trigger["summary"],
    )
    relevant_objects = select_relevant_objects(thread, max_objects=max_objects)
    evidence_gaps = build_evidence_gaps(thread)
    artifact_refs = _unique_ref_values(thread, "artifact_refs")
    source_refs = _unique_ref_values(thread, "source_refs")

    return {
        "schema_version": SCHEMA_VERSION,
        "builder": BUILDER_NAME,
        "generated_at": generated_at,
        "bundle_id": bundle_id,
        "thread_id": thread["thread_id"],
        "topic": thread["topic"],
        "research_state": thread["research_state"],
        "trigger": trigger,
        "thread_summary": build_thread_summary(thread),
        "relevant_objects": relevant_objects,
        "weak_claims": select_weak_claims(thread),
        "evidence_gaps": evidence_gaps,
        "artifact_refs": artifact_refs,
        "retrieval_candidates": build_retrieval_candidates(relevant_objects, source_refs),
        "activation_previews": build_activation_previews(
            thread_id=thread["thread_id"],
            relevant_objects=relevant_objects,
            artifact_refs=artifact_refs,
            source_refs=source_refs,
        ),
        "stop_conditions": build_stop_conditions(trigger),
        "context_boundary": (
            "이 bundle은 automatic/on-demand 루프가 같은 research_thread 기억을 읽기 위한 "
            "read-only 입력이다. 새 claim, evidence, artifact, live mutation을 만들지 않는다."
        ),
        "live_store_mutations": [],
    }


def preview_or_write_research_context_bundle(
    *,
    thread_id: str,
    trigger_type: str,
    trigger_summary: str,
    artifacts_dir: Path | None = None,
    execute: bool = False,
    created_at: str | None = None,
    max_objects: int = 12,
) -> dict[str, Any]:
    research_thread = load_research_thread(thread_id, artifacts_dir=artifacts_dir)
    bundle = build_research_context_bundle(
        research_thread=research_thread,
        trigger_type=trigger_type,
        trigger_summary=trigger_summary,
        created_at=created_at,
        max_objects=max_objects,
    )
    paths = research_context_bundle_paths(
        thread_id=thread_id,
        bundle_id=bundle["bundle_id"],
        artifacts_dir=artifacts_dir,
    )
    markdown = render_research_context_bundle_markdown(bundle)
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "written" if execute else "would_write",
        "dry_run": not execute,
        "thread_id": thread_id,
        "bundle_id": bundle["bundle_id"],
        **paths.as_dict(),
        "bundle": bundle,
        "preview_markdown": markdown,
        "live_store_mutations": [],
    }
    if execute:
        paths.json_path.parent.mkdir(parents=True, exist_ok=True)
        paths.json_path.write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths.markdown_path.write_text(markdown, encoding="utf-8")
    return result


def build_bundle_id(*, thread_id: str, trigger_type: str, trigger_summary: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", trigger_summary).strip("_").lower() or "context"
    digest = hashlib.sha1(f"{thread_id}:{trigger_type}:{trigger_summary}".encode("utf-8")).hexdigest()[:10]
    return f"{trigger_type}_{slug[:40]}_{digest}"


def build_thread_summary(thread: dict[str, Any]) -> dict[str, Any]:
    return {
        "thread_id": thread["thread_id"],
        "topic": thread["topic"],
        "research_state": thread["research_state"],
        "schema_version": thread["schema_version"],
        "section_counts": {section: len(thread.get(section, [])) for section in SECTION_NAMES},
        "open_next_actions": _compact_items(
            "next_actions",
            [item for item in thread.get("next_actions", []) if item.get("status") == "open"],
            limit=5,
        ),
        "recent_decisions": _compact_items("decisions", thread.get("decisions", [])[-5:], limit=5),
    }


def select_relevant_objects(thread: dict[str, Any], *, max_objects: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    preferred_sections = (
        "claims",
        "evidence",
        "counterarguments",
        "idea_candidates",
        "failure_modes",
        "next_actions",
        "decisions",
        "kg_ingest_preview",
        "source_signals",
    )
    for section in preferred_sections:
        items = thread.get(section, [])
        prioritized = [
            item for item in items
            if item.get("status") in RELEVANT_STATUSES
            or item.get("review_state") != "reviewed"
            or item.get("support_state") in {"needs_evidence", "not_evaluated", "blocked_until_evidence"}
        ]
        if not prioritized and section in {"decisions", "source_signals"}:
            prioritized = items[-2:]
        selected.extend(_compact_items(section, prioritized, limit=max_objects - len(selected)))
        if len(selected) >= max_objects:
            break
    return selected[:max_objects]


def select_weak_claims(thread: dict[str, Any]) -> list[dict[str, Any]]:
    weak = [
        item for item in thread.get("claims", [])
        if item.get("support_state") in {"needs_evidence", "not_evaluated"}
        or item.get("review_state") != "reviewed"
    ]
    return _compact_items("claims", weak, limit=8)


def build_evidence_gaps(thread: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = []
    for section in ("claims", "counterarguments", "failure_modes", "kg_ingest_preview"):
        for item in thread.get(section, []):
            if item.get("support_state") in {"needs_evidence", "not_evaluated", "blocked_until_evidence"}:
                gaps.append(item)
            elif item.get("status") in {"open", "candidate", "blocked_until_evidence"}:
                gaps.append(item)
    return _compact_items("evidence_gaps", gaps, limit=10)


def build_retrieval_candidates(
    relevant_objects: list[dict[str, Any]],
    source_refs: list[str],
) -> list[dict[str, Any]]:
    candidates = []
    for idx, source_ref in enumerate(source_refs[:10], start=1):
        candidates.append({
            "id": f"retrieval.source_ref.{idx}",
            "source_ref": source_ref,
            "reason": "research_thread object가 참조한 source를 RAG/문헌 검토 후보로 유지한다.",
            "status": "preview_only",
        })
    for item in relevant_objects[:5]:
        if item.get("object_ref"):
            candidates.append({
                "id": f"retrieval.object_ref.{len(candidates) + 1}",
                "object_ref": item["object_ref"],
                "reason": "요청 맥락과 관련된 thread object를 retrieval/query seed로 유지한다.",
                "status": "preview_only",
            })
    return candidates


def build_activation_previews(
    *,
    thread_id: str,
    relevant_objects: list[dict[str, Any]],
    artifact_refs: list[str],
    source_refs: list[str],
) -> dict[str, Any]:
    object_refs = [item["object_ref"] for item in relevant_objects if item.get("object_ref")]
    return {
        "kg_ingest_preview": {
            "status": "preview_only",
            "candidate_object_refs": object_refs[:10],
            "artifact_refs": artifact_refs[:10],
            "approval_boundary": "Neo4j/Graphiti ingest는 명시적 사용자 승인 후 별도 실행 경계에서만 가능하다.",
            "live_store_mutations": [],
        },
        "rag_retrieval_preview": {
            "status": "preview_only",
            "source_refs": source_refs[:10],
            "approval_boundary": "Qdrant/RAG write 또는 reindex는 명시적 사용자 승인 후 별도 실행 경계에서만 가능하다.",
            "live_store_mutations": [],
        },
        "slack_discussion_preview": {
            "status": "preview_only",
            "thread_id": thread_id,
            "suggested_surface": "review_summary",
            "approval_boundary": "Slack send는 명시적 사용자 승인 후 별도 실행 경계에서만 가능하다.",
            "live_store_mutations": [],
        },
    }


def build_stop_conditions(trigger: dict[str, str]) -> list[str]:
    conditions = [
        "context bundle이 새 research claim, 수치, citation을 만들어야 하면 멈춘다.",
        "thread artifact를 변경해야 하면 patch preview만 만들고 멈춘다.",
        "KG/RAG/Slack/Scout/runtime write가 필요하면 preview만 남기고 멈춘다.",
        "한국어 사용자 검토 문장을 유지할 수 없으면 멈춘다.",
    ]
    if trigger["type"] == "on_demand":
        conditions.append("사용자 요청이 기존 thread와 연결되지 않으면 답변 전에 clarification이 필요하다.")
    else:
        conditions.append("자동 루프가 기억 갱신 후보 없이 observation만 늘리면 멈춘다.")
    return conditions


def render_research_context_bundle_markdown(bundle: dict[str, Any]) -> str:
    lines = [
        f"# Research Context Bundle: {bundle['thread_id']}",
        "",
        f"- Bundle ID: `{bundle['bundle_id']}`",
        f"- 생성 시각: `{bundle['generated_at']}`",
        f"- Trigger: `{bundle['trigger']['type']}`",
        f"- Trigger summary: {bundle['trigger']['summary']}",
        "- 라이브 저장소 변경: 없음",
        "",
        "## Context Boundary",
        "",
        bundle["context_boundary"],
        "",
        "## Thread Summary",
        "",
        f"- Topic: `{bundle['thread_summary']['topic']}`",
        f"- Research state: `{bundle['thread_summary']['research_state']}`",
        "",
        "## Relevant Objects",
        "",
    ]
    if not bundle["relevant_objects"]:
        lines.append("- 관련 object 없음")
    else:
        for item in bundle["relevant_objects"]:
            lines.append(
                f"- `{item['object_ref']}` ({item['section']}) "
                f"[{item['status']}/{item['review_state']}/{item['support_state']}] {item['text']}"
            )
    lines.extend(["", "## Evidence Gaps", ""])
    if not bundle["evidence_gaps"]:
        lines.append("- evidence gap 없음")
    else:
        for item in bundle["evidence_gaps"]:
            lines.append(f"- `{item['object_ref']}` [{item['status']}] {item['text']}")
    lines.extend(["", "## Activation Previews", "", "```json"])
    lines.append(json.dumps(bundle["activation_previews"], ensure_ascii=False, indent=2, sort_keys=True))
    lines.extend(["```", ""])
    return "\n".join(lines)


def _build_trigger(*, trigger_type: str, trigger_summary: str) -> dict[str, str]:
    if trigger_type not in VALID_TRIGGER_TYPES:
        valid = ", ".join(VALID_TRIGGER_TYPES)
        raise ValueError(f"unsupported trigger_type: {trigger_type}. Valid trigger types: {valid}")
    if not isinstance(trigger_summary, str) or not trigger_summary.strip():
        raise ValueError("trigger_summary must be a non-empty string")
    return {
        "type": trigger_type,
        "summary": trigger_summary.strip(),
    }


def _compact_items(section: str, items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    compact = []
    for item in items[:max(limit, 0)]:
        compact.append({
            "thread_id": item.get("thread_id"),
            "section": section,
            "id": item.get("id", ""),
            "object_ref": item.get("object_ref", f"{section}:{item.get('id', '')}"),
            "text": item.get("text", ""),
            "status": item.get("status", ""),
            "authority_state": item.get("authority_state", ""),
            "review_state": item.get("review_state", ""),
            "support_state": item.get("support_state", ""),
            "source_refs": list(item.get("source_refs", [])),
            "artifact_refs": list(item.get("artifact_refs", [])),
            "related_object_refs": list(item.get("related_object_refs", [])),
        })
    return compact


def _unique_ref_values(thread: dict[str, Any], field: str) -> list[str]:
    values: list[str] = []
    for section in SECTION_NAMES:
        for item in thread.get(section, []):
            for value in item.get(field, []):
                if isinstance(value, str) and value.strip() and value not in values:
                    values.append(value)
    return values
