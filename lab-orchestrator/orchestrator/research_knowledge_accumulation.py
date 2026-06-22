"""Portable knowledge accumulation records for research_thread memory.

This module turns reviewed research_thread objects into durable knowledge
records and optional archival queue jobs. It does not call Graphiti, Qdrant,
Scout, Slack, or any live service directly.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.config import ARCHIVAL_QUEUE_DIR
from orchestrator.research_thread import (
    SECTION_NAMES,
    load_research_thread,
    normalize_research_thread,
    resolve_artifacts_dir,
    utc_now,
    validate_research_thread,
)


SCHEMA_VERSION = 1
BUILDER_NAME = "research_knowledge_accumulation_v1"
KNOWLEDGE_RECORDS_DIR = "research_knowledge_records"
CONTRACT_REF = "docs/ceml-ra-ground-goal-and-phases.md"

READY_STATUSES = {"accepted", "completed"}
READY_REVIEW_STATES = {"reviewed"}
READY_AUTHORITY_STATES = {"ground_contract", "reviewed_artifact"}


@dataclass(frozen=True)
class KnowledgeRecordPaths:
    json_path: Path
    markdown_path: Path
    archival_queue_preview_path: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "json_path": str(self.json_path),
            "markdown_path": str(self.markdown_path),
            "archival_queue_preview_path": str(self.archival_queue_preview_path),
        }


def research_knowledge_records_dir(artifacts_dir: Path | None = None) -> Path:
    return resolve_artifacts_dir(artifacts_dir) / KNOWLEDGE_RECORDS_DIR


def knowledge_record_paths(
    *,
    thread_id: str,
    record_set_id: str,
    artifacts_dir: Path | None = None,
) -> KnowledgeRecordPaths:
    base = research_knowledge_records_dir(artifacts_dir)
    stem = f"{thread_id}_{record_set_id}"
    return KnowledgeRecordPaths(
        json_path=base / f"{stem}.json",
        markdown_path=base / f"{stem}.md",
        archival_queue_preview_path=base / f"{stem}_archival_queue_preview.json",
    )


def build_knowledge_record_set(
    *,
    research_thread: dict[str, Any],
    purpose: str,
    include_pending_review: bool = False,
    created_at: str | None = None,
    max_records: int = 50,
) -> dict[str, Any]:
    thread = normalize_research_thread(research_thread)
    validate_research_thread(thread)
    purpose = _clean_text(purpose, "purpose")
    generated_at = created_at or utc_now()
    record_set_id = build_record_set_id(thread_id=thread["thread_id"], purpose=purpose)
    records = select_knowledge_records(
        thread,
        record_set_id=record_set_id,
        include_pending_review=include_pending_review,
        max_records=max_records,
    )
    ready_records = [record for record in records if record["accumulation_state"] == "ready_for_archival_queue"]
    queue_preview = [build_archival_queue_job(record) for record in ready_records]
    coverage = {
        "record_count": len(records),
        "ready_for_archival_queue": len(ready_records),
        "needs_review": len([record for record in records if record["accumulation_state"] == "needs_review"]),
        "source_thread_sections": _section_counts(thread),
        "live_store_mutations": [],
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "builder": BUILDER_NAME,
        "generated_at": generated_at,
        "record_set_id": record_set_id,
        "thread_id": thread["thread_id"],
        "topic": thread["topic"],
        "research_state": thread["research_state"],
        "purpose": purpose,
        "include_pending_review": include_pending_review,
        "selection_policy": {
            "ready_statuses": sorted(READY_STATUSES),
            "ready_review_states": sorted(READY_REVIEW_STATES),
            "ready_authority_states": sorted(READY_AUTHORITY_STATES),
            "pending_review_policy": "included_as_needs_review" if include_pending_review else "excluded",
        },
        "records": records,
        "archival_queue_preview": queue_preview,
        "coverage": coverage,
        "destination_previews": {
            "graphiti_archival_queue": {
                "status": "preview_only",
                "ready_records": len(queue_preview),
                "worker_required": "archival_worker가 queue job을 처리해야 Graphiti live store가 변경된다.",
                "live_store_mutations": [],
            },
            "qdrant_rag": {
                "status": "deferred",
                "reason": "Qdrant write는 source document chunk contract가 필요하므로 이 record set에서는 preview만 남긴다.",
                "live_store_mutations": [],
            },
        },
        "live_store_mutations": [],
    }


def preview_or_write_knowledge_records(
    *,
    thread_id: str,
    purpose: str,
    artifacts_dir: Path | None = None,
    execute: bool = False,
    enqueue_archival: bool = False,
    archival_queue_dir: Path | None = None,
    include_pending_review: bool = False,
    created_at: str | None = None,
    max_records: int = 50,
) -> dict[str, Any]:
    thread = load_research_thread(thread_id, artifacts_dir=artifacts_dir)
    record_set = build_knowledge_record_set(
        research_thread=thread,
        purpose=purpose,
        include_pending_review=include_pending_review,
        created_at=created_at,
        max_records=max_records,
    )
    paths = knowledge_record_paths(
        thread_id=thread_id,
        record_set_id=record_set["record_set_id"],
        artifacts_dir=artifacts_dir,
    )
    markdown = render_knowledge_record_set_markdown(record_set)
    artifact_mutations: list[dict[str, str]] = []
    archival_queue_mutations: list[dict[str, str]] = []
    status = "would_enqueue_archival" if enqueue_archival and not execute else "would_write"
    if execute:
        paths.json_path.parent.mkdir(parents=True, exist_ok=True)
        paths.json_path.write_text(
            json.dumps(record_set, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths.markdown_path.write_text(markdown, encoding="utf-8")
        paths.archival_queue_preview_path.write_text(
            json.dumps(record_set["archival_queue_preview"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifact_mutations.extend([
            {"type": "knowledge_record_json", "path": str(paths.json_path)},
            {"type": "knowledge_record_markdown", "path": str(paths.markdown_path)},
            {"type": "archival_queue_preview", "path": str(paths.archival_queue_preview_path)},
        ])
        status = "written"
    if enqueue_archival:
        if not execute:
            status = "would_enqueue_archival"
        else:
            archival_queue_mutations = enqueue_archival_jobs(
                record_set,
                archival_queue_dir=archival_queue_dir,
            )
            status = "archival_queued"

    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "dry_run": not execute,
        "read_only": not execute and not enqueue_archival,
        "artifact_write": execute,
        "archival_enqueue": bool(enqueue_archival and execute),
        "thread_id": thread_id,
        "record_set_id": record_set["record_set_id"],
        **paths.as_dict(),
        "record_set": record_set,
        "preview_markdown": markdown,
        "artifact_mutations": artifact_mutations,
        "archival_queue_mutations": archival_queue_mutations,
        "live_store_mutations": [],
    }


def select_knowledge_records(
    thread: dict[str, Any],
    *,
    record_set_id: str,
    include_pending_review: bool,
    max_records: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for section in SECTION_NAMES:
        for item in thread.get(section, []):
            state = accumulation_state(item)
            if state == "not_selected":
                if not include_pending_review:
                    continue
                state = "needs_review"
            record = build_knowledge_record(
                thread=thread,
                section=section,
                item=item,
                record_set_id=record_set_id,
                accumulation_state_value=state,
            )
            records.append(record)
            if len(records) >= max_records:
                return records
    return records


def accumulation_state(item: dict[str, Any]) -> str:
    if (
        item.get("status") in READY_STATUSES
        or item.get("review_state") in READY_REVIEW_STATES
        or item.get("authority_state") in READY_AUTHORITY_STATES
    ):
        return "ready_for_archival_queue"
    return "not_selected"


def build_knowledge_record(
    *,
    thread: dict[str, Any],
    section: str,
    item: dict[str, Any],
    record_set_id: str,
    accumulation_state_value: str,
) -> dict[str, Any]:
    object_ref = str(item.get("object_ref") or f"{section}:{item.get('id', '')}")
    record_id = build_record_id(thread_id=thread["thread_id"], object_ref=object_ref, text=str(item.get("text", "")))
    knowledge_text = build_knowledge_text(thread=thread, section=section, item=item)
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "record_set_id": record_set_id,
        "thread_id": thread["thread_id"],
        "topic": thread["topic"],
        "section": section,
        "object_id": str(item.get("id", "")),
        "object_ref": object_ref,
        "object_type": str(item.get("object_type", section)),
        "text": str(item.get("text", "")),
        "knowledge_text": knowledge_text,
        "status": str(item.get("status", "")),
        "authority_state": str(item.get("authority_state", "")),
        "review_state": str(item.get("review_state", "")),
        "support_state": str(item.get("support_state", "")),
        "source_refs": list(item.get("source_refs", []) or []),
        "artifact_refs": list(item.get("artifact_refs", []) or []),
        "related_object_refs": list(item.get("related_object_refs", []) or []),
        "provenance": dict(item.get("provenance", {}) or {}),
        "accumulation_state": accumulation_state_value,
        "destination_policy": {
            "graphiti": "queue_after_explicit_enqueue" if accumulation_state_value == "ready_for_archival_queue" else "hold_until_reviewed",
            "qdrant": "deferred_until_document_chunk_contract",
        },
        "live_store_mutations": [],
    }


def build_record_set_id(*, thread_id: str, purpose: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", purpose).strip("_").lower() or "knowledge_accumulation"
    digest = hashlib.sha1(f"{thread_id}:{purpose}".encode("utf-8")).hexdigest()[:10]
    return f"{slug[:40]}_{digest}"


def build_record_id(*, thread_id: str, object_ref: str, text: str) -> str:
    digest = hashlib.sha1(f"{thread_id}:{object_ref}:{text}".encode("utf-8")).hexdigest()[:12]
    return f"knowledge_record.{_safe_id(thread_id)}.{_safe_id(object_ref)}.{digest}"


def build_knowledge_text(*, thread: dict[str, Any], section: str, item: dict[str, Any]) -> str:
    source_refs = ", ".join(item.get("source_refs", []) or []) or "source_refs 없음"
    return (
        f"Research thread `{thread['thread_id']}` / section `{section}` / object `{item.get('object_ref', '')}`\n"
        f"상태: status={item.get('status', '')}, review={item.get('review_state', '')}, "
        f"support={item.get('support_state', '')}, authority={item.get('authority_state', '')}\n"
        f"내용: {item.get('text', '')}\n"
        f"Source refs: {source_refs}"
    )


def build_archival_queue_job(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "conversation_id": record["record_id"],
        "user_message": "Accumulate reviewed CEML_RA research_thread knowledge.",
        "assistant_message": record["knowledge_text"],
        "agent_name": BUILDER_NAME,
        "timestamp": utc_now(),
        "metadata": {
            "thread_id": record["thread_id"],
            "object_ref": record["object_ref"],
            "section": record["section"],
            "record_id": record["record_id"],
            "source_refs": record["source_refs"],
        },
    }


def enqueue_archival_jobs(
    record_set: dict[str, Any],
    *,
    archival_queue_dir: Path | None = None,
) -> list[dict[str, str]]:
    queue_dir = (archival_queue_dir or ARCHIVAL_QUEUE_DIR).expanduser().resolve()
    queue_dir.mkdir(parents=True, exist_ok=True)
    mutations = []
    for job in record_set.get("archival_queue_preview", []):
        record_id = str(job.get("metadata", {}).get("record_id", "knowledge_record"))
        path = queue_dir / f"{_safe_id(record_id)}.json"
        status = "exists" if path.exists() else "queued"
        if not path.exists():
            path.write_text(json.dumps(job, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        mutations.append({"type": "archival_queue_job", "path": str(path), "status": status})
    return mutations


def render_knowledge_record_set_markdown(record_set: dict[str, Any]) -> str:
    lines = [
        f"# Research Knowledge Records: {record_set['thread_id']}",
        "",
        f"- Record set ID: `{record_set['record_set_id']}`",
        f"- 생성 시각: `{record_set['generated_at']}`",
        f"- Purpose: {record_set['purpose']}",
        f"- Records: `{record_set['coverage']['record_count']}`",
        f"- Archival queue ready: `{record_set['coverage']['ready_for_archival_queue']}`",
        "- 라이브 저장소 변경: 없음",
        "",
        "## 축적 경계",
        "",
        "이 artifact는 reviewed/accepted research_thread object를 장기 기억 후보 record로 고정한다.",
        "Graphiti/Qdrant/Slack live store를 직접 변경하지 않으며, Graphiti 반영은 별도 archival queue worker가 처리한다.",
        "",
        "## Knowledge Records",
        "",
    ]
    if not record_set["records"]:
        lines.append("- 축적 가능한 record 없음")
    for record in record_set["records"]:
        lines.extend([
            f"- `{record['record_id']}` [{record['accumulation_state']}]",
            f"  - Object: `{record['object_ref']}` ({record['section']})",
            f"  - State: `{record['status']}` / `{record['review_state']}` / `{record['support_state']}`",
            f"  - Text: {record['text']}",
        ])
    lines.extend([
        "",
        "## Archival Queue Preview",
        "",
    ])
    if not record_set["archival_queue_preview"]:
        lines.append("- queue 후보 없음")
    for job in record_set["archival_queue_preview"]:
        metadata = job.get("metadata", {})
        lines.append(f"- `{metadata.get('record_id', '')}` -> conversation `{job.get('conversation_id', '')}`")
    lines.extend([
        "",
        "## Destination Previews",
        "",
        "```json",
        json.dumps(record_set["destination_previews"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
    ])
    return "\n".join(lines)


def _section_counts(thread: dict[str, Any]) -> dict[str, int]:
    return {section: len(thread.get(section, [])) for section in SECTION_NAMES}


def _clean_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _safe_id(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("._") or "knowledge_record"
