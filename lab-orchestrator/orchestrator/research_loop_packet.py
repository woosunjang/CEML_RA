"""Dry-run-first research loop packet planning for CEML_RA.

This module turns a research_thread plus a trigger into a reviewable loop
packet. It does not create new research claims, mutate the research_thread, call
LLMs, or touch live Slack/Scout/KG/RAG/runtime stores.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.research_thread import (
    load_research_thread,
    resolve_artifacts_dir,
    utc_now,
    validate_research_thread,
)


SCHEMA_VERSION = 1
PLANNER_NAME = "research_loop_packet_v1"
LOOP_PACKETS_DIR = "research_loop_packets"
VALID_TRIGGER_TYPES = ("automatic", "on_demand")

CONTRACT_REF = "docs/ceml-ra-research-loop-contract-v1.md"

SUBAGENT_ROLE_CATALOG: tuple[dict[str, str], ...] = (
    {
        "role": "Scout",
        "input": "topic, source hint, thread context",
        "output": "source signals, candidate sources",
        "must_not": "Scout DB를 조용히 변경하지 않는다.",
    },
    {
        "role": "Literature/RAG",
        "input": "source refs, question, thread context",
        "output": "evidence preview, retrieval summary",
        "must_not": "RAG 결과를 확정 claim으로 승격하지 않는다.",
    },
    {
        "role": "KG Memory",
        "input": "thread items, artifact refs",
        "output": "KG ingest preview",
        "must_not": "승인 없이 Neo4j/Graphiti에 ingest하지 않는다.",
    },
    {
        "role": "Evidence Critic",
        "input": "claims, evidence, artifact draft",
        "output": "counterarguments, missing evidence, failure modes",
        "must_not": "빈 근거를 확정처럼 포장하지 않는다.",
    },
    {
        "role": "Writing",
        "input": "thread context, evidence boundary, audience",
        "output": "Korean-first draft or artifact",
        "must_not": "출처 없는 새 연구 주장을 만들지 않는다.",
    },
    {
        "role": "Project",
        "input": "decisions, next actions, deadlines",
        "output": "next-action plan, stop conditions",
        "must_not": "status loop를 제품 진전으로 포장하지 않는다.",
    },
)


@dataclass(frozen=True)
class ResearchLoopPacketPaths:
    json_path: Path
    markdown_path: Path
    patch_preview_path: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "json_path": str(self.json_path),
            "markdown_path": str(self.markdown_path),
            "patch_preview_path": str(self.patch_preview_path),
        }


def research_loop_packets_dir(artifacts_dir: Path | None = None) -> Path:
    return resolve_artifacts_dir(artifacts_dir) / LOOP_PACKETS_DIR


def research_loop_packet_paths(
    *,
    thread_id: str,
    packet_id: str,
    artifacts_dir: Path | None = None,
) -> ResearchLoopPacketPaths:
    base = research_loop_packets_dir(artifacts_dir)
    stem = f"{thread_id}_{packet_id}"
    return ResearchLoopPacketPaths(
        json_path=base / f"{stem}.json",
        markdown_path=base / f"{stem}.md",
        patch_preview_path=base / f"{stem}_thread_patch_preview.json",
    )


def build_research_loop_packet(
    *,
    research_thread: dict[str, Any],
    trigger_type: str,
    trigger_summary: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    validate_research_thread(research_thread)
    trigger = _build_trigger(trigger_type=trigger_type, trigger_summary=trigger_summary)
    generated_at = created_at or utc_now()
    thread_id = research_thread["thread_id"]
    packet_id = build_packet_id(thread_id=thread_id, trigger_type=trigger["type"], trigger_summary=trigger["summary"])
    selected_roles = select_roles_for_trigger(research_thread, trigger)
    source_context = build_source_context(research_thread)
    expected_outputs = build_expected_outputs(trigger, selected_roles)
    stop_conditions = build_stop_conditions(trigger)
    artifact_candidates = build_artifact_candidates(thread_id, trigger)
    thread_patch_preview = build_thread_patch_preview(
        thread_id=thread_id,
        packet_id=packet_id,
        trigger=trigger,
        selected_roles=selected_roles,
        artifact_candidates=artifact_candidates,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "planner": PLANNER_NAME,
        "generated_at": generated_at,
        "packet_id": packet_id,
        "thread_id": thread_id,
        "topic": research_thread["topic"],
        "research_state": research_thread["research_state"],
        "trigger": trigger,
        "candidate_roles": list(SUBAGENT_ROLE_CATALOG),
        "selected_roles": selected_roles,
        "source_context": source_context,
        "expected_outputs": expected_outputs,
        "stop_conditions": stop_conditions,
        "artifact_candidates": artifact_candidates,
        "thread_patch_preview": thread_patch_preview,
        "live_store_mutations": [],
    }


def preview_or_write_research_loop_packet(
    *,
    thread_id: str,
    trigger_type: str,
    trigger_summary: str,
    artifacts_dir: Path | None = None,
    execute: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    research_thread = load_research_thread(thread_id, artifacts_dir=artifacts_dir)
    packet = build_research_loop_packet(
        research_thread=research_thread,
        trigger_type=trigger_type,
        trigger_summary=trigger_summary,
        created_at=created_at,
    )
    paths = research_loop_packet_paths(
        thread_id=thread_id,
        packet_id=packet["packet_id"],
        artifacts_dir=artifacts_dir,
    )
    markdown = render_research_loop_packet_markdown(packet)
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "written" if execute else "would_write",
        "dry_run": not execute,
        "thread_id": thread_id,
        "packet_id": packet["packet_id"],
        **paths.as_dict(),
        "packet": packet,
        "preview_markdown": markdown,
        "live_store_mutations": [],
    }
    if execute:
        paths.json_path.parent.mkdir(parents=True, exist_ok=True)
        paths.json_path.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths.markdown_path.write_text(markdown, encoding="utf-8")
        paths.patch_preview_path.write_text(
            json.dumps(packet["thread_patch_preview"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result


def build_packet_id(*, thread_id: str, trigger_type: str, trigger_summary: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", trigger_summary).strip("_").lower()
    if not slug:
        slug = "research_loop"
    digest = hashlib.sha1(f"{thread_id}:{trigger_type}:{trigger_summary}".encode("utf-8")).hexdigest()[:10]
    return f"{trigger_type}_{slug[:40]}_{digest}"


def select_roles_for_trigger(research_thread: dict[str, Any], trigger: dict[str, str]) -> list[dict[str, Any]]:
    role_order = ["Scout", "Literature/RAG", "Evidence Critic", "Project"]
    if trigger["type"] == "on_demand":
        role_order = ["Literature/RAG", "Evidence Critic", "Writing", "Project"]
    if _has_no_source_context(research_thread):
        role_order.insert(0, "Scout")
    role_order = _dedupe(role_order)
    catalog = {item["role"]: item for item in SUBAGENT_ROLE_CATALOG}
    selected = []
    for role in role_order:
        item = dict(catalog[role])
        item["reason"] = _role_reason(role, trigger)
        selected.append(item)
    return selected


def build_source_context(research_thread: dict[str, Any]) -> dict[str, Any]:
    open_next_actions = [
        {
            "id": item["id"],
            "text": item["text"],
            "status": item["status"],
        }
        for item in research_thread.get("next_actions", [])
        if item.get("status") == "open"
    ][:5]
    latest_decisions = [
        {
            "id": item["id"],
            "text": item["text"],
            "status": item["status"],
        }
        for item in research_thread.get("decisions", [])[-3:]
    ]
    return {
        "thread_id": research_thread["thread_id"],
        "topic": research_thread["topic"],
        "research_state": research_thread["research_state"],
        "section_counts": {
            section: len(research_thread.get(section, []))
            for section in (
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
        },
        "open_next_actions": open_next_actions,
        "latest_decisions": latest_decisions,
        "context_boundary": "이 packet은 기존 thread 상태를 요약할 뿐 새 연구 claim이나 evidence를 생성하지 않는다.",
    }


def build_expected_outputs(trigger: dict[str, str], selected_roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outputs = [
        {
            "type": "thread_patch_preview",
            "description": "루프 계획과 stop condition을 사람이 검토할 수 있는 research_thread patch preview로 남긴다.",
            "owner_role": "Coordinator",
        },
        {
            "type": "loop_review_note",
            "description": "이번 루프가 실제 research_thread 기억을 어떻게 전진시킬지 한국어 요약으로 남긴다.",
            "owner_role": "Project",
        },
    ]
    if any(role["role"] == "Evidence Critic" for role in selected_roles):
        outputs.append({
            "type": "evidence_boundary_preview",
            "description": "확정 claim이 아니라 검토해야 할 근거 경계와 missing evidence를 분리한다.",
            "owner_role": "Evidence Critic",
        })
    if trigger["type"] == "on_demand":
        outputs.append({
            "type": "response_context_plan",
            "description": "사용자 요청 답변 전에 어떤 thread 맥락과 artifact를 읽어야 하는지 정한다.",
            "owner_role": "Writing",
        })
    return outputs


def build_stop_conditions(trigger: dict[str, str]) -> list[str]:
    conditions = [
        "새 연구 claim, 수치, citation을 추정해야 하면 멈춘다.",
        "research_thread를 직접 변경해야 하면 patch preview만 남기고 멈춘다.",
        "Slack, runtime service, Scout DB, Qdrant, Neo4j, Graphiti, KG/RAG store 변경이 필요하면 멈춘다.",
        "사용자에게 보일 Markdown 또는 설명 문장을 한국어 중심으로 유지할 수 없으면 멈춘다.",
    ]
    if trigger["type"] == "automatic":
        conditions.append("자동 루프가 많은 작업량만 만들고 기억 갱신을 만들지 못하면 멈춘다.")
    else:
        conditions.append("사용자 요청의 의도가 기존 thread 맥락으로 판단하기 어려우면 답변 생성 전에 질문한다.")
    return conditions


def build_artifact_candidates(thread_id: str, trigger: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            "artifact_type": "research_loop_packet",
            "recommended_output_dir": LOOP_PACKETS_DIR,
            "recommended_markdown_name": f"{thread_id}_{trigger['type']}_loop_packet.md",
            "recommended_json_name": f"{thread_id}_{trigger['type']}_loop_packet.json",
            "purpose": "루프 입력, 역할 호출 계획, 출력 후보, stop condition을 검토 가능한 형태로 남긴다.",
        },
        {
            "artifact_type": "thread_patch_preview",
            "recommended_output_dir": LOOP_PACKETS_DIR,
            "recommended_json_name": f"{thread_id}_{trigger['type']}_thread_patch_preview.json",
            "purpose": "실제 thread 변경 전에 사람이 검토할 수 있는 patch 후보를 남긴다.",
        },
    ]


def build_thread_patch_preview(
    *,
    thread_id: str,
    packet_id: str,
    trigger: dict[str, str],
    selected_roles: list[dict[str, Any]],
    artifact_candidates: list[dict[str, str]],
) -> dict[str, Any]:
    role_names = [role["role"] for role in selected_roles]
    return {
        "schema_version": 1,
        "thread_id": thread_id,
        "research_state": "loop_packet_planned",
        "append": {
            "decisions": [
                {
                    "id": f"decision.loop_packet.{packet_id}",
                    "text": (
                        f"Research Loop Packet v1이 `{trigger['type']}` trigger를 검토하고 "
                        f"{', '.join(role_names)} 역할 호출 계획을 만들었다. 이 결정은 새 연구 내용을 "
                        "작성하지 않고 다음 루프의 기억 갱신 경계를 정하기 위한 것이다."
                    ),
                    "status": "proposed",
                    "confidence": PLANNER_NAME,
                    "source_refs": [CONTRACT_REF],
                    "tags": ["research-loop-packet", "memory-spine", trigger["type"]],
                    "metadata": {
                        "packet_id": packet_id,
                        "live_store_mutations": [],
                    },
                }
            ],
            "failure_modes": [
                {
                    "id": f"failure_mode.loop_packet.{packet_id}.content_drift",
                    "text": "Loop Packet 실행이 새 연구 claim을 임의로 만들거나 live store를 변경하면 실패한다.",
                    "status": "open",
                    "confidence": PLANNER_NAME,
                    "source_refs": [CONTRACT_REF],
                    "tags": ["research-loop-packet", "anti-drift"],
                    "metadata": {
                        "packet_id": packet_id,
                        "live_store_mutations": [],
                    },
                }
            ],
            "next_actions": [
                {
                    "id": f"next_action.loop_packet.{packet_id}.review",
                    "text": "이 loop packet의 역할 호출 계획과 stop condition을 검토한 뒤, 필요한 경우 별도 실행 루프를 설계한다.",
                    "status": "open",
                    "confidence": PLANNER_NAME,
                    "source_refs": [CONTRACT_REF],
                    "tags": ["research-loop-packet", "review-before-execution"],
                    "metadata": {
                        "packet_id": packet_id,
                        "artifact_candidates": artifact_candidates,
                        "live_store_mutations": [],
                    },
                }
            ],
        },
        "metadata": {
            "last_research_loop_packet": {
                "packet_id": packet_id,
                "trigger": trigger,
                "selected_roles": role_names,
                "live_store_mutations": [],
            }
        },
    }


def render_research_loop_packet_markdown(packet: dict[str, Any]) -> str:
    lines = [
        f"# Research Loop Packet: {packet['thread_id']}",
        "",
        f"- Packet ID: `{packet['packet_id']}`",
        f"- 생성 시각: `{packet['generated_at']}`",
        f"- Trigger: `{packet['trigger']['type']}`",
        f"- Trigger summary: {packet['trigger']['summary']}",
        "- 라이브 저장소 변경: 없음",
        "",
        "## 목적",
        "",
        "이 packet은 다음 연구 루프의 입력, 역할 호출, 출력 후보, stop condition을 구조화한다.",
        "새 연구 claim, 수치, citation을 만들지 않으며 research_thread를 직접 변경하지 않는다.",
        "",
        "## Source Context",
        "",
        f"- Topic: `{packet['source_context']['topic']}`",
        f"- Research state: `{packet['source_context']['research_state']}`",
        f"- Context boundary: {packet['source_context']['context_boundary']}",
        "",
        "### Open Next Actions",
        "",
    ]
    open_actions = packet["source_context"]["open_next_actions"]
    if not open_actions:
        lines.append("- 열린 next action 없음")
    else:
        for item in open_actions:
            lines.append(f"- `{item['id']}` [{item['status']}] {item['text']}")
    lines.extend(["", "## Selected Roles", ""])
    for role in packet["selected_roles"]:
        lines.append(f"- `{role['role']}`: {role['reason']}")
        lines.append(f"  - Output: {role['output']}")
        lines.append(f"  - Must not: {role['must_not']}")
    lines.extend(["", "## Expected Outputs", ""])
    for output in packet["expected_outputs"]:
        lines.append(f"- `{output['type']}` ({output['owner_role']}): {output['description']}")
    lines.extend(["", "## Artifact Candidates", ""])
    for artifact in packet["artifact_candidates"]:
        lines.append(f"- `{artifact['artifact_type']}`: {artifact['purpose']}")
        lines.append(f"  - Output dir: `{artifact['recommended_output_dir']}`")
    lines.extend(["", "## Stop Conditions", ""])
    for condition in packet["stop_conditions"]:
        lines.append(f"- {condition}")
    lines.extend([
        "",
        "## Thread Patch Preview",
        "",
        "이 packet은 research_thread를 직접 변경하지 않는다. 아래 patch preview를 사람이 검토한 뒤 별도 CLI로 적용할 수 있다.",
        "",
        "```json",
        json.dumps(packet["thread_patch_preview"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
    ])
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


def _role_reason(role: str, trigger: dict[str, str]) -> str:
    if role == "Scout":
        return "source signal이 부족하거나 자동 루프에서 새 후보 source 검토가 필요할 수 있다."
    if role == "Literature/RAG":
        return "기존 thread와 artifact를 읽고 답변 또는 다음 루프의 근거 경계를 잡아야 한다."
    if role == "Evidence Critic":
        return "약한 주장, missing evidence, counterargument, failure mode를 먼저 분리해야 한다."
    if role == "Writing":
        return "요청 기반 루프에서 사용자에게 보일 한국어 응답 또는 artifact 후보를 준비할 수 있다."
    if role == "Project":
        return "결정과 next action을 기억으로 되돌릴 수 있는 stop condition과 후속 작업을 정해야 한다."
    return f"{trigger['type']} trigger 처리를 위한 보조 역할이다."


def _has_no_source_context(research_thread: dict[str, Any]) -> bool:
    return not research_thread.get("source_signals") and not research_thread.get("evidence")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
