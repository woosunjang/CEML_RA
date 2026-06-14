"""Small reviewable patch layer for durable research_thread artifacts.

This module updates local JSON/Markdown artifacts only. It does not touch
Slack, runtime services, Scout DB, Qdrant, Neo4j, Graphiti, KG, or RAG stores.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from orchestrator.research_thread import (
    SECTION_NAMES,
    load_research_thread,
    make_section_item,
    normalize_research_thread,
    render_research_thread_markdown,
    research_thread_paths,
    utc_now,
    validate_research_thread,
    write_research_thread,
)


PATCH_SCHEMA_VERSION = 2
SUPPORTED_PATCH_SCHEMA_VERSIONS = (1, 2)
PATCHABLE_SECTIONS_V1 = ("decisions", "next_actions", "failure_modes")
PATCHABLE_SECTIONS = SECTION_NAMES
THREAD_METADATA_KEY = "metadata"


def load_patch_file(path: Path) -> dict[str, Any]:
    try:
        patch = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"patch file is not valid JSON: {path}") from exc
    if not isinstance(patch, dict):
        raise ValueError("research_thread patch must be a JSON object")
    return patch


def preview_or_apply_research_thread_patch(
    *,
    thread_id: str,
    patch: dict[str, Any],
    artifacts_dir: Path | None = None,
    execute: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    created_at = created_at or utc_now()
    paths = research_thread_paths(thread_id, artifacts_dir)
    if not paths.json_path.exists():
        return {
            "status": "missing_thread",
            "dry_run": not execute,
            "thread_id": thread_id,
            **paths.as_dict(),
            "error": "research_thread JSON does not exist",
            "live_store_mutations": [],
        }

    original = load_research_thread(thread_id, artifacts_dir=artifacts_dir)
    updated, changes = apply_research_thread_patch(original, patch, created_at=created_at)
    changed = updated != original
    status = "updated" if execute and changed else "would_update" if changed else "no_changes"

    result = {
        "schema_version": PATCH_SCHEMA_VERSION,
        "status": status,
        "dry_run": not execute,
        "thread_id": thread_id,
        **paths.as_dict(),
        "changes": changes,
        "preview_markdown": render_research_thread_markdown(updated),
        "live_store_mutations": [],
    }
    if execute and changed:
        result["write"] = write_research_thread(updated, artifacts_dir=artifacts_dir, overwrite=True)
    return result


def apply_research_thread_patch(
    thread: dict[str, Any],
    patch: dict[str, Any],
    *,
    created_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    thread = normalize_research_thread(thread)
    validate_research_thread(thread)
    _validate_patch_shape(thread["thread_id"], patch)
    now = created_at or utc_now()
    updated = copy.deepcopy(thread)
    changes: dict[str, Any] = {
        "research_state": None,
        "appended": {section: 0 for section in PATCHABLE_SECTIONS},
        "updated": {section: 0 for section in PATCHABLE_SECTIONS},
        "metadata_keys": [],
    }

    if "research_state" in patch and patch["research_state"] != updated["research_state"]:
        changes["research_state"] = {
            "from": updated["research_state"],
            "to": patch["research_state"],
        }
        updated["research_state"] = patch["research_state"]

    for section, raw_items in patch.get("append", {}).items():
        existing_ids = _section_ids(updated, section)
        seen_ids: set[str] = set()
        for raw_item in raw_items:
            item = _coerce_append_item(raw_item, created_at=now)
            item_id = item["id"]
            if item_id in existing_ids:
                raise ValueError(f"cannot append duplicate item id: {section}.{item_id}")
            if item_id in seen_ids:
                raise ValueError(f"cannot append duplicate item id within patch: {section}.{item_id}")
            seen_ids.add(item_id)
            updated[section].append(item)
            changes["appended"][section] += 1

    for section, raw_items in patch.get("updates", {}).items():
        by_id = {item["id"]: item for item in updated[section]}
        for raw_item in raw_items:
            item_id = _required_nonempty_string(raw_item, "id", f"updates.{section}")
            if item_id not in by_id:
                raise ValueError(f"cannot update missing item id: {section}.{item_id}")
            target = by_id[item_id]
            changed = False
            for text_field in (
                "text",
                "status",
                "authority_state",
                "review_state",
                "support_state",
            ):
                if text_field in raw_item and raw_item[text_field] != target.get(text_field):
                    target[text_field] = _required_nonempty_string(
                        raw_item,
                        text_field,
                        f"updates.{section}.{item_id}",
                    )
                    changed = True
            for list_field in ("source_refs", "tags", "artifact_refs", "related_object_refs"):
                if list_field in raw_item:
                    values = _optional_string_list(raw_item[list_field], f"updates.{section}.{item_id}.{list_field}")
                    if values != target.get(list_field):
                        target[list_field] = values
                        changed = True
            if "metadata" in raw_item:
                metadata = raw_item["metadata"]
                if not isinstance(metadata, dict):
                    raise ValueError(f"updates.{section}.{item_id}.metadata must be an object")
                merged = dict(target.get("metadata", {}))
                merged.update(metadata)
                if merged != target.get("metadata", {}):
                    target["metadata"] = merged
                    changed = True
            if "provenance" in raw_item:
                provenance = raw_item["provenance"]
                if not isinstance(provenance, dict):
                    raise ValueError(f"updates.{section}.{item_id}.provenance must be an object")
                merged_provenance = dict(target.get("provenance", {}))
                merged_provenance.update(provenance)
                if merged_provenance != target.get("provenance", {}):
                    target["provenance"] = merged_provenance
                    changed = True
            if changed:
                changes["updated"][section] += 1

    if THREAD_METADATA_KEY in patch:
        metadata_patch = patch[THREAD_METADATA_KEY]
        if not isinstance(metadata_patch, dict):
            raise ValueError("metadata must be an object")
        metadata = dict(updated.get("metadata", {}))
        for key, value in metadata_patch.items():
            if metadata.get(key) != value:
                metadata[key] = value
                changes["metadata_keys"].append(key)
        updated["metadata"] = metadata

    if _has_changes(changes):
        updated["updated_at"] = now

    validate_research_thread(updated)
    return updated, changes


def _validate_patch_shape(thread_id: str, patch: dict[str, Any]) -> None:
    schema_version = patch.get("schema_version", PATCH_SCHEMA_VERSION)
    if schema_version not in SUPPORTED_PATCH_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported research_thread patch schema_version: {schema_version}")
    if "thread_id" in patch and patch["thread_id"] != thread_id:
        raise ValueError(f"patch thread_id does not match target thread: {patch['thread_id']} != {thread_id}")
    if "research_state" in patch:
        _required_nonempty_string(patch, "research_state", "patch")
    patchable_sections = _patchable_sections_for_schema(schema_version)
    for key in ("append", "updates"):
        value = patch.get(key, {})
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be an object")
        for section, items in value.items():
            if section not in patchable_sections:
                valid = ", ".join(patchable_sections)
                raise ValueError(f"unsupported patch section: {section}. Valid sections: {valid}")
            if not isinstance(items, list):
                raise ValueError(f"{key}.{section} must be a list")
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    raise ValueError(f"{key}.{section}[{idx}] must be an object")
    if THREAD_METADATA_KEY in patch and not isinstance(patch[THREAD_METADATA_KEY], dict):
        raise ValueError("metadata must be an object")


def _coerce_append_item(raw_item: dict[str, Any], *, created_at: str) -> dict[str, Any]:
    item_id = _required_nonempty_string(raw_item, "id", "append item")
    text = _required_nonempty_string(raw_item, "text", f"append item {item_id}")
    status = raw_item.get("status", "open")
    if not isinstance(status, str) or not status.strip():
        raise ValueError(f"append item status must be a non-empty string: {item_id}")
    item = make_section_item(
        item_id,
        text,
        status=status,
        created_at=raw_item.get("created_at") or created_at,
        source_refs=raw_item.get("source_refs"),
        confidence=raw_item.get("confidence"),
        tags=raw_item.get("tags"),
        metadata=raw_item.get("metadata"),
        object_type=raw_item.get("object_type"),
        object_ref=raw_item.get("object_ref"),
        authority_state=raw_item.get("authority_state"),
        review_state=raw_item.get("review_state"),
        support_state=raw_item.get("support_state"),
        artifact_refs=raw_item.get("artifact_refs"),
        related_object_refs=raw_item.get("related_object_refs"),
        provenance=raw_item.get("provenance"),
    )
    return item


def _required_nonempty_string(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def _section_ids(thread: dict[str, Any], section: str) -> set[str]:
    return {str(item.get("id")) for item in thread.get(section, [])}


def _patchable_sections_for_schema(schema_version: int) -> tuple[str, ...]:
    if schema_version == 1:
        return PATCHABLE_SECTIONS_V1
    return PATCHABLE_SECTIONS


def _optional_string_list(value: Any, context: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a list")
    result = []
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{context}[{idx}] must be a non-empty string")
        result.append(item)
    return result


def _has_changes(changes: dict[str, Any]) -> bool:
    return bool(
        changes["research_state"]
        or any(changes["appended"].values())
        or any(changes["updated"].values())
        or changes["metadata_keys"]
    )
