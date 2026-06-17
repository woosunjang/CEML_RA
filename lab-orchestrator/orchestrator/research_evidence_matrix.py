"""Evidence Matrix review artifacts for CEML_RA research threads.

This module builds a structured review surface from a research_thread and its
shared context bundle. It does not create new research claims, score scientific
truth, mutate live stores, or apply thread patches.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.research_context_bundle import build_research_context_bundle
from orchestrator.research_thread import (
    load_research_thread,
    normalize_research_thread,
    resolve_artifacts_dir,
    utc_now,
    validate_research_thread,
)


SCHEMA_VERSION = 1
BUILDER_NAME = "evidence_matrix_review_surface_v1"
EVIDENCE_MATRICES_DIR = "evidence_matrices"
CONTRACT_REF = "docs/ceml-ra-capability-development-plan-v1.md"

FOCUS_SECTIONS = ("claims", "idea_candidates", "next_actions")
VALID_TRIGGER_TYPES = ("automatic", "on_demand")
VALID_MATURITY_LANES = (
    "raw",
    "needs_evidence",
    "proposal_reviewable",
    "calculation_ready",
    "experiment_ready",
    "defer",
)
NEEDS_EVIDENCE_STATES = {"needs_evidence", "not_evaluated", "blocked_until_evidence"}


@dataclass(frozen=True)
class EvidenceMatrixPaths:
    json_path: Path
    markdown_path: Path
    patch_preview_path: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "json_path": str(self.json_path),
            "markdown_path": str(self.markdown_path),
            "patch_preview_path": str(self.patch_preview_path),
        }


def evidence_matrices_dir(artifacts_dir: Path | None = None) -> Path:
    return resolve_artifacts_dir(artifacts_dir) / EVIDENCE_MATRICES_DIR


def evidence_matrix_paths(
    *,
    thread_id: str,
    matrix_id: str,
    artifacts_dir: Path | None = None,
) -> EvidenceMatrixPaths:
    base = evidence_matrices_dir(artifacts_dir)
    stem = f"{thread_id}_{matrix_id}"
    return EvidenceMatrixPaths(
        json_path=base / f"{stem}.json",
        markdown_path=base / f"{stem}.md",
        patch_preview_path=base / f"{stem}_thread_patch_preview.json",
    )


def build_evidence_matrix(
    *,
    research_thread: dict[str, Any],
    trigger_type: str,
    trigger_summary: str,
    created_at: str | None = None,
    max_rows: int = 12,
) -> dict[str, Any]:
    thread = normalize_research_thread(research_thread)
    validate_research_thread(thread)
    trigger = _build_trigger(trigger_type=trigger_type, trigger_summary=trigger_summary)
    generated_at = created_at or utc_now()
    matrix_id = build_matrix_id(
        thread_id=thread["thread_id"],
        trigger_type=trigger["type"],
        trigger_summary=trigger["summary"],
    )
    context_bundle = build_research_context_bundle(
        research_thread=thread,
        trigger_type=trigger["type"],
        trigger_summary=trigger["summary"],
        created_at=generated_at,
    )
    focus_items = select_focus_items(thread, context_bundle=context_bundle, max_rows=max_rows)
    rows = [
        build_matrix_row(
            focus_item=item,
            research_thread=thread,
            matrix_id=matrix_id,
        )
        for item in focus_items
    ]
    coverage = build_coverage_summary(rows)
    recommended_thread_patch = build_thread_patch_preview(
        thread_id=thread["thread_id"],
        matrix_id=matrix_id,
        trigger=trigger,
        coverage=coverage,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "builder": BUILDER_NAME,
        "generated_at": generated_at,
        "matrix_id": matrix_id,
        "thread_id": thread["thread_id"],
        "topic": thread["topic"],
        "research_state": thread["research_state"],
        "trigger": trigger,
        "context_bundle": context_bundle,
        "review_surface_boundary": {
            "kind": "structured_review_surface",
            "text": (
                "이 Evidence Matrix는 자율 판단 엔진이 아니라 claim/idea/action을 근거, 반론, "
                "결손, 성숙도 lane과 병치하는 검토 표면이다. 근거 없는 항목을 artifact나 KG fact로 "
                "승격하지 않는다."
            ),
        },
        "maturity_lanes": list(VALID_MATURITY_LANES),
        "rows": rows,
        "coverage": coverage,
        "recommended_thread_patch": recommended_thread_patch,
        "stop_conditions": build_stop_conditions(),
        "live_store_mutations": [],
    }


def preview_or_write_evidence_matrix(
    *,
    thread_id: str,
    trigger_type: str,
    trigger_summary: str,
    artifacts_dir: Path | None = None,
    execute: bool = False,
    created_at: str | None = None,
    max_rows: int = 12,
) -> dict[str, Any]:
    thread = load_research_thread(thread_id, artifacts_dir=artifacts_dir)
    matrix = build_evidence_matrix(
        research_thread=thread,
        trigger_type=trigger_type,
        trigger_summary=trigger_summary,
        created_at=created_at,
        max_rows=max_rows,
    )
    paths = evidence_matrix_paths(
        thread_id=thread_id,
        matrix_id=matrix["matrix_id"],
        artifacts_dir=artifacts_dir,
    )
    markdown = render_evidence_matrix_markdown(matrix)
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "written" if execute else "would_write",
        "dry_run": not execute,
        "read_only": not execute,
        "artifact_write": execute,
        "thread_id": thread_id,
        "matrix_id": matrix["matrix_id"],
        **paths.as_dict(),
        "matrix": matrix,
        "preview_markdown": markdown,
        "recommended_thread_patch": matrix["recommended_thread_patch"],
        "live_store_mutations": [],
    }
    if execute:
        paths.json_path.parent.mkdir(parents=True, exist_ok=True)
        paths.json_path.write_text(
            json.dumps(matrix, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths.markdown_path.write_text(markdown, encoding="utf-8")
        paths.patch_preview_path.write_text(
            json.dumps(matrix["recommended_thread_patch"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result


def build_matrix_id(*, thread_id: str, trigger_type: str, trigger_summary: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", trigger_summary).strip("_").lower() or "evidence_matrix"
    digest = hashlib.sha1(f"{thread_id}:{trigger_type}:{trigger_summary}".encode("utf-8")).hexdigest()[:10]
    return f"{trigger_type}_{slug[:40]}_{digest}"


def select_focus_items(
    thread: dict[str, Any],
    *,
    context_bundle: dict[str, Any],
    max_rows: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for section in FOCUS_SECTIONS:
        for item in thread.get(section, []):
            selected.append(_compact_item(section, item))
            if len(selected) >= max_rows:
                return selected
    if selected:
        return selected

    for item in context_bundle.get("evidence_gaps", []):
        selected.append(dict(item))
        if len(selected) >= max_rows:
            break
    return selected


def build_matrix_row(
    *,
    focus_item: dict[str, Any],
    research_thread: dict[str, Any],
    matrix_id: str,
) -> dict[str, Any]:
    evidence = _related_items(focus_item, research_thread.get("evidence", []), section="evidence")
    counterarguments = _related_items(focus_item, research_thread.get("counterarguments", []), section="counterarguments")
    missing_evidence = build_missing_evidence(focus_item=focus_item, evidence=evidence)
    maturity = infer_maturity_lane(focus_item)
    review_action = recommend_review_action(
        evidence=evidence,
        counterarguments=counterarguments,
        missing_evidence=missing_evidence,
        maturity_lane=maturity["lane"],
    )
    row_id = _safe_id(f"evidence_matrix_row.{matrix_id}.{focus_item.get('section', 'object')}.{focus_item.get('id', 'unknown')}")
    return {
        "row_id": row_id,
        "focus": focus_item,
        "maturity_lane": maturity,
        "current_evidence": evidence,
        "counterarguments": counterarguments,
        "missing_evidence": missing_evidence,
        "review_questions": build_review_questions(
            focus_item=focus_item,
            evidence=evidence,
            counterarguments=counterarguments,
            missing_evidence=missing_evidence,
        ),
        "recommended_review_action": review_action,
        "provenance": {
            "source_refs": focus_item.get("source_refs", []),
            "artifact_refs": focus_item.get("artifact_refs", []),
            "object_ref": focus_item.get("object_ref", ""),
        },
        "live_store_mutations": [],
    }


def build_missing_evidence(
    *,
    focus_item: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> list[dict[str, str]]:
    missing = []
    support_state = str(focus_item.get("support_state", "not_evaluated"))
    if support_state in NEEDS_EVIDENCE_STATES:
        missing.append({
            "id": "missing.support_state",
            "status": "open",
            "text": f"이 항목의 support_state가 `{support_state}`이므로 근거 검토가 필요하다.",
        })
    if not evidence:
        missing.append({
            "id": "missing.no_linked_evidence",
            "status": "open",
            "text": "이 항목을 지지하는 evidence object가 아직 연결되지 않았다.",
        })
    return missing


def infer_maturity_lane(item: dict[str, Any]) -> dict[str, str]:
    metadata = item.get("metadata", {})
    explicit_candidates = []
    if isinstance(metadata, dict):
        explicit_candidates.append(("metadata", metadata.get("maturity_lane")))
    explicit_candidates.extend([
        ("field", item.get("maturity_lane")),
        ("status", item.get("status")),
        ("support_state", item.get("support_state")),
    ])
    for source, value in explicit_candidates:
        if isinstance(value, str) and value in VALID_MATURITY_LANES:
            return {"lane": value, "source": source, "note": "thread에 명시된 maturity lane을 사용했다."}
    for tag in item.get("tags", []) or []:
        if tag in VALID_MATURITY_LANES:
            return {"lane": tag, "source": "tag", "note": "thread tag에 명시된 maturity lane을 사용했다."}

    support_state = str(item.get("support_state", "not_evaluated"))
    if support_state in NEEDS_EVIDENCE_STATES:
        return {
            "lane": "needs_evidence",
            "source": "support_state",
            "note": "근거 부족 상태를 review lane으로 표시했다. 자동 승격은 하지 않는다.",
        }
    return {
        "lane": "raw",
        "source": "default",
        "note": "명시 maturity lane이 없어 raw review lane으로 유지했다.",
    }


def recommend_review_action(
    *,
    evidence: list[dict[str, Any]],
    counterarguments: list[dict[str, Any]],
    missing_evidence: list[dict[str, str]],
    maturity_lane: str,
) -> dict[str, str]:
    if missing_evidence:
        return {
            "action": "hold_for_evidence",
            "status": "requires_review",
            "text": "근거 결손이 남아 있으므로 claim/proposal/KG fact 승격을 보류한다.",
        }
    if counterarguments:
        return {
            "action": "review_counterarguments",
            "status": "requires_review",
            "text": "반론이 남아 있으므로 patch 적용 전에 counterargument를 검토한다.",
        }
    if evidence and maturity_lane in {"proposal_reviewable", "calculation_ready", "experiment_ready"}:
        return {
            "action": "review_for_possible_promotion",
            "status": "reviewable",
            "text": "연결 근거가 있으나 자동 승격하지 않는다. 사용자가 patch review에서 승격 여부를 결정한다.",
        }
    return {
        "action": "keep_under_review",
        "status": "preview_only",
        "text": "현재 thread 상태를 유지하고 다음 근거 수집 또는 비판 검토 후보로 둔다.",
    }


def build_review_questions(
    *,
    focus_item: dict[str, Any],
    evidence: list[dict[str, Any]],
    counterarguments: list[dict[str, Any]],
    missing_evidence: list[dict[str, str]],
) -> list[str]:
    questions = [
        "이 항목은 어떤 연구 결정, 계산, 실험, 제안서 판단에 영향을 주는가?",
    ]
    if not evidence:
        questions.append("이 항목을 지지하는 최소 evidence object 또는 source는 무엇인가?")
    if counterarguments:
        questions.append("현재 반론이 이 항목을 기각하는가, 아니면 claim boundary를 좁히는가?")
    if missing_evidence:
        questions.append("missing evidence가 해소되기 전까지 이 항목을 어떤 lane에 묶어둘 것인가?")
    if focus_item.get("section") == "next_actions":
        questions.append("이 next action은 근거 수집, 비판 검토, artifact draft 중 어디로 이어져야 하는가?")
    return questions


def build_coverage_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows_with_evidence = [row for row in rows if row["current_evidence"]]
    rows_with_counterarguments = [row for row in rows if row["counterarguments"]]
    rows_with_missing = [row for row in rows if row["missing_evidence"]]
    lanes: dict[str, int] = {lane: 0 for lane in VALID_MATURITY_LANES}
    for row in rows:
        lane = row["maturity_lane"]["lane"]
        lanes[lane] = lanes.get(lane, 0) + 1
    return {
        "row_count": len(rows),
        "rows_with_evidence": len(rows_with_evidence),
        "rows_with_counterarguments": len(rows_with_counterarguments),
        "rows_with_missing_evidence": len(rows_with_missing),
        "maturity_lane_counts": lanes,
        "critique_gate": "requires_review" if rows_with_missing or rows_with_counterarguments else "preview_passed",
        "live_store_mutations": [],
    }


def build_thread_patch_preview(
    *,
    thread_id: str,
    matrix_id: str,
    trigger: dict[str, str],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "thread_id": thread_id,
        "research_state": "evidence_matrix_reviewed",
        "append": {
            "decisions": [
                {
                    "id": f"decision.evidence_matrix.{matrix_id}",
                    "text": (
                        f"Evidence Matrix Review Surface v1이 `{trigger['type']}` trigger를 기준으로 "
                        "근거, 반론, 결손, maturity lane을 병치한 검토 행렬을 만들었다. 이 결정은 "
                        "새 research claim을 확정하지 않고 patch review로 이어질 구조를 남기기 위한 것이다."
                    ),
                    "status": "proposed",
                    "confidence": BUILDER_NAME,
                    "source_refs": [CONTRACT_REF],
                    "tags": ["evidence-matrix", "review-surface", trigger["type"]],
                    "review_state": "pending_review",
                    "support_state": "coordination_boundary",
                    "metadata": {
                        "matrix_id": matrix_id,
                        "coverage": coverage,
                        "live_store_mutations": [],
                    },
                }
            ],
            "failure_modes": [
                {
                    "id": f"failure_mode.evidence_matrix.{matrix_id}.overclaiming",
                    "text": (
                        "Evidence Matrix를 자동 판단 엔진이나 확정 claim 승격기로 취급하면 실패한다. "
                        "근거 결손과 반론은 patch review 전까지 보존해야 한다."
                    ),
                    "status": "open",
                    "confidence": BUILDER_NAME,
                    "source_refs": [CONTRACT_REF],
                    "tags": ["evidence-matrix", "anti-overclaim"],
                    "review_state": "pending_review",
                    "support_state": "risk_boundary",
                    "metadata": {
                        "matrix_id": matrix_id,
                        "critique_gate": coverage["critique_gate"],
                        "live_store_mutations": [],
                    },
                }
            ],
            "next_actions": [
                {
                    "id": f"next_action.evidence_matrix.{matrix_id}.patch_review",
                    "text": (
                        "Evidence Matrix 행의 missing evidence, counterargument, maturity lane을 검토한 뒤 "
                        "필요한 thread patch를 preview/apply/reject workflow에서 명시적으로 결정한다."
                    ),
                    "status": "open",
                    "confidence": BUILDER_NAME,
                    "source_refs": [CONTRACT_REF],
                    "tags": ["evidence-matrix", "patch-review"],
                    "review_state": "pending_review",
                    "support_state": "next_action",
                    "metadata": {
                        "matrix_id": matrix_id,
                        "rows_with_missing_evidence": coverage["rows_with_missing_evidence"],
                        "rows_with_counterarguments": coverage["rows_with_counterarguments"],
                        "live_store_mutations": [],
                    },
                }
            ],
        },
        "metadata": {
            "last_evidence_matrix": {
                "matrix_id": matrix_id,
                "trigger": trigger,
                "coverage": coverage,
                "live_store_mutations": [],
            }
        },
        "live_store_mutations": [],
    }


def build_stop_conditions() -> list[str]:
    return [
        "새 연구 claim, 수치, citation을 추정해야 하면 Evidence Matrix 생성을 멈춘다.",
        "maturity lane을 명시 근거 없이 승격해야 하면 raw 또는 needs_evidence로 남긴다.",
        "research_thread를 직접 변경해야 하면 recommended_thread_patch만 남기고 멈춘다.",
        "Slack, runtime service, Scout DB, Qdrant, Neo4j, Graphiti, KG/RAG store 변경이 필요하면 멈춘다.",
    ]


def render_evidence_matrix_markdown(matrix: dict[str, Any]) -> str:
    lines = [
        f"# Evidence Matrix Review Surface: {matrix['thread_id']}",
        "",
        f"- Matrix ID: `{matrix['matrix_id']}`",
        f"- 생성 시각: `{matrix['generated_at']}`",
        f"- Trigger: `{matrix['trigger']['type']}`",
        f"- Trigger summary: {matrix['trigger']['summary']}",
        "- 라이브 저장소 변경: 없음",
        "",
        "## 검토 경계",
        "",
        matrix["review_surface_boundary"]["text"],
        "",
        "## Coverage",
        "",
        f"- Row count: `{matrix['coverage']['row_count']}`",
        f"- Evidence linked rows: `{matrix['coverage']['rows_with_evidence']}`",
        f"- Counterargument rows: `{matrix['coverage']['rows_with_counterarguments']}`",
        f"- Missing evidence rows: `{matrix['coverage']['rows_with_missing_evidence']}`",
        f"- Critique gate: `{matrix['coverage']['critique_gate']}`",
        "",
        "## Matrix Rows",
        "",
    ]
    if not matrix["rows"]:
        lines.append("- 검토할 row 없음")
    for row in matrix["rows"]:
        focus = row["focus"]
        lines.extend([
            f"### `{row['row_id']}`",
            "",
            f"- Focus: `{focus.get('object_ref', '')}` ({focus.get('section', '')})",
            f"- Status: `{focus.get('status', '')}` / Review: `{focus.get('review_state', '')}` / Support: `{focus.get('support_state', '')}`",
            f"- Maturity lane: `{row['maturity_lane']['lane']}` ({row['maturity_lane']['source']})",
            f"- Recommended action: `{row['recommended_review_action']['action']}`",
            f"- Text: {focus.get('text', '')}",
            "",
            "#### Current Evidence",
            "",
        ])
        _append_item_lines(lines, row["current_evidence"], empty_text="연결 evidence 없음")
        lines.extend(["", "#### Counterarguments", ""])
        _append_item_lines(lines, row["counterarguments"], empty_text="명시 counterargument 없음")
        lines.extend(["", "#### Missing Evidence", ""])
        _append_missing_lines(lines, row["missing_evidence"])
        lines.extend(["", "#### Review Questions", ""])
        for question in row["review_questions"]:
            lines.append(f"- {question}")
        lines.append("")
    lines.extend([
        "## Recommended Thread Patch",
        "",
        "이 Matrix는 research_thread를 직접 변경하지 않는다. 아래 patch preview는 기존 Patch Review Workflow에서 preview/apply/reject로 검토할 후보이다.",
        "",
        "```json",
        json.dumps(matrix["recommended_thread_patch"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
    ])
    return "\n".join(lines)


def _related_items(focus_item: dict[str, Any], candidates: list[dict[str, Any]], *, section: str) -> list[dict[str, Any]]:
    focus_ref = focus_item.get("object_ref")
    focus_related = set(focus_item.get("related_object_refs", []) or [])
    focus_sources = set(focus_item.get("source_refs", []) or [])
    related = []
    for candidate in candidates:
        candidate_related = set(candidate.get("related_object_refs", []) or [])
        candidate_sources = set(candidate.get("source_refs", []) or [])
        match_reason = None
        if focus_ref and focus_ref in candidate_related:
            match_reason = "candidate_related_object_ref"
        elif candidate.get("object_ref") in focus_related:
            match_reason = "focus_related_object_ref"
        elif focus_sources and focus_sources.intersection(candidate_sources):
            match_reason = "source_ref_overlap"
        if match_reason:
            item = _compact_item(section, candidate)
            item["match_reason"] = match_reason
            related.append(item)
    return related


def _compact_item(section: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "section": section,
        "id": str(item.get("id", "")),
        "object_ref": str(item.get("object_ref", "")),
        "text": str(item.get("text", "")),
        "status": str(item.get("status", "")),
        "authority_state": str(item.get("authority_state", "")),
        "review_state": str(item.get("review_state", "")),
        "support_state": str(item.get("support_state", "")),
        "source_refs": list(item.get("source_refs", []) or []),
        "artifact_refs": list(item.get("artifact_refs", []) or []),
        "related_object_refs": list(item.get("related_object_refs", []) or []),
        "tags": list(item.get("tags", []) or []),
        "metadata": dict(item.get("metadata", {}) or {}),
    }


def _build_trigger(*, trigger_type: str, trigger_summary: str) -> dict[str, str]:
    if trigger_type not in VALID_TRIGGER_TYPES:
        valid = ", ".join(VALID_TRIGGER_TYPES)
        raise ValueError(f"unsupported trigger_type: {trigger_type}. Valid trigger types: {valid}")
    if not isinstance(trigger_summary, str) or not trigger_summary.strip():
        raise ValueError("trigger_summary must be a non-empty string")
    return {"type": trigger_type, "summary": trigger_summary.strip()}


def _append_item_lines(lines: list[str], items: list[dict[str, Any]], *, empty_text: str) -> None:
    if not items:
        lines.append(f"- {empty_text}")
        return
    for item in items:
        lines.append(f"- `{item['object_ref']}` [{item['status']}] {item['text']}")


def _append_missing_lines(lines: list[str], items: list[dict[str, str]]) -> None:
    if not items:
        lines.append("- missing evidence 없음")
        return
    for item in items:
        lines.append(f"- `{item['id']}` [{item['status']}] {item['text']}")


def _safe_id(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("._") or "evidence_matrix_row"
