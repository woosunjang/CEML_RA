"""Review records for research_thread patch approval decisions.

This module only writes durable local artifact review records. It never touches
Slack, runtime services, Scout DB, Qdrant, Neo4j, Graphiti, KG, or RAG stores.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.research_thread import resolve_artifacts_dir, utc_now
from orchestrator.research_thread_patch import preview_or_apply_research_thread_patch


REVIEW_SCHEMA_VERSION = 1
PATCH_REVIEWS_DIR = "research_patch_reviews"
SUPPORTED_ACTIONS = ("preview", "apply", "reject")


@dataclass(frozen=True)
class ResearchPatchReviewPaths:
    json_path: Path

    def as_dict(self) -> dict[str, str]:
        return {"review_record_path": str(self.json_path)}


def research_patch_reviews_dir(artifacts_dir: Path | None = None) -> Path:
    return resolve_artifacts_dir(artifacts_dir) / PATCH_REVIEWS_DIR


def patch_hash(patch: dict[str, Any]) -> str:
    canonical = json.dumps(patch, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def process_research_patch_review(
    *,
    thread_id: str,
    patch: dict[str, Any],
    action: str,
    reviewer: str | None = None,
    review_note: str | None = None,
    confirm_artifact_write: bool = False,
    artifacts_dir: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if action not in SUPPORTED_ACTIONS:
        raise ValueError(f"unsupported patch review action: {action}")
    if action in {"apply", "reject"} and not confirm_artifact_write:
        raise PermissionError("confirm_artifact_write=true is required for apply/reject")
    if not isinstance(patch, dict):
        raise ValueError("patch must be an object")

    created_at = created_at or utc_now()
    dry_run = action == "preview"
    execute_patch = action == "apply"
    patch_result = preview_or_apply_research_thread_patch(
        thread_id=thread_id,
        patch=patch,
        artifacts_dir=artifacts_dir,
        execute=execute_patch,
        created_at=created_at,
    )
    if patch_result.get("status") == "missing_thread":
        raise FileNotFoundError(f"research_thread not found: {thread_id}")

    result_status = "rejected" if action == "reject" else str(patch_result["status"])
    artifact_mutations = _artifact_mutations(action=action, patch_result=patch_result)
    record = build_patch_review_record(
        thread_id=thread_id,
        patch=patch,
        action=action,
        patch_result=patch_result,
        result_status=result_status,
        reviewer=reviewer,
        review_note=review_note,
        artifact_mutations=artifact_mutations,
        created_at=created_at,
    )

    review_record_path = None
    if not dry_run:
        paths = _review_paths(thread_id=thread_id, action=action, patch_hash_value=record["patch_hash"], created_at=created_at, artifacts_dir=artifacts_dir)
        paths.json_path.parent.mkdir(parents=True, exist_ok=True)
        paths.json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        review_record_path = str(paths.json_path)
        artifact_mutations = [*artifact_mutations, {"type": "patch_review_record", "path": review_record_path}]
        record["artifact_mutations"] = artifact_mutations

    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "status": "previewed" if action == "preview" else "applied" if action == "apply" else "rejected",
        "dry_run": dry_run,
        "read_only": dry_run,
        "artifact_write": not dry_run,
        "thread_id": thread_id,
        "action": action,
        "patch_hash": record["patch_hash"],
        "patch_result": patch_result,
        "review_record": record,
        "review_record_path": review_record_path,
        "artifact_mutations": artifact_mutations,
        "live_store_mutations": [],
    }


def build_patch_review_record(
    *,
    thread_id: str,
    patch: dict[str, Any],
    action: str,
    patch_result: dict[str, Any],
    result_status: str,
    reviewer: str | None,
    review_note: str | None,
    artifact_mutations: list[dict[str, str]],
    created_at: str,
) -> dict[str, Any]:
    patch_hash_value = patch_hash(patch)
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "review_id": _review_id(thread_id=thread_id, action=action, patch_hash_value=patch_hash_value, created_at=created_at),
        "thread_id": thread_id,
        "action": action,
        "patch_hash": patch_hash_value,
        "reviewer": _clean_optional_text(reviewer) or "local_reviewer",
        "review_note": _clean_optional_text(review_note) or "",
        "patch": patch,
        "result_status": result_status,
        "created_at": created_at,
        "artifact_mutations": artifact_mutations,
        "patch_result_status": patch_result.get("status"),
        "live_store_mutations": [],
    }


def _artifact_mutations(*, action: str, patch_result: dict[str, Any]) -> list[dict[str, str]]:
    if action != "apply" or "write" not in patch_result:
        return []
    write = patch_result.get("write", {})
    mutations = []
    for key, mutation_type in (("json_path", "research_thread_json"), ("markdown_path", "research_thread_markdown")):
        path = write.get(key)
        if isinstance(path, str) and path:
            mutations.append({"type": mutation_type, "path": path})
    return mutations


def _review_paths(
    *,
    thread_id: str,
    action: str,
    patch_hash_value: str,
    created_at: str,
    artifacts_dir: Path | None,
) -> ResearchPatchReviewPaths:
    digest = patch_hash_value.split(":", 1)[-1][:12]
    stem = _safe_filename(f"{thread_id}_{_timestamp_for_path(created_at)}_{action}_{digest}")
    return ResearchPatchReviewPaths(json_path=research_patch_reviews_dir(artifacts_dir) / f"{stem}.json")


def _review_id(*, thread_id: str, action: str, patch_hash_value: str, created_at: str) -> str:
    digest = patch_hash_value.split(":", 1)[-1][:12]
    return f"research_patch_review.{_safe_filename(thread_id)}.{_timestamp_for_path(created_at)}.{action}.{digest}"


def _timestamp_for_path(value: str) -> str:
    return value.replace(":", "").replace("-", "").replace(".", "").replace("Z", "Z")


def _safe_filename(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("._") or "research_patch_review"


def _clean_optional_text(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""
