"""Plan the next research work package from durable CEML_RA memory.

This module turns an existing proposal seed plus a research_thread into a
reviewable execution packet. It does not write new research results, mutate the
research_thread, call LLMs, or touch live Slack/Scout/KG/RAG/runtime stores.
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
PLANNER_NAME = "research_work_package_planner_v1"
WORK_PACKAGES_DIR = "research_work_packages"


@dataclass(frozen=True)
class WorkPackagePlanPaths:
    json_path: Path
    markdown_path: Path
    patch_preview_path: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "json_path": str(self.json_path),
            "markdown_path": str(self.markdown_path),
            "patch_preview_path": str(self.patch_preview_path),
        }


def load_proposal_seed(path: Path) -> dict[str, Any]:
    try:
        seed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"proposal seed is not valid JSON: {path}") from exc
    validate_proposal_seed(seed)
    return seed


def validate_proposal_seed(seed: dict[str, Any]) -> None:
    if not isinstance(seed, dict):
        raise ValueError("proposal seed must be a JSON object")
    for field in ("topic_id", "work_packages", "next_actions"):
        if field not in seed:
            raise ValueError(f"proposal seed missing required field: {field}")
    if not isinstance(seed["topic_id"], str) or not seed["topic_id"].strip():
        raise ValueError("proposal seed topic_id must be a non-empty string")
    if not isinstance(seed["work_packages"], list) or not seed["work_packages"]:
        raise ValueError("proposal seed work_packages must be a non-empty list")
    for idx, item in enumerate(seed["work_packages"]):
        if not isinstance(item, dict):
            raise ValueError(f"proposal seed work_packages[{idx}] must be an object")
        for field in ("title", "output"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"proposal seed work_packages[{idx}].{field} must be a non-empty string")
    if not isinstance(seed["next_actions"], list):
        raise ValueError("proposal seed next_actions must be a list")


def work_packages_dir(artifacts_dir: Path | None = None) -> Path:
    return resolve_artifacts_dir(artifacts_dir) / WORK_PACKAGES_DIR


def work_package_plan_paths(
    *,
    thread_id: str,
    work_package_id: str,
    artifacts_dir: Path | None = None,
) -> WorkPackagePlanPaths:
    base = work_packages_dir(artifacts_dir)
    stem = f"{thread_id}_{work_package_id}_execution_packet"
    return WorkPackagePlanPaths(
        json_path=base / f"{stem}.json",
        markdown_path=base / f"{stem}.md",
        patch_preview_path=base / f"{thread_id}_{work_package_id}_thread_patch_preview.json",
    )


def build_work_package_execution_packet(
    *,
    proposal_seed: dict[str, Any],
    research_thread: dict[str, Any],
    proposal_seed_path: Path,
    created_at: str | None = None,
) -> dict[str, Any]:
    validate_proposal_seed(proposal_seed)
    validate_research_thread(research_thread)
    if proposal_seed["topic_id"] != research_thread["thread_id"]:
        raise ValueError(
            f"proposal seed topic_id does not match research_thread: "
            f"{proposal_seed['topic_id']} != {research_thread['thread_id']}"
        )

    generated_at = created_at or utc_now()
    selected, selection = select_next_work_package(proposal_seed, research_thread)
    work_package_id = work_package_id_from_title(selected["title"])
    artifact_contract = artifact_contract_for_work_package(
        topic_id=proposal_seed["topic_id"],
        work_package_id=work_package_id,
        work_package=selected,
    )
    claim_boundaries = _claim_boundaries(proposal_seed)
    missing_evidence = _missing_evidence_for_work_package(proposal_seed, selected)
    stop_conditions = _stop_conditions_for_work_package(work_package_id)
    patch_preview = build_thread_patch_preview(
        thread_id=research_thread["thread_id"],
        work_package_id=work_package_id,
        work_package=selected,
        proposal_seed_path=proposal_seed_path,
        artifact_contract=artifact_contract,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "planner": PLANNER_NAME,
        "generated_at": generated_at,
        "thread_id": research_thread["thread_id"],
        "topic_id": proposal_seed["topic_id"],
        "dry_run_capable": True,
        "selected_work_package": {
            "id": work_package_id,
            "title": selected["title"],
            "output": selected["output"],
        },
        "why_selected": selection["why_selected"],
        "source_artifacts": _source_artifacts(proposal_seed, proposal_seed_path),
        "artifact_contract": artifact_contract,
        "claim_boundaries": claim_boundaries,
        "missing_evidence": missing_evidence,
        "stop_conditions": stop_conditions,
        "thread_patch_preview": patch_preview,
        "live_store_mutations": [],
    }


def select_next_work_package(
    proposal_seed: dict[str, Any],
    research_thread: dict[str, Any],
) -> tuple[dict[str, str], dict[str, Any]]:
    open_next_actions = [
        item
        for item in research_thread.get("next_actions", [])
        if item.get("status") == "open"
    ]
    proposal_next_actions = [
        item
        for item in open_next_actions
        if str(item.get("id", "")).startswith("next_action.proposal_seed_artifact.")
    ]
    relevant_next_actions = proposal_next_actions or open_next_actions
    seed_next_actions = [str(item) for item in proposal_seed.get("next_actions", [])]
    scored: list[tuple[int, int, dict[str, str], list[str]]] = []
    for idx, package in enumerate(proposal_seed["work_packages"]):
        text = f"{package['title']} {package['output']}"
        package_id = work_package_id_from_title(package["title"])
        score = 0
        reasons: list[str] = []
        action_texts = [item.get("text", "") for item in relevant_next_actions] + seed_next_actions
        action_ids = [item.get("id", "") for item in relevant_next_actions]
        if "hre_intensity" in package_id and _action_mentions(action_texts + action_ids, ("hre-intensity", "hre_intensity", "HRE 사용 강도")):
            score += 12
            reasons.append("열린 next_action이 HRE-intensity table 또는 HRE 사용 강도 작업을 직접 가리킨다.")
        if "digital_twin_ml_descriptor" in package_id and _action_mentions(action_texts + action_ids, ("descriptor", "digital twin", "ML")):
            score += 8
            reasons.append("열린 next_action이 digital twin/ML descriptor table 작업을 직접 가리킨다.")
        if _contains_any(text, ("HRE", "사용 강도", "intensity")):
            score += 5
            reasons.append("proposal seed의 첫 계산 가능 공백인 HRE 사용 강도 정규화와 직접 연결된다.")
        if _contains_any(text, ("descriptor", "digital twin", "ML")):
            score += 2
            reasons.append("descriptor 기반 계산 스코핑과 연결된다.")
        if _contains_any(text, ("circularity", "recycling", "공급")):
            score += 1
            reasons.append("공급/circularity 보조 맥락과 연결된다.")
        for action in relevant_next_actions:
            overlap = _keyword_overlap(text, action.get("text", ""))
            if overlap:
                score += min(3, overlap)
                reasons.append(f"열린 next_action `{action['id']}`와 키워드가 겹친다.")
        scored.append((score, -idx, {"title": package["title"], "output": package["output"]}, reasons))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    score, _, selected, reasons = scored[0]
    if not reasons:
        reasons = ["proposal seed에 기록된 첫 번째 work package라서 v1 기본 선택으로 사용한다."]
    return selected, {
        "score": score,
        "why_selected": reasons,
        "selection_policy": "deterministic_seed_and_open_next_action_overlap",
    }


def artifact_contract_for_work_package(
    *,
    topic_id: str,
    work_package_id: str,
    work_package: dict[str, str],
) -> dict[str, Any]:
    if "hre_intensity" in work_package_id:
        return {
            "artifact_type": "hre_intensity_table",
            "recommended_output_dir": "research_value_tests/hre_intensity_table",
            "recommended_markdown_name": f"{topic_id}_hre_intensity_table.md",
            "recommended_json_name": f"{topic_id}_hre_intensity_table.json",
            "must_include": [
                "선택된 route family와 lane",
                "HRE source/type과 HRE amount value_status",
                "coercivity 근거와 Br/BHmax value_status",
                "temperature condition과 comparability status",
                "missing evidence와 next validation",
                "claim boundary와 do-not-claim 항목",
            ],
            "must_not_do": [
                "빠진 값을 실패 증거로 해석하지 않는다.",
                "Tb-Ga GBD의 Br/BHmax 값을 추정하지 않는다.",
                "recycling-linked route를 HRE-free로 주장하지 않는다.",
                "새 source search나 live KG/RAG ingest를 수행하지 않는다.",
            ],
        }
    return {
        "artifact_type": "research_work_package_artifact",
        "recommended_output_dir": f"research_value_tests/{work_package_id}",
        "recommended_markdown_name": f"{topic_id}_{work_package_id}.md",
        "recommended_json_name": f"{topic_id}_{work_package_id}.json",
        "must_include": [
            "선택된 work package의 목적",
            "입력 source artifacts",
            "claim boundary",
            "missing evidence",
            "next validation",
        ],
        "must_not_do": [
            "새 research claim을 근거 없이 채우지 않는다.",
            "live KG/RAG/Scout/runtime store를 변경하지 않는다.",
        ],
    }


def build_thread_patch_preview(
    *,
    thread_id: str,
    work_package_id: str,
    work_package: dict[str, str],
    proposal_seed_path: Path,
    artifact_contract: dict[str, Any],
) -> dict[str, Any]:
    source_ref = str(proposal_seed_path)
    return {
        "schema_version": 1,
        "thread_id": thread_id,
        "research_state": "work_package_planned",
        "append": {
            "decisions": [
                {
                    "id": f"decision.work_package_planner.{work_package_id}",
                    "text": (
                        f"Research Work Package Planner가 다음 작업으로 `{work_package['title']}`를 선택했다. "
                        "이 결정은 새 연구값을 채우는 것이 아니라 다음 artifact 작업의 실행 패킷을 구조화하기 위한 것이다."
                    ),
                    "status": "accepted",
                    "source_refs": [source_ref],
                    "confidence": "work_package_planner",
                    "tags": ["work-package-planner", "artifact-first"],
                    "metadata": {"live_store_mutations": []},
                }
            ],
            "failure_modes": [
                {
                    "id": f"failure_mode.work_package_planner.{work_package_id}.manual_research_drift",
                    "text": (
                        "후속 작업은 planner가 만든 artifact contract를 넘어 새 연구값을 임의로 채우거나, "
                        "빠진 근거를 추정하거나, live store를 변경하면 실패한다."
                    ),
                    "status": "open",
                    "source_refs": [source_ref],
                    "confidence": "work_package_planner",
                    "tags": ["work-package-planner", "anti-drift"],
                    "metadata": {"live_store_mutations": []},
                }
            ],
            "next_actions": [
                {
                    "id": f"next_action.work_package_planner.execute_{work_package_id}",
                    "text": (
                        f"`{artifact_contract['artifact_type']}` artifact를 생성하되, "
                        "planner의 claim boundary와 stop condition을 먼저 검토한다."
                    ),
                    "status": "open",
                    "source_refs": [source_ref],
                    "confidence": "work_package_planner",
                    "tags": ["work-package-planner", "next-artifact"],
                    "metadata": {
                        "artifact_contract": artifact_contract,
                        "live_store_mutations": [],
                    },
                }
            ],
        },
        "metadata": {
            "last_work_package_plan": {
                "planner": PLANNER_NAME,
                "work_package_id": work_package_id,
                "proposal_seed": source_ref,
                "live_store_mutations": [],
            }
        },
    }


def render_work_package_markdown(packet: dict[str, Any]) -> str:
    selected = packet["selected_work_package"]
    contract = packet["artifact_contract"]
    lines = [
        f"# 연구 Work Package 실행 패킷: {selected['title']}",
        "",
        f"- 생성 시각: `{packet['generated_at']}`",
        f"- Thread ID: `{packet['thread_id']}`",
        f"- 선택된 work package ID: `{selected['id']}`",
        "- 라이브 저장소 변경: 없음",
        "",
        "## 선택된 작업 패키지",
        "",
        f"- 제목: {selected['title']}",
        f"- 기대 산출물: {selected['output']}",
        "",
        "## 왜 이 작업인가",
        "",
    ]
    lines.extend(f"- {reason}" for reason in packet["why_selected"])
    lines.extend([
        "",
        "## Source Artifacts",
        "",
    ])
    for name, path in packet["source_artifacts"].items():
        lines.append(f"- `{name}`: {path}")
    lines.extend([
        "",
        "## Artifact Contract",
        "",
        f"- Artifact type: `{contract['artifact_type']}`",
        f"- 권장 출력 디렉터리: `{contract['recommended_output_dir']}`",
        f"- 권장 Markdown 파일: `{contract['recommended_markdown_name']}`",
        f"- 권장 JSON 파일: `{contract['recommended_json_name']}`",
        "",
        "### 반드시 포함할 것",
        "",
    ])
    lines.extend(f"- {item}" for item in contract["must_include"])
    lines.extend([
        "",
        "### 하지 말 것",
        "",
    ])
    lines.extend(f"- {item}" for item in contract["must_not_do"])
    lines.extend([
        "",
        "## Claim Boundaries",
        "",
    ])
    lines.extend(f"- {item}" for item in packet["claim_boundaries"])
    lines.extend([
        "",
        "## Missing Evidence",
        "",
    ])
    for gap in packet["missing_evidence"]:
        lines.append(f"- {gap['gap']}: {gap['next_validation']}")
    lines.extend([
        "",
        "## Stop Conditions",
        "",
    ])
    lines.extend(f"- {item}" for item in packet["stop_conditions"])
    lines.extend([
        "",
        "## Thread Patch Preview",
        "",
        "이 패킷은 research_thread를 직접 변경하지 않는다. 아래 patch preview를 사람이 검토한 뒤 별도 CLI로 적용할 수 있다.",
        "",
        "```json",
        json.dumps(packet["thread_patch_preview"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
    ])
    return "\n".join(lines)


def preview_or_write_work_package_plan(
    *,
    proposal_seed_path: Path,
    thread_id: str,
    artifacts_dir: Path | None = None,
    execute: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    proposal_seed = load_proposal_seed(proposal_seed_path)
    research_thread = load_research_thread(thread_id, artifacts_dir=artifacts_dir)
    packet = build_work_package_execution_packet(
        proposal_seed=proposal_seed,
        research_thread=research_thread,
        proposal_seed_path=proposal_seed_path,
        created_at=created_at,
    )
    paths = work_package_plan_paths(
        thread_id=thread_id,
        work_package_id=packet["selected_work_package"]["id"],
        artifacts_dir=artifacts_dir,
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "written" if execute else "would_write",
        "dry_run": not execute,
        "thread_id": thread_id,
        "selected_work_package_id": packet["selected_work_package"]["id"],
        **paths.as_dict(),
        "packet": packet,
        "preview_markdown": render_work_package_markdown(packet),
        "live_store_mutations": [],
    }
    if execute:
        paths.json_path.parent.mkdir(parents=True, exist_ok=True)
        paths.json_path.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths.markdown_path.write_text(render_work_package_markdown(packet), encoding="utf-8")
        paths.patch_preview_path.write_text(
            json.dumps(packet["thread_patch_preview"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result


def work_package_id_from_title(title: str) -> str:
    lower = title.lower()
    if "hre" in lower and ("사용 강도" in title or "intensity" in lower):
        return "hre_intensity_route_comparison"
    if "descriptor" in lower or "digital twin" in lower or "ml" in lower:
        return "digital_twin_ml_descriptor_table"
    if "circularity" in lower or "recycling" in lower or "공급" in title:
        return "circularity_context_note"
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", title).strip("_").lower()
    if slug:
        return slug[:64]
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]
    return f"work_package_{digest}"


def _source_artifacts(proposal_seed: dict[str, Any], proposal_seed_path: Path) -> dict[str, str]:
    refs = dict(proposal_seed.get("prior_reviewed_memory", {}))
    refs["proposal_seed"] = str(proposal_seed_path)
    return refs


def _claim_boundaries(proposal_seed: dict[str, Any]) -> list[str]:
    values = proposal_seed.get("do_not_claim", [])
    if isinstance(values, list) and values:
        return [str(item) for item in values]
    return ["새 연구 claim을 근거 없이 확정하지 않는다."]


def _missing_evidence_for_work_package(
    proposal_seed: dict[str, Any],
    work_package: dict[str, str],
) -> list[dict[str, str]]:
    missing = proposal_seed.get("missing_evidence", [])
    if not isinstance(missing, list):
        return []
    package_text = f"{work_package['title']} {work_package['output']}"
    selected = []
    for item in missing:
        if not isinstance(item, dict):
            continue
        gap_text = f"{item.get('gap', '')} {item.get('why_it_matters', '')} {item.get('next_validation', '')}"
        if _keyword_overlap(package_text, gap_text) or not selected:
            selected.append({
                "gap": str(item.get("gap", "미상 공백")),
                "why_it_matters": str(item.get("why_it_matters", "")),
                "next_validation": str(item.get("next_validation", "")),
            })
    return selected


def _stop_conditions_for_work_package(work_package_id: str) -> list[str]:
    common = [
        "새 source search, PDF extraction, LLM interpretation이 필요해지면 멈춘다.",
        "research_thread 직접 mutation이 필요해지면 patch preview만 남기고 멈춘다.",
        "Slack, runtime, Scout DB, Qdrant, Neo4j, Graphiti, KG/RAG store 변경이 필요하면 멈춘다.",
    ]
    if "hre_intensity" in work_package_id:
        return [
            "HRE 사용 강도를 하나의 숫자로 정규화하려면 추가 가정이 필요한 경우 멈춘다.",
            "Tb-Ga GBD Br/BHmax 값을 추정해야 비교가 가능해지는 경우 멈춘다.",
            "recycling-linked route를 HRE-free로 해석해야 하는 경우 멈춘다.",
            *common,
        ]
    return common


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def _action_mentions(texts: list[str], needles: tuple[str, ...]) -> bool:
    joined = " ".join(texts).lower()
    return any(needle.lower() in joined for needle in needles)


def _keyword_overlap(left: str, right: str) -> int:
    keywords = (
        "hre",
        "사용",
        "강도",
        "intensity",
        "descriptor",
        "digital",
        "ml",
        "recycling",
        "circularity",
        "br",
        "bhmax",
        "coercivity",
        "gbd",
    )
    left_lower = left.lower()
    right_lower = right.lower()
    return sum(1 for keyword in keywords if keyword in left_lower and keyword in right_lower)
