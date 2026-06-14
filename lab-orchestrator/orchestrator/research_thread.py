"""Durable research_thread artifacts for the CEML_RA memory spine.

This module owns the Phase 1 artifact contract only. It writes human-readable
Markdown plus machine-readable JSON and does not touch live DB, KG, RAG, Scout,
Slack, or runtime services.
"""

from __future__ import annotations

import json
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from orchestrator.config import ARTIFACTS_DIR


SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = (1, 2)
RESEARCH_THREADS_DIR = "research_threads"
DEFAULT_SEED_TOPICS = ("materials_ontology_kg", "rare_earth_magnets")
GROUND_CONTRACT_REF = "docs/ceml-ra-ground-goal-and-phases.md"

SECTION_NAMES = (
    "source_signals",
    "claims",
    "evidence",
    "counterarguments",
    "idea_candidates",
    "failure_modes",
    "decisions",
    "next_actions",
    "kg_ingest_preview",
)

SECTION_OBJECT_TYPES = {
    "source_signals": "source_signal",
    "claims": "claim",
    "evidence": "evidence",
    "counterarguments": "counterargument",
    "idea_candidates": "idea_candidate",
    "failure_modes": "failure_mode",
    "decisions": "decision",
    "next_actions": "next_action",
    "kg_ingest_preview": "kg_ingest_preview",
}

REQUIRED_FIELDS = (
    "schema_version",
    "thread_id",
    "topic",
    "research_state",
    "created_at",
    "updated_at",
)


@dataclass(frozen=True)
class ResearchThreadPaths:
    json_path: Path
    markdown_path: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "json_path": str(self.json_path),
            "markdown_path": str(self.markdown_path),
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_artifacts_dir(artifacts_dir: Path | None = None) -> Path:
    return (artifacts_dir or ARTIFACTS_DIR).expanduser().resolve()


def research_threads_dir(artifacts_dir: Path | None = None) -> Path:
    return resolve_artifacts_dir(artifacts_dir) / RESEARCH_THREADS_DIR


def research_thread_paths(thread_id: str, artifacts_dir: Path | None = None) -> ResearchThreadPaths:
    base = research_threads_dir(artifacts_dir)
    return ResearchThreadPaths(
        json_path=base / f"{thread_id}.json",
        markdown_path=base / f"{thread_id}.md",
    )


def make_section_item(
    item_id: str,
    text: str,
    *,
    status: str = "open",
    created_at: str | None = None,
    source_refs: Iterable[str] | None = None,
    confidence: str | None = None,
    tags: Iterable[str] | None = None,
    metadata: dict[str, Any] | None = None,
    object_type: str | None = None,
    object_ref: str | None = None,
    authority_state: str | None = None,
    review_state: str | None = None,
    support_state: str | None = None,
    artifact_refs: Iterable[str] | None = None,
    related_object_refs: Iterable[str] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": item_id,
        "text": text,
        "status": status,
        "created_at": created_at or utc_now(),
        "object_type": object_type or _infer_object_type(item_id),
        "object_ref": object_ref or _object_ref_from_item_id(item_id),
        "authority_state": authority_state or "thread_local",
        "review_state": review_state or _default_review_state(status),
        "support_state": support_state or confidence or "not_evaluated",
        "artifact_refs": list(artifact_refs or []),
        "related_object_refs": list(related_object_refs or []),
        "provenance": dict(provenance or {}),
    }
    if source_refs:
        item["source_refs"] = list(source_refs)
        item["provenance"].setdefault("source_refs", list(source_refs))
    if confidence is not None:
        item["confidence"] = confidence
    if tags:
        item["tags"] = list(tags)
    if metadata:
        item["metadata"] = metadata
    return item


def normalize_research_thread(thread: dict[str, Any]) -> dict[str, Any]:
    """Return a schema v2 thread while accepting legacy schema v1 artifacts."""
    if not isinstance(thread, dict):
        raise ValueError("research_thread must be an object")
    data = copy.deepcopy(thread)
    missing = [field for field in REQUIRED_FIELDS if field not in data]
    if missing:
        raise ValueError(f"research_thread missing required fields: {', '.join(missing)}")
    schema_version = data["schema_version"]
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported research_thread schema_version: {schema_version}")
    for section in SECTION_NAMES:
        if section not in data:
            raise ValueError(f"research_thread missing section: {section}")
        if not isinstance(data[section], list):
            raise ValueError(f"research_thread section must be a list: {section}")
        data[section] = [
            _normalize_section_item(section, item, legacy=schema_version == 1)
            for item in data[section]
        ]
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("research_thread metadata must be an object")
    data["metadata"] = dict(metadata)
    data["metadata"].setdefault("authority_model", "research_thread_v2")
    data["metadata"].setdefault("object_model", "section_items_with_object_refs")
    data["schema_version"] = SCHEMA_VERSION
    return data


def validate_research_thread(thread: dict[str, Any]) -> None:
    thread = normalize_research_thread(thread)
    missing = [field for field in REQUIRED_FIELDS if field not in thread]
    if missing:
        raise ValueError(f"research_thread missing required fields: {', '.join(missing)}")
    if thread["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported research_thread schema_version: {thread['schema_version']}")
    for field in ("thread_id", "topic", "research_state", "created_at", "updated_at"):
        if not isinstance(thread[field], str) or not thread[field].strip():
            raise ValueError(f"research_thread field must be a non-empty string: {field}")
    for section in SECTION_NAMES:
        if section not in thread:
            raise ValueError(f"research_thread missing section: {section}")
        if not isinstance(thread[section], list):
            raise ValueError(f"research_thread section must be a list: {section}")
        for item in thread[section]:
            _validate_section_item(section, item)
    if not isinstance(thread.get("metadata", {}), dict):
        raise ValueError("research_thread metadata must be an object")


def _validate_section_item(section: str, item: Any) -> None:
    if not isinstance(item, dict):
        raise ValueError(f"research_thread section item must be an object: {section}")
    for field in ("id", "text", "status", "created_at"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            raise ValueError(f"research_thread item field must be a non-empty string: {section}.{field}")
    if "source_refs" in item and not isinstance(item["source_refs"], list):
        raise ValueError(f"research_thread item source_refs must be a list: {section}.{item['id']}")
    if "tags" in item and not isinstance(item["tags"], list):
        raise ValueError(f"research_thread item tags must be a list: {section}.{item['id']}")
    if "metadata" in item and not isinstance(item["metadata"], dict):
        raise ValueError(f"research_thread item metadata must be an object: {section}.{item['id']}")
    for field in ("object_type", "object_ref", "authority_state", "review_state", "support_state"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            raise ValueError(f"research_thread item field must be a non-empty string: {section}.{field}")
    if "artifact_refs" in item and not isinstance(item["artifact_refs"], list):
        raise ValueError(f"research_thread item artifact_refs must be a list: {section}.{item['id']}")
    if "related_object_refs" in item and not isinstance(item["related_object_refs"], list):
        raise ValueError(f"research_thread item related_object_refs must be a list: {section}.{item['id']}")
    if "provenance" in item and not isinstance(item["provenance"], dict):
        raise ValueError(f"research_thread item provenance must be an object: {section}.{item['id']}")


def render_research_thread_markdown(thread: dict[str, Any]) -> str:
    thread = normalize_research_thread(thread)
    validate_research_thread(thread)
    lines = [
        f"# Research Thread: {thread['topic']}",
        "",
        f"- Thread ID: `{thread['thread_id']}`",
        f"- State: `{thread['research_state']}`",
        f"- Schema: `{thread['schema_version']}`",
        f"- Created: `{thread['created_at']}`",
        f"- Updated: `{thread['updated_at']}`",
        "",
        "This artifact is the human-readable ground truth for the research thread.",
        "It is not a status report, KG ingest result, RAG index, or Slack transcript.",
        "",
    ]

    for section in SECTION_NAMES:
        title = section.replace("_", " ").title()
        lines.extend([f"## {title}", ""])
        items = thread[section]
        if not items:
            lines.extend(["_None recorded yet._", ""])
            continue
        for item in items:
            lines.append(f"- `{item['id']}` [{item['status']}] {item['text']}")
            lines.append(f"  - Object ref: `{item['object_ref']}`")
            lines.append(
                "  - Authority: "
                f"{item['authority_state']} / Review: {item['review_state']} / Support: {item['support_state']}"
            )
            if item.get("source_refs"):
                lines.append(f"  - Source refs: {', '.join(item['source_refs'])}")
            if item.get("confidence"):
                lines.append(f"  - Confidence: {item['confidence']}")
            if item.get("tags"):
                lines.append(f"  - Tags: {', '.join(item['tags'])}")
            if item.get("artifact_refs"):
                lines.append(f"  - Artifact refs: {', '.join(item['artifact_refs'])}")
            if item.get("related_object_refs"):
                lines.append(f"  - Related object refs: {', '.join(item['related_object_refs'])}")
        lines.append("")

    lines.extend(["## Metadata", "", "```json", json.dumps(thread.get("metadata", {}), ensure_ascii=False, indent=2, sort_keys=True), "```", ""])
    return "\n".join(lines)


def write_research_thread(
    thread: dict[str, Any],
    *,
    artifacts_dir: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    thread = normalize_research_thread(thread)
    validate_research_thread(thread)
    paths = research_thread_paths(thread["thread_id"], artifacts_dir)
    if not overwrite and (paths.json_path.exists() or paths.markdown_path.exists()):
        return {
            "status": "exists",
            "thread_id": thread["thread_id"],
            "topic": thread["topic"],
            **paths.as_dict(),
        }

    paths.json_path.parent.mkdir(parents=True, exist_ok=True)
    paths.json_path.write_text(
        json.dumps(thread, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths.markdown_path.write_text(render_research_thread_markdown(thread), encoding="utf-8")
    return {
        "status": "created",
        "thread_id": thread["thread_id"],
        "topic": thread["topic"],
        **paths.as_dict(),
    }


def load_research_thread(thread_id: str, *, artifacts_dir: Path | None = None) -> dict[str, Any]:
    paths = research_thread_paths(thread_id, artifacts_dir)
    data = json.loads(paths.json_path.read_text(encoding="utf-8"))
    data = normalize_research_thread(data)
    validate_research_thread(data)
    return data


def list_research_threads(*, artifacts_dir: Path | None = None) -> list[dict[str, Any]]:
    base = research_threads_dir(artifacts_dir)
    if not base.exists():
        return []
    items = []
    for path in sorted(base.glob("*.json")):
        try:
            thread = json.loads(path.read_text(encoding="utf-8"))
            thread = normalize_research_thread(thread)
            validate_research_thread(thread)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        paths = research_thread_paths(thread["thread_id"], artifacts_dir)
        items.append({
            "thread_id": thread["thread_id"],
            "topic": thread["topic"],
            "research_state": thread["research_state"],
            "updated_at": thread["updated_at"],
            **paths.as_dict(),
        })
    return items


def build_seed_research_thread(topic: str, *, created_at: str | None = None) -> dict[str, Any]:
    if topic not in DEFAULT_SEED_TOPICS:
        valid = ", ".join(DEFAULT_SEED_TOPICS)
        raise ValueError(f"unsupported seed topic '{topic}'. Valid seed topics: {valid}")
    now = created_at or utc_now()
    next_actions = _seed_next_actions(topic, now)
    thread = {
        "schema_version": SCHEMA_VERSION,
        "thread_id": topic,
        "topic": topic,
        "research_state": "seeded",
        "created_at": now,
        "updated_at": now,
        "source_signals": [
            make_section_item(
                "ground_contract.phase1",
                "The CEML_RA ground contract names this topic as one of the first two research_thread proof-loop targets.",
                status="accepted",
                created_at=now,
                source_refs=[GROUND_CONTRACT_REF],
                confidence="contract",
                tags=["phase1", "seed"],
                authority_state="ground_contract",
                review_state="reviewed",
                support_state="contract",
            )
        ],
        "claims": [],
        "evidence": [],
        "counterarguments": [],
        "idea_candidates": [],
        "failure_modes": [],
        "decisions": [
            make_section_item(
                "decision.seed_first_proof_loop",
                "Seed this topic as part of the first CEML_RA proof loop so future Scout, RAG, KG, writing, and project work share one durable memory spine.",
                status="accepted",
                created_at=now,
                source_refs=[GROUND_CONTRACT_REF],
                confidence="contract",
                tags=["phase1", "memory-spine"],
                authority_state="ground_contract",
                review_state="reviewed",
                support_state="contract",
            )
        ],
        "next_actions": next_actions,
        "kg_ingest_preview": [
            make_section_item(
                "kg_preview.none_yet",
                "No KG ingest is proposed by this seed artifact. Future KG updates must start as preview records derived from evidence in this thread.",
                status="blocked_until_evidence",
                created_at=now,
                source_refs=[GROUND_CONTRACT_REF],
                confidence="contract",
                tags=["kg-preview", "no-live-mutation"],
                authority_state="ground_contract",
                review_state="reviewed",
                support_state="blocked_until_evidence",
            )
        ],
        "metadata": {
            "ground_contract": GROUND_CONTRACT_REF,
            "first_proof_loop": True,
            "seeded_by": "lab-orchestrator/tools/seed_research_threads.py",
            "contains_literature_claims": False,
            "authority_model": "research_thread_v2",
            "object_model": "section_items_with_object_refs",
            "live_store_mutations": [],
        },
    }
    validate_research_thread(thread)
    return thread


def _seed_next_actions(topic: str, created_at: str) -> list[dict[str, Any]]:
    if topic == "materials_ontology_kg":
        questions = (
            "Define the first useful materials-ontology KG question that would change a research decision, not just populate a graph.",
            "Identify which entity types, relations, and provenance fields are required to represent materials synthesis, properties, measurements, and claims.",
            "Find the smallest evidence set needed to compare ontology-guided KG memory against plain document RAG for materials research discussion.",
        )
    elif topic == "rare_earth_magnets":
        questions = (
            "Identify which rare-earth magnet bottleneck should be tracked first: supply risk, coercivity, temperature stability, recycling, or rare-earth reduction.",
            "List the evidence needed to separate speculative magnet ideas from candidates worth calculation, experiment, or proposal review.",
            "Define how this thread should connect composition, processing, microstructure, properties, and application constraints without premature KG ingest.",
        )
    else:
        raise ValueError(f"unsupported seed topic: {topic}")

    return [
        make_section_item(
            f"next_action.q{idx}",
            question,
            status="open",
            created_at=created_at,
            source_refs=[GROUND_CONTRACT_REF],
            confidence="research_question",
            tags=["phase1", "research-question"],
            authority_state="ground_contract",
            review_state="reviewed",
            support_state="research_question",
        )
        for idx, question in enumerate(questions, start=1)
    ]


def seed_research_threads(
    *,
    artifacts_dir: Path | None = None,
    execute: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    resolved_artifacts = resolve_artifacts_dir(artifacts_dir)
    results = []
    for topic in DEFAULT_SEED_TOPICS:
        thread = build_seed_research_thread(topic, created_at=created_at)
        paths = research_thread_paths(topic, resolved_artifacts)
        exists = paths.json_path.exists() or paths.markdown_path.exists()
        if execute:
            result = write_research_thread(thread, artifacts_dir=resolved_artifacts)
        else:
            result = {
                "status": "exists" if exists else "would_create",
                "thread_id": thread["thread_id"],
                "topic": thread["topic"],
                **paths.as_dict(),
                "thread": thread,
            }
        results.append(result)
    return {
        "schema_version": SCHEMA_VERSION,
        "dry_run": not execute,
        "artifacts_dir": str(resolved_artifacts),
        "threads": results,
    }


def _normalize_section_item(section: str, item: Any, *, legacy: bool) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"research_thread section item must be an object: {section}")
    normalized = copy.deepcopy(item)
    item_id = normalized.get("id")
    status = normalized.get("status", "")
    confidence = normalized.get("confidence")
    source_refs = normalized.get("source_refs", [])
    if not isinstance(source_refs, list):
        source_refs = []

    normalized.setdefault("object_type", SECTION_OBJECT_TYPES.get(section, section))
    if isinstance(item_id, str) and item_id.strip():
        normalized.setdefault("object_ref", f"{section}:{item_id}")
    else:
        normalized.setdefault("object_ref", "")
    normalized.setdefault("authority_state", _default_authority_state(normalized))
    normalized.setdefault("review_state", _default_review_state(status))
    normalized.setdefault("support_state", confidence or _default_support_state(section, normalized))
    normalized.setdefault("artifact_refs", [])
    normalized.setdefault("related_object_refs", [])

    provenance = normalized.get("provenance", {})
    if not isinstance(provenance, dict):
        provenance = {}
    provenance.setdefault("source_refs", list(source_refs))
    if legacy:
        provenance.setdefault("schema_upgrade", "v1_to_v2_compatible_loader")
    normalized["provenance"] = provenance
    return normalized


def _infer_object_type(item_id: str) -> str:
    prefix = item_id.split(".", 1)[0]
    return prefix or "research_object"


def _object_ref_from_item_id(item_id: str) -> str:
    object_type = _infer_object_type(item_id)
    return f"{object_type}:{item_id}"


def _default_authority_state(item: dict[str, Any]) -> str:
    if item.get("confidence") == "contract":
        return "ground_contract"
    if item.get("status") in {"accepted", "completed"}:
        return "reviewed_artifact"
    return "thread_local"


def _default_review_state(status: Any) -> str:
    if status in {"accepted", "completed"}:
        return "reviewed"
    if isinstance(status, str) and status.startswith("blocked"):
        return "blocked"
    return "pending_review"


def _default_support_state(section: str, item: dict[str, Any]) -> str:
    if section == "kg_ingest_preview" and str(item.get("status", "")).startswith("blocked"):
        return "blocked_until_evidence"
    if section in {"next_actions", "idea_candidates"}:
        return "needs_evidence"
    return "not_evaluated"
