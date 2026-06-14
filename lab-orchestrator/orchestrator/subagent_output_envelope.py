"""Reviewable subagent output envelopes for CEML_RA research loops.

This module converts a Research Loop Packet plus explicitly supplied subagent
summary text into a shared return shape. It does not execute subagents, call
LLMs, create research claims, mutate research_thread artifacts, or touch live
Slack/Scout/KG/RAG/runtime stores.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from orchestrator.research_loop_packet import CONTRACT_REF, SUBAGENT_ROLE_CATALOG
from orchestrator.research_thread import resolve_artifacts_dir, utc_now


LOOP_PACKET_SCHEMA_VERSION = 1
ENVELOPE_SCHEMA_VERSION = 2
SCHEMA_VERSION = ENVELOPE_SCHEMA_VERSION
ENVELOPE_PLANNER_NAME = "subagent_output_envelope_v2"
SUBAGENT_OUTPUT_ENVELOPES_DIR = "subagent_output_envelopes"

ROLE_OUTPUT_TYPES: dict[str, tuple[str, ...]] = {
    "Scout": ("source_signal_preview", "candidate_source_preview"),
    "Literature/RAG": ("evidence_preview", "retrieval_summary_preview"),
    "KG Memory": ("kg_ingest_preview",),
    "Evidence Critic": ("evidence_boundary_preview", "counterargument_review"),
    "Writing": ("korean_first_draft_preview", "response_context_plan", "artifact_draft_preview"),
    "Project": ("next_action_plan", "loop_review_note", "stop_condition_review"),
}


@dataclass(frozen=True)
class SubagentOutputEnvelopePaths:
    json_path: Path
    markdown_path: Path
    patch_preview_path: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "json_path": str(self.json_path),
            "markdown_path": str(self.markdown_path),
            "patch_preview_path": str(self.patch_preview_path),
        }


def subagent_output_envelopes_dir(artifacts_dir: Path | None = None) -> Path:
    return resolve_artifacts_dir(artifacts_dir) / SUBAGENT_OUTPUT_ENVELOPES_DIR


def subagent_output_envelope_paths(
    *,
    thread_id: str,
    envelope_id: str,
    artifacts_dir: Path | None = None,
) -> SubagentOutputEnvelopePaths:
    base = subagent_output_envelopes_dir(artifacts_dir)
    stem = f"{thread_id}_{envelope_id}"
    return SubagentOutputEnvelopePaths(
        json_path=base / f"{stem}.json",
        markdown_path=base / f"{stem}.md",
        patch_preview_path=base / f"{stem}_thread_patch_preview.json",
    )


def load_loop_packet(path: Path) -> dict[str, Any]:
    try:
        packet = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"loop packet is not valid JSON: {path}") from exc
    validate_loop_packet(packet)
    return packet


def validate_loop_packet(packet: dict[str, Any]) -> None:
    if not isinstance(packet, dict):
        raise ValueError("loop packet must be a JSON object")
    required = (
        "schema_version",
        "packet_id",
        "thread_id",
        "topic",
        "research_state",
        "trigger",
        "selected_roles",
        "expected_outputs",
        "artifact_candidates",
        "thread_patch_preview",
        "live_store_mutations",
    )
    missing = [field for field in required if field not in packet]
    if missing:
        raise ValueError(f"loop packet missing required fields: {', '.join(missing)}")
    if packet["schema_version"] != LOOP_PACKET_SCHEMA_VERSION:
        raise ValueError(f"unsupported loop packet schema_version: {packet['schema_version']}")
    for field in ("packet_id", "thread_id", "topic", "research_state"):
        _required_nonempty_string(packet, field, "loop packet")
    if not isinstance(packet["trigger"], dict):
        raise ValueError("loop packet trigger must be an object")
    if not isinstance(packet["selected_roles"], list):
        raise ValueError("loop packet selected_roles must be a list")
    if not packet["selected_roles"]:
        raise ValueError("loop packet selected_roles must not be empty")
    for idx, role in enumerate(packet["selected_roles"]):
        if not isinstance(role, dict):
            raise ValueError(f"loop packet selected_roles[{idx}] must be an object")
        _required_nonempty_string(role, "role", f"loop packet selected_roles[{idx}]")
    for field in ("expected_outputs", "artifact_candidates", "live_store_mutations"):
        if not isinstance(packet[field], list):
            raise ValueError(f"loop packet {field} must be a list")
    if packet["live_store_mutations"]:
        raise ValueError("loop packet has live_store_mutations; envelope v1 only accepts no-mutation packets")
    if not isinstance(packet["thread_patch_preview"], dict):
        raise ValueError("loop packet thread_patch_preview must be an object")


def build_subagent_output_envelope(
    *,
    loop_packet: dict[str, Any],
    role: str,
    output_type: str,
    summary: str,
    loop_packet_ref: str,
    missing_evidence: Iterable[str] | None = None,
    counterarguments: Iterable[str] | None = None,
    failure_modes: Iterable[str] | None = None,
    artifact_candidates: Iterable[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    validate_loop_packet(loop_packet)
    selected_role = _selected_role(loop_packet, role)
    output_type = _validate_output_type(role, output_type)
    summary = _clean_text(summary, "summary")
    generated_at = created_at or utc_now()
    packet_id = loop_packet["packet_id"]
    thread_id = loop_packet["thread_id"]
    envelope_id = build_envelope_id(
        loop_packet_id=packet_id,
        role=role,
        output_type=output_type,
        summary=summary,
    )
    normalized_missing = _normalize_text_items(missing_evidence)
    normalized_counterarguments = _normalize_text_items(counterarguments)
    normalized_failure_modes = _normalize_text_items(failure_modes)
    normalized_artifacts = _normalize_text_items(artifact_candidates)
    thread_patch_preview = build_thread_patch_preview(
        thread_id=thread_id,
        envelope_id=envelope_id,
        role=role,
        output_type=output_type,
        summary=summary,
        missing_evidence=normalized_missing,
        counterarguments=normalized_counterarguments,
        failure_modes=normalized_failure_modes,
        artifact_candidates=normalized_artifacts,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "planner": ENVELOPE_PLANNER_NAME,
        "generated_at": generated_at,
        "envelope_id": envelope_id,
        "loop_packet_id": packet_id,
        "thread_id": thread_id,
        "topic": loop_packet["topic"],
        "research_state": loop_packet["research_state"],
        "role": role,
        "role_contract": selected_role,
        "output_type": output_type,
        "summary": summary,
        "input_refs": {
            "loop_packet": loop_packet_ref,
            "research_thread": thread_id,
            "contract": CONTRACT_REF,
        },
        "source_boundary": {
            "kind": "explicit_input_only",
            "text": (
                "이 envelope는 loop packet과 CLI로 명시 입력된 요약/검토 항목만 재구성한다. "
                "새 문헌 claim, 수치, citation, 실험 결과를 생성하지 않는다."
            ),
        },
        "context_bundle": loop_packet.get("context_bundle", {}),
        "evidence_boundaries": build_evidence_boundaries(role=role, output_type=output_type),
        "missing_evidence": _review_items(normalized_missing, default="명시 입력된 missing evidence 없음"),
        "counterarguments": _review_items(normalized_counterarguments, default="명시 입력된 counterargument 없음"),
        "failure_modes": _review_items(
            normalized_failure_modes,
            default="이 envelope를 근거 확정 또는 live store 변경으로 오해하면 실패한다.",
        ),
        "artifact_candidates": _review_items(normalized_artifacts, default="명시 입력된 artifact 후보 없음"),
        "loop_packet_artifact_candidates": loop_packet.get("artifact_candidates", []),
        "critique_gate": build_critique_gate(
            role=role,
            output_type=output_type,
            missing_evidence=normalized_missing,
            counterarguments=normalized_counterarguments,
            failure_modes=normalized_failure_modes,
        ),
        "artifact_co_production": build_artifact_co_production(
            role=role,
            output_type=output_type,
            artifact_candidates=normalized_artifacts,
            loop_packet_artifact_candidates=loop_packet.get("artifact_candidates", []),
        ),
        "recommended_thread_patch": thread_patch_preview,
        "stop_conditions": build_stop_conditions(role=role),
        "live_store_mutations": [],
    }


def preview_or_write_subagent_output_envelope(
    *,
    loop_packet_path: Path,
    role: str,
    output_type: str,
    summary: str,
    artifacts_dir: Path | None = None,
    execute: bool = False,
    missing_evidence: Iterable[str] | None = None,
    counterarguments: Iterable[str] | None = None,
    failure_modes: Iterable[str] | None = None,
    artifact_candidates: Iterable[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    loop_packet_path = loop_packet_path.expanduser().resolve()
    loop_packet = load_loop_packet(loop_packet_path)
    envelope = build_subagent_output_envelope(
        loop_packet=loop_packet,
        role=role,
        output_type=output_type,
        summary=summary,
        loop_packet_ref=str(loop_packet_path),
        missing_evidence=missing_evidence,
        counterarguments=counterarguments,
        failure_modes=failure_modes,
        artifact_candidates=artifact_candidates,
        created_at=created_at,
    )
    paths = subagent_output_envelope_paths(
        thread_id=envelope["thread_id"],
        envelope_id=envelope["envelope_id"],
        artifacts_dir=artifacts_dir,
    )
    markdown = render_subagent_output_envelope_markdown(envelope)
    exists = paths.json_path.exists() or paths.markdown_path.exists() or paths.patch_preview_path.exists()
    status = "exists" if execute and exists else "written" if execute else "would_write"
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "dry_run": not execute,
        "thread_id": envelope["thread_id"],
        "loop_packet_id": envelope["loop_packet_id"],
        "envelope_id": envelope["envelope_id"],
        **paths.as_dict(),
        "envelope": envelope,
        "preview_markdown": markdown,
        "live_store_mutations": [],
    }
    if execute and not exists:
        paths.json_path.parent.mkdir(parents=True, exist_ok=True)
        paths.json_path.write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths.markdown_path.write_text(markdown, encoding="utf-8")
        paths.patch_preview_path.write_text(
            json.dumps(envelope["recommended_thread_patch"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result


def build_envelope_id(*, loop_packet_id: str, role: str, output_type: str, summary: str) -> str:
    role_slug = _slug(role)
    output_slug = _slug(output_type)
    digest = hashlib.sha1(f"{loop_packet_id}:{role}:{output_type}:{summary}".encode("utf-8")).hexdigest()[:10]
    return f"{role_slug}_{output_slug}_{digest}"


def build_evidence_boundaries(*, role: str, output_type: str) -> list[dict[str, str]]:
    boundaries = [
        {
            "id": "boundary.explicit_input_only",
            "text": "명시 입력된 요약과 검토 항목만 사용한다.",
            "status": "active",
        },
        {
            "id": "boundary.no_claim_creation",
            "text": "새 문헌 claim, 수치, citation, 실험 결과를 생성하지 않는다.",
            "status": "active",
        },
    ]
    if role in ("Literature/RAG", "Evidence Critic") or output_type in ("evidence_preview", "evidence_boundary_preview"):
        boundaries.append({
            "id": "boundary.preview_not_confirmed_claim",
            "text": "evidence preview는 확정 claim이 아니라 Coordinator 검토용 경계 정보다.",
            "status": "active",
        })
    if role == "KG Memory" or output_type == "kg_ingest_preview":
        boundaries.append({
            "id": "boundary.kg_preview_only",
            "text": "KG 관련 출력은 ingest 후보 preview일 뿐 Neo4j/Graphiti를 변경하지 않는다.",
            "status": "active",
        })
    if role == "Writing":
        boundaries.append({
            "id": "boundary.korean_first_user_artifact",
            "text": "사용자가 읽는 초안과 설명 문장은 한국어 우선으로 작성한다.",
            "status": "active",
        })
    return boundaries


def build_stop_conditions(*, role: str) -> list[str]:
    conditions = [
        "새 연구 claim, 수치, citation을 추정해야 하면 envelope 생성을 멈춘다.",
        "research_thread를 직접 변경해야 하면 recommended_thread_patch만 남기고 멈춘다.",
        "Slack, runtime service, Scout DB, Qdrant, Neo4j, Graphiti, KG/RAG store 변경이 필요하면 멈춘다.",
        "사용자에게 보일 Markdown 또는 설명 문장을 한국어 중심으로 유지할 수 없으면 멈춘다.",
    ]
    if role == "Scout":
        conditions.append("Scout DB read/write가 필요하면 이 envelope v1 범위를 넘으므로 멈춘다.")
    if role == "KG Memory":
        conditions.append("KG ingest 실행이 필요하면 preview만 남기고 멈춘다.")
    return conditions


def build_critique_gate(
    *,
    role: str,
    output_type: str,
    missing_evidence: list[str],
    counterarguments: list[str],
    failure_modes: list[str],
) -> dict[str, Any]:
    findings = []
    if missing_evidence:
        findings.append({
            "id": "critique.missing_evidence",
            "status": "requires_review",
            "text": "명시된 missing evidence가 해소되기 전에는 claim 승격을 금지한다.",
        })
    if counterarguments:
        findings.append({
            "id": "critique.counterarguments_present",
            "status": "requires_review",
            "text": "반론이 남아 있으므로 artifact나 KG fact 승격 전에 Coordinator 검토가 필요하다.",
        })
    if failure_modes:
        findings.append({
            "id": "critique.failure_modes_present",
            "status": "requires_review",
            "text": "실패 모드가 남아 있으므로 next action 또는 stop condition으로 되돌려야 한다.",
        })
    if role != "Evidence Critic" and output_type not in {"evidence_boundary_preview", "counterargument_review"}:
        findings.append({
            "id": "critique.evidence_critic_required",
            "status": "required_before_promotion",
            "text": "이 envelope 출력은 Evidence Critic 검토 없이 확정 기억으로 승격될 수 없다.",
        })
    status = "requires_review" if findings else "preview_passed"
    return {
        "status": status,
        "role": role,
        "output_type": output_type,
        "findings": findings,
        "allows_thread_mutation": False,
        "allows_kg_ingest": False,
        "live_store_mutations": [],
    }


def build_artifact_co_production(
    *,
    role: str,
    output_type: str,
    artifact_candidates: list[str],
    loop_packet_artifact_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates = [
        {
            "id": f"artifact.explicit.{idx}",
            "text": item,
            "status": "candidate",
            "source": "explicit_input",
        }
        for idx, item in enumerate(artifact_candidates, start=1)
    ]
    for idx, item in enumerate(loop_packet_artifact_candidates, start=1):
        candidates.append({
            "id": f"artifact.loop_packet.{idx}",
            "text": item.get("purpose", item.get("artifact_type", "artifact candidate")),
            "status": "candidate",
            "source": "loop_packet",
            "artifact_type": item.get("artifact_type"),
        })
    return {
        "status": "preview_only",
        "role": role,
        "output_type": output_type,
        "candidates": candidates,
        "requires_thread_patch_preview": True,
        "live_store_mutations": [],
    }


def build_thread_patch_preview(
    *,
    thread_id: str,
    envelope_id: str,
    role: str,
    output_type: str,
    summary: str,
    missing_evidence: list[str],
    counterarguments: list[str],
    failure_modes: list[str],
    artifact_candidates: list[str],
) -> dict[str, Any]:
    append: dict[str, list[dict[str, Any]]] = {
        "decisions": [
            {
                "id": f"decision.subagent_output_envelope.{envelope_id}",
                "text": (
                    f"`{role}` 역할의 `{output_type}` 결과를 Subagent Output Envelope v2 형태로 "
                    "Coordinator에 반환할 수 있게 되었다. 이 결정은 새 연구 내용을 확정하지 않고 "
                    "역할 출력, 근거 경계, critique gate, patch preview를 같은 research_thread 흐름에 연결하기 위한 것이다."
                ),
                "status": "proposed",
                "confidence": ENVELOPE_PLANNER_NAME,
                "source_refs": [CONTRACT_REF],
                "tags": ["subagent-output-envelope", "research-loop", _slug(role)],
                "review_state": "pending_review",
                "support_state": "coordination_boundary",
                "metadata": {
                    "envelope_id": envelope_id,
                    "role": role,
                    "output_type": output_type,
                    "live_store_mutations": [],
                },
            }
        ],
        "failure_modes": [
            {
                "id": f"failure_mode.subagent_output_envelope.{envelope_id}.overclaiming",
                "text": "Subagent output envelope가 입력 summary를 확정 evidence나 새 research claim처럼 포장하면 실패한다.",
                "status": "open",
                "confidence": ENVELOPE_PLANNER_NAME,
                "source_refs": [CONTRACT_REF],
                "tags": ["subagent-output-envelope", "anti-overclaim"],
                "review_state": "pending_review",
                "support_state": "risk_boundary",
                "metadata": {
                    "envelope_id": envelope_id,
                    "missing_evidence": missing_evidence,
                    "counterarguments": counterarguments,
                    "failure_modes": failure_modes,
                    "live_store_mutations": [],
                },
            }
        ],
        "next_actions": [
            {
                "id": f"next_action.subagent_output_envelope.{envelope_id}.coordinator_review",
                "text": (
                    f"Coordinator가 `{role}` envelope를 검토해 실제 thread patch 적용, durable artifact 작성, "
                    "또는 stop condition 중 하나로 다음 단계를 결정한다."
                ),
                "status": "open",
                "confidence": ENVELOPE_PLANNER_NAME,
                "source_refs": [CONTRACT_REF],
                "tags": ["subagent-output-envelope", "coordinator-review"],
                "review_state": "pending_review",
                "support_state": "next_action",
                "metadata": {
                    "envelope_id": envelope_id,
                    "summary": summary,
                    "artifact_candidates": artifact_candidates,
                    "live_store_mutations": [],
                },
            }
        ],
    }
    if counterarguments:
        append["counterarguments"] = [
            {
                "id": f"counterargument.subagent_output_envelope.{envelope_id}.{idx}",
                "text": item,
                "status": "open",
                "confidence": ENVELOPE_PLANNER_NAME,
                "source_refs": [CONTRACT_REF],
                "tags": ["subagent-output-envelope", "critique-gate"],
                "review_state": "pending_review",
                "support_state": "needs_evidence",
                "metadata": {"envelope_id": envelope_id, "live_store_mutations": []},
            }
            for idx, item in enumerate(counterarguments, start=1)
        ]
    if missing_evidence:
        append["failure_modes"].extend([
            {
                "id": f"failure_mode.subagent_output_envelope.{envelope_id}.missing_evidence.{idx}",
                "text": item,
                "status": "open",
                "confidence": ENVELOPE_PLANNER_NAME,
                "source_refs": [CONTRACT_REF],
                "tags": ["subagent-output-envelope", "missing-evidence"],
                "review_state": "pending_review",
                "support_state": "needs_evidence",
                "metadata": {"envelope_id": envelope_id, "live_store_mutations": []},
            }
            for idx, item in enumerate(missing_evidence, start=1)
        ])
    return {
        "schema_version": 2,
        "thread_id": thread_id,
        "research_state": "subagent_output_envelope_planned",
        "append": append,
        "metadata": {
            "last_subagent_output_envelope": {
                "envelope_id": envelope_id,
                "role": role,
                "output_type": output_type,
                "live_store_mutations": [],
            }
        },
    }


def render_subagent_output_envelope_markdown(envelope: dict[str, Any]) -> str:
    lines = [
        f"# Subagent Output Envelope: {envelope['role']}",
        "",
        f"- Envelope ID: `{envelope['envelope_id']}`",
        f"- Loop Packet ID: `{envelope['loop_packet_id']}`",
        f"- Thread ID: `{envelope['thread_id']}`",
        f"- Output type: `{envelope['output_type']}`",
        f"- 생성 시각: `{envelope['generated_at']}`",
        "- 라이브 저장소 변경: 없음",
        "",
        "## 목적",
        "",
        "이 envelope는 subagent 역할 출력이 독립 산출물로 흩어지지 않고 Coordinator를 통해 같은 research_thread 기억으로 돌아오게 하는 표준 반환 형식이다.",
        "새 연구 claim, 수치, citation을 만들지 않으며 research_thread를 직접 변경하지 않는다.",
        "",
        "## 입력 경계",
        "",
        f"- Loop packet: `{envelope['input_refs']['loop_packet']}`",
        f"- Contract: `{envelope['input_refs']['contract']}`",
        f"- Source boundary: {envelope['source_boundary']['text']}",
        "",
        "## 역할 출력 요약",
        "",
        envelope["summary"],
        "",
        "## Evidence Boundaries",
        "",
    ]
    for item in envelope["evidence_boundaries"]:
        lines.append(f"- `{item['id']}` [{item['status']}] {item['text']}")
    lines.extend(["", "## Missing Evidence", ""])
    _append_review_section(lines, envelope["missing_evidence"])
    lines.extend(["", "## Counterarguments", ""])
    _append_review_section(lines, envelope["counterarguments"])
    lines.extend(["", "## Failure Modes", ""])
    _append_review_section(lines, envelope["failure_modes"])
    lines.extend(["", "## Artifact Candidates", ""])
    _append_review_section(lines, envelope["artifact_candidates"])
    lines.extend(["", "## Critique Gate", ""])
    lines.append(f"- Status: `{envelope['critique_gate']['status']}`")
    for finding in envelope["critique_gate"]["findings"]:
        lines.append(f"- `{finding['id']}` [{finding['status']}] {finding['text']}")
    lines.extend(["", "## Artifact Co-production", ""])
    lines.append(f"- Status: `{envelope['artifact_co_production']['status']}`")
    for candidate in envelope["artifact_co_production"]["candidates"]:
        lines.append(f"- `{candidate['id']}` [{candidate['status']}] {candidate['text']}")
    lines.extend(["", "## Stop Conditions", ""])
    for condition in envelope["stop_conditions"]:
        lines.append(f"- {condition}")
    lines.extend([
        "",
        "## Thread Patch Preview",
        "",
        "이 envelope는 research_thread를 직접 변경하지 않는다. 아래 patch preview는 Coordinator 검토 후 별도 CLI로 적용할 수 있는 후보일 뿐이다.",
        "",
        "```json",
        json.dumps(envelope["recommended_thread_patch"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
    ])
    return "\n".join(lines)


def _append_review_section(lines: list[str], items: list[dict[str, str]]) -> None:
    for item in items:
        lines.append(f"- `{item['id']}` [{item['status']}] {item['text']}")


def _selected_role(loop_packet: dict[str, Any], role: str) -> dict[str, Any]:
    role = _clean_text(role, "role")
    selected = {item["role"]: item for item in loop_packet["selected_roles"]}
    if role not in selected:
        valid = ", ".join(selected)
        raise ValueError(f"role is not selected in loop packet: {role}. Selected roles: {valid}")
    if role not in ROLE_OUTPUT_TYPES:
        catalog = ", ".join(item["role"] for item in SUBAGENT_ROLE_CATALOG)
        raise ValueError(f"unsupported subagent role: {role}. Valid roles: {catalog}")
    return dict(selected[role])


def _validate_output_type(role: str, output_type: str) -> str:
    output_type = _clean_text(output_type, "output_type")
    valid = ROLE_OUTPUT_TYPES.get(role, ())
    if output_type not in valid:
        raise ValueError(f"unsupported output_type for {role}: {output_type}. Valid output types: {', '.join(valid)}")
    return output_type


def _review_items(values: list[str], *, default: str) -> list[dict[str, str]]:
    source = values or [default]
    status = "unresolved" if values else "not_provided"
    return [
        {
            "id": f"item.{idx}",
            "text": value,
            "status": status,
        }
        for idx, value in enumerate(source, start=1)
    ]


def _normalize_text_items(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return []
    return [_clean_text(value, "list item") for value in values if isinstance(value, str) and value.strip()]


def _required_nonempty_string(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def _clean_text(value: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a non-empty string")
    return value.strip()


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", value).strip("_").lower()
    return slug or "item"
