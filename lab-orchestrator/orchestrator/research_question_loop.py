"""On-demand research question loop for feature-first CEML_RA usage.

This loop turns a user question into a reusable research memory update:
answer artifact, memory note, optional question-based work package draft,
research_thread patch, and optional live Graphiti/Qdrant memory writes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from orchestrator.model_profiles import profile_manager
from orchestrator.research_thread import (
    load_research_thread,
    normalize_research_thread,
    resolve_artifacts_dir,
    utc_now,
    validate_research_thread,
)
from orchestrator.research_thread_patch import preview_or_apply_research_thread_patch
from orchestrator.research_weekly_loop import (
    KgSearch,
    GraphitiIngest,
    QdrantUpsert,
    SourceSearch,
    build_citations,
    build_recommended_checks,
    build_reuse_provenance,
    build_skipped_live_write_results,
    build_source_availability,
    build_weak_or_deferred_claims,
    collect_live_store_mutations,
    collect_thread_memory,
    collect_weekly_sources,
    default_query_for_thread,
    load_previous_memory_notes,
    memory_note_thread_dir,
    render_memory_note_markdown,
    run_memory_preflight,
    status_from_live_writes,
    thread_focus_label,
    write_live_memory,
)


SCHEMA_VERSION = 1
BUILDER_NAME = "research_question_loop_v0"
QUESTION_RUNS_DIR = "research_question_runs"
WORK_PACKAGE_DRAFTS_DIR = "research_work_package_drafts"

Synthesizer = Callable[..., Awaitable[str]]


@dataclass(frozen=True)
class QuestionLoopPaths:
    run_json_path: Path
    run_markdown_path: Path
    memory_json_path: Path
    memory_markdown_path: Path
    work_package_json_path: Path
    work_package_markdown_path: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "run_json_path": str(self.run_json_path),
            "run_markdown_path": str(self.run_markdown_path),
            "memory_json_path": str(self.memory_json_path),
            "memory_markdown_path": str(self.memory_markdown_path),
            "work_package_json_path": str(self.work_package_json_path),
            "work_package_markdown_path": str(self.work_package_markdown_path),
        }


def question_runs_thread_dir(thread_id: str, artifacts_dir: Path | None = None) -> Path:
    return resolve_artifacts_dir(artifacts_dir) / QUESTION_RUNS_DIR / thread_id


def work_package_drafts_thread_dir(thread_id: str, artifacts_dir: Path | None = None) -> Path:
    return resolve_artifacts_dir(artifacts_dir) / WORK_PACKAGE_DRAFTS_DIR / thread_id


def question_loop_paths(
    *,
    thread_id: str,
    run_id: str,
    memory_note_id: str,
    work_package_id: str,
    artifacts_dir: Path | None = None,
) -> QuestionLoopPaths:
    return QuestionLoopPaths(
        run_json_path=question_runs_thread_dir(thread_id, artifacts_dir) / f"{run_id}.json",
        run_markdown_path=question_runs_thread_dir(thread_id, artifacts_dir) / f"{run_id}.md",
        memory_json_path=memory_note_thread_dir(thread_id, artifacts_dir) / f"{memory_note_id}.json",
        memory_markdown_path=memory_note_thread_dir(thread_id, artifacts_dir) / f"{memory_note_id}.md",
        work_package_json_path=work_package_drafts_thread_dir(thread_id, artifacts_dir) / f"{work_package_id}.json",
        work_package_markdown_path=work_package_drafts_thread_dir(thread_id, artifacts_dir) / f"{work_package_id}.md",
    )


async def preview_or_run_question_loop(
    *,
    thread_id: str,
    question: str,
    artifacts_dir: Path | None = None,
    execute: bool = False,
    use_live_memory: bool = True,
    use_llm: bool = True,
    make_work_package: bool = True,
    days: int = 30,
    scout_limit: int = 5,
    rag_limit: int = 5,
    kg_limit: int = 5,
    created_at: str | None = None,
    scout_search: SourceSearch | None = None,
    rag_search: SourceSearch | None = None,
    kg_search: KgSearch | None = None,
    graphiti_ingest: GraphitiIngest | None = None,
    qdrant_upsert: QdrantUpsert | None = None,
    answer_synthesizer: Synthesizer | None = None,
    work_package_synthesizer: Synthesizer | None = None,
) -> dict[str, Any]:
    if days < 1 or days > 90:
        raise ValueError("days must be between 1 and 90")
    if min(scout_limit, rag_limit, kg_limit) < 0:
        raise ValueError("source limits must be non-negative")

    created_at = created_at or utc_now()
    question = question.strip()
    if not question:
        raise ValueError("question must be a non-empty string")

    thread = normalize_research_thread(load_research_thread(thread_id, artifacts_dir=artifacts_dir))
    validate_research_thread(thread)
    preflight_report = await run_memory_preflight(thread_id=thread_id, artifacts_dir=artifacts_dir)

    query = question or default_query_for_thread(thread_id)
    run_id = build_question_run_id(thread_id=thread_id, question=question, created_at=created_at)
    memory_note_id = build_question_memory_note_id(thread_id=thread_id, run_id=run_id)
    work_package_id = build_work_package_id(thread_id=thread_id, run_id=run_id, question=question)
    paths = question_loop_paths(
        thread_id=thread_id,
        run_id=run_id,
        memory_note_id=memory_note_id,
        work_package_id=work_package_id,
        artifacts_dir=artifacts_dir,
    )

    prior_notes = load_previous_memory_notes(thread_id=thread_id, artifacts_dir=artifacts_dir, limit=5)
    thread_memory = collect_thread_memory(thread, limit=10)
    source_bundle = await collect_weekly_sources(
        query=query,
        days=days,
        scout_limit=scout_limit,
        rag_limit=rag_limit,
        kg_limit=kg_limit,
        scout_search=scout_search,
        rag_search=rag_search,
        kg_search=kg_search,
    )
    evidence_sources = source_bundle["scout"] + source_bundle["rag"] + source_bundle["kg"]
    citations = build_citations(prior_notes, thread_memory, evidence_sources)
    reuse_provenance = build_reuse_provenance(prior_notes, source_bundle)
    weak_or_deferred_claims = build_weak_or_deferred_claims(source_bundle)
    recommended_checks = build_recommended_checks(thread, source_bundle)

    answer = await synthesize_question_answer(
        thread=thread,
        question=question,
        citations=citations,
        prior_notes=prior_notes,
        thread_memory=thread_memory,
        source_bundle=source_bundle,
        weak_or_deferred_claims=weak_or_deferred_claims,
        use_llm=use_llm,
        synthesizer=answer_synthesizer,
    )
    work_package_draft = None
    work_package_markdown = ""
    if make_work_package:
        work_package_draft = await synthesize_work_package_draft(
            thread=thread,
            question=question,
            run_id=run_id,
            work_package_id=work_package_id,
            answer=answer,
            citations=citations,
            source_bundle=source_bundle,
            recommended_checks=recommended_checks,
            created_at=created_at,
            use_llm=use_llm,
            synthesizer=work_package_synthesizer,
            artifact_ref=str(paths.work_package_markdown_path),
        )
        work_package_markdown = render_work_package_draft_markdown(work_package_draft)

    memory_note = build_question_memory_note(
        thread=thread,
        run_id=run_id,
        memory_note_id=memory_note_id,
        question=question,
        created_at=created_at,
        days=days,
        answer=answer,
        citations=citations,
        reuse_provenance=reuse_provenance,
        thread_memory=thread_memory,
        source_bundle=source_bundle,
        weak_or_deferred_claims=weak_or_deferred_claims,
        recommended_checks=recommended_checks,
        work_package_draft=work_package_draft,
        artifact_ref=str(paths.memory_markdown_path),
    )
    memory_markdown = render_memory_note_markdown(memory_note)

    live_write_results = build_skipped_live_write_results(use_live_memory=use_live_memory, execute=execute)
    if execute and use_live_memory:
        live_write_results = await write_live_memory(
            thread_id=thread_id,
            memory_note=memory_note,
            memory_markdown=memory_markdown,
            memory_artifact_ref=str(paths.memory_markdown_path),
            graphiti_ingest=graphiti_ingest,
            qdrant_upsert=qdrant_upsert,
            graphiti_agent_name=BUILDER_NAME,
            graphiti_user_message=f"Accumulate on-demand research answer for {thread_id}.",
        )

    source_availability = build_source_availability(
        source_bundle=source_bundle,
        live_write_results=live_write_results,
        preflight_report=preflight_report,
    )
    thread_patch = build_question_thread_patch(
        thread_id=thread_id,
        run_id=run_id,
        question=question,
        answer=answer,
        memory_note=memory_note,
        paths=paths,
        work_package_draft=work_package_draft,
        live_write_results=live_write_results,
    )
    thread_patch_result = preview_or_apply_research_thread_patch(
        thread_id=thread_id,
        patch=thread_patch,
        artifacts_dir=artifacts_dir,
        execute=execute,
        created_at=created_at,
    )
    status = status_from_live_writes(live_write_results) if execute else "would_run"

    run_record = {
        "schema_version": SCHEMA_VERSION,
        "builder": BUILDER_NAME,
        "status": status,
        "dry_run": not execute,
        "thread_id": thread_id,
        "run_id": run_id,
        "memory_note_id": memory_note_id,
        "question": question,
        "query": query,
        "period_days": days,
        "created_at": created_at,
        "answer": answer,
        "memory_note": memory_note,
        "work_package_draft": work_package_draft,
        "thread_patch": thread_patch,
        "thread_patch_result": thread_patch_result,
        "source_availability": source_availability,
        "preflight_summary": preflight_report["summary"],
        "preflight_report": preflight_report,
        "source_errors": source_bundle["errors"],
        "live_write_results": live_write_results,
        "live_store_mutations": collect_live_store_mutations(live_write_results),
    }
    run_markdown = render_question_run_markdown(run_record)

    artifact_mutations: list[dict[str, str]] = []
    if execute:
        paths.run_json_path.parent.mkdir(parents=True, exist_ok=True)
        paths.memory_json_path.parent.mkdir(parents=True, exist_ok=True)
        paths.run_json_path.write_text(
            json.dumps(run_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths.run_markdown_path.write_text(run_markdown, encoding="utf-8")
        paths.memory_json_path.write_text(
            json.dumps(memory_note, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths.memory_markdown_path.write_text(memory_markdown, encoding="utf-8")
        artifact_mutations.extend([
            {"type": "question_run_json", "path": str(paths.run_json_path)},
            {"type": "question_run_markdown", "path": str(paths.run_markdown_path)},
            {"type": "question_memory_note_json", "path": str(paths.memory_json_path)},
            {"type": "question_memory_note_markdown", "path": str(paths.memory_markdown_path)},
        ])
        if work_package_draft is not None:
            paths.work_package_json_path.parent.mkdir(parents=True, exist_ok=True)
            paths.work_package_json_path.write_text(
                json.dumps(work_package_draft, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            paths.work_package_markdown_path.write_text(work_package_markdown, encoding="utf-8")
            artifact_mutations.extend([
                {"type": "question_work_package_json", "path": str(paths.work_package_json_path)},
                {"type": "question_work_package_markdown", "path": str(paths.work_package_markdown_path)},
            ])

    return {
        **run_record,
        **paths.as_dict(),
        "preview_markdown": run_markdown,
        "memory_note_markdown": memory_markdown,
        "work_package_markdown": work_package_markdown,
        "artifact_mutations": artifact_mutations,
    }


async def synthesize_question_answer(
    *,
    thread: dict[str, Any],
    question: str,
    citations: list[dict[str, str]],
    prior_notes: list[dict[str, Any]],
    thread_memory: list[dict[str, Any]],
    source_bundle: dict[str, Any],
    weak_or_deferred_claims: list[dict[str, Any]],
    use_llm: bool,
    synthesizer: Synthesizer | None = None,
) -> dict[str, Any]:
    fallback = fallback_question_answer(
        thread=thread,
        question=question,
        citations=citations,
        prior_notes=prior_notes,
        thread_memory=thread_memory,
        source_bundle=source_bundle,
        weak_or_deferred_claims=weak_or_deferred_claims,
        reason="llm_disabled" if not use_llm else "llm_unavailable",
    )
    if not use_llm:
        return fallback
    try:
        model = _model_for_agent("literature")
        text = await (synthesizer or _generate_answer)(
            system_prompt=QUESTION_ANSWER_SYSTEM_PROMPT,
            user_prompt=build_question_answer_prompt(
                thread=thread,
                question=question,
                citations=citations,
                prior_notes=prior_notes,
                thread_memory=thread_memory,
                source_bundle=source_bundle,
                weak_or_deferred_claims=weak_or_deferred_claims,
            ),
            model=model,
            temperature=0.2,
        )
        if _looks_like_llm_error(text):
            raise RuntimeError(text[:300])
        return {
            "synthesis_mode": "llm",
            "synthesis_model": model or "default",
            "text": text.strip(),
            "citation_refs": [item["id"] for item in citations[:10]],
            "fresh_evidence": {
                "scout": source_bundle["scout"],
                "rag": source_bundle["rag"],
                "kg": source_bundle["kg"],
            },
            "guardrails": QUESTION_GUARDRAILS,
        }
    except Exception as exc:
        fallback["synthesis_error"] = str(exc)
        return fallback


async def synthesize_work_package_draft(
    *,
    thread: dict[str, Any],
    question: str,
    run_id: str,
    work_package_id: str,
    answer: dict[str, Any],
    citations: list[dict[str, str]],
    source_bundle: dict[str, Any],
    recommended_checks: list[dict[str, Any]],
    created_at: str,
    use_llm: bool,
    synthesizer: Synthesizer | None = None,
    artifact_ref: str,
) -> dict[str, Any]:
    fallback_text = fallback_work_package_text(
        thread=thread,
        question=question,
        answer=answer,
        recommended_checks=recommended_checks,
    )
    synthesis = {
        "synthesis_mode": "fallback",
        "synthesis_reason": "llm_disabled" if not use_llm else "llm_unavailable",
        "synthesis_model": "",
        "text": fallback_text,
    }
    if use_llm:
        try:
            model = _model_for_agent("project")
            text = await (synthesizer or _generate_answer)(
                system_prompt=WORK_PACKAGE_SYSTEM_PROMPT,
                user_prompt=build_work_package_prompt(
                    thread=thread,
                    question=question,
                    answer=answer,
                    citations=citations,
                    source_bundle=source_bundle,
                    recommended_checks=recommended_checks,
                ),
                model=model,
                temperature=0.2,
            )
            if _looks_like_llm_error(text):
                raise RuntimeError(text[:300])
            synthesis = {
                "synthesis_mode": "llm",
                "synthesis_reason": "",
                "synthesis_model": model or "default",
                "text": text.strip(),
            }
        except Exception as exc:
            synthesis["synthesis_error"] = str(exc)

    source_refs = [item["id"] for item in citations[:10]]
    evidence_sources = source_bundle["scout"] + source_bundle["rag"] + source_bundle["kg"]
    return {
        "schema_version": SCHEMA_VERSION,
        "builder": BUILDER_NAME,
        "work_package_id": work_package_id,
        "run_id": run_id,
        "thread_id": thread["thread_id"],
        "topic": thread["topic"],
        "created_at": created_at,
        "artifact_ref": artifact_ref,
        "question": question,
        "objective": f"질문 `{question}`에 대한 다음 연구 실행 단위를 만든다.",
        "synthesis": synthesis,
        "source_refs": source_refs,
        "fresh_evidence_refs": [item["citation"] for item in evidence_sources[:8]],
        "recommended_checks": recommended_checks,
        "tasks": build_work_package_tasks(question=question, recommended_checks=recommended_checks),
        "deliverables": [
            "근거 경계가 명시된 짧은 연구 메모",
            "다음 run에서 검증할 citation 목록",
            "research_thread에 남길 next_action 후보",
        ],
        "stop_conditions": [
            "제공된 citation 밖의 확정 주장을 해야 하면 멈춘다.",
            "새 PDF/DB ingest가 필요하면 별도 source intake 작업으로 분리한다.",
            "Slack, scheduler, background daemon이 필요하면 이번 v0 범위 밖으로 둔다.",
        ],
        "live_store_mutations": [],
    }


def build_question_memory_note(
    *,
    thread: dict[str, Any],
    run_id: str,
    memory_note_id: str,
    question: str,
    created_at: str,
    days: int,
    answer: dict[str, Any],
    citations: list[dict[str, str]],
    reuse_provenance: list[dict[str, Any]],
    thread_memory: list[dict[str, Any]],
    source_bundle: dict[str, Any],
    weak_or_deferred_claims: list[dict[str, Any]],
    recommended_checks: list[dict[str, Any]],
    work_package_draft: dict[str, Any] | None,
    artifact_ref: str,
) -> dict[str, Any]:
    evidence_sources = source_bundle["scout"] + source_bundle["rag"] + source_bundle["kg"]
    summary = first_meaningful_line(answer["text"])
    next_questions = build_question_next_questions(
        question=question,
        answer=answer,
        thread=thread,
        work_package_draft=work_package_draft,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "builder": BUILDER_NAME,
        "memory_note_id": memory_note_id,
        "run_id": run_id,
        "thread_id": thread["thread_id"],
        "topic": thread["topic"],
        "created_at": created_at,
        "period_days": days,
        "query": question,
        "artifact_ref": artifact_ref,
        "summary": summary,
        "answer": answer,
        "judgment_change": {
            "summary": summary,
            "decision_delta": "사용자 질문에 대한 현재 기억 기반 답변과 다음 실행 단위를 남겼다.",
            "support_level": "bounded_on_demand_synthesis",
            "memory_refs": [entry["citation"] for entry in reuse_provenance[:5]],
            "evidence_refs": [item["citation"] for item in evidence_sources[:5]],
        },
        "reuse_provenance": reuse_provenance,
        "memory_reuse_sources": source_bundle.get("memory_reuse_sources", {"rag": [], "kg": []}),
        "weak_or_deferred_claims": weak_or_deferred_claims,
        "recommended_checks": recommended_checks,
        "claims": [
            {
                "id": f"{memory_note_id}.answer",
                "text": summary,
                "source_refs": [citation["id"] for citation in citations[:10]],
            }
        ],
        "next_questions": next_questions,
        "citations": citations,
        "reused_memory_count": len(reuse_provenance) + len(thread_memory),
        "new_evidence_count": len(evidence_sources),
        "work_package_ref": (work_package_draft or {}).get("artifact_ref", ""),
        "quality_version": "research_question_loop_v0",
        "evidence_separation_version": "weekly_loop_evidence_separation_v1",
        "live_store_mutations": [],
    }


def build_question_thread_patch(
    *,
    thread_id: str,
    run_id: str,
    question: str,
    answer: dict[str, Any],
    memory_note: dict[str, Any],
    paths: QuestionLoopPaths,
    work_package_draft: dict[str, Any] | None,
    live_write_results: dict[str, Any],
) -> dict[str, Any]:
    artifact_refs = [str(paths.run_markdown_path), str(paths.memory_markdown_path)]
    if work_package_draft is not None:
        artifact_refs.append(str(paths.work_package_markdown_path))
    claim = memory_note["claims"][0]
    live_summary = json.dumps(
        {
            "graphiti": live_write_results["graphiti"]["status"],
            "qdrant": live_write_results["qdrant"]["status"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    next_action_text = memory_note["next_questions"][0]
    if work_package_draft is not None:
        next_action_text = f"Work package `{work_package_draft['work_package_id']}`를 실행하고 결과를 다음 질문 loop에 재사용한다."
    return {
        "schema_version": 2,
        "thread_id": thread_id,
        "research_state": "on_demand_question_loop_updated",
        "append": {
            "claims": [
                {
                    "id": f"question_loop.{run_id}.answer",
                    "text": claim["text"],
                    "status": "reviewed_signal",
                    "authority_state": "reviewed_artifact",
                    "review_state": "reviewed",
                    "support_state": "bounded_synthesis",
                    "source_refs": claim["source_refs"],
                    "artifact_refs": artifact_refs,
                    "metadata": {"question_loop_run_id": run_id, "question": question},
                }
            ],
            "evidence": [
                {
                    "id": f"question_loop.{run_id}.evidence",
                    "text": (
                        f"On-demand question loop `{run_id}`는 질문 `{question}`에 대해 "
                        f"{memory_note['reused_memory_count']}개의 기존 기억과 "
                        f"{memory_note['new_evidence_count']}개의 새 근거 신호를 연결했다."
                    ),
                    "status": "reviewed_signal",
                    "authority_state": "reviewed_artifact",
                    "review_state": "reviewed",
                    "support_state": "bounded_synthesis",
                    "source_refs": claim["source_refs"],
                    "artifact_refs": artifact_refs,
                    "metadata": {"question_loop_run_id": run_id},
                }
            ],
            "decisions": [
                {
                    "id": f"question_loop.{run_id}.decision.stored",
                    "text": f"On-demand 질문 답변과 reusable memory note를 저장했다. Live memory write 결과: {live_summary}",
                    "status": "accepted",
                    "authority_state": "reviewed_artifact",
                    "review_state": "reviewed",
                    "support_state": "bounded_synthesis",
                    "artifact_refs": artifact_refs,
                    "metadata": {"question_loop_run_id": run_id, "live_write_results": live_write_results},
                }
            ],
            "next_actions": [
                {
                    "id": f"question_loop.{run_id}.next_action",
                    "text": next_action_text,
                    "status": "open",
                    "authority_state": "thread_local",
                    "review_state": "reviewed",
                    "support_state": "bounded_synthesis",
                    "artifact_refs": artifact_refs,
                    "metadata": {"question_loop_run_id": run_id},
                }
            ],
        },
        "metadata": {
            "last_question_loop": {
                "run_id": run_id,
                "memory_note_id": memory_note["memory_note_id"],
                "run_markdown_path": str(paths.run_markdown_path),
                "memory_markdown_path": str(paths.memory_markdown_path),
                "work_package_markdown_path": str(paths.work_package_markdown_path if work_package_draft else ""),
                "live_write_results": live_write_results,
                "synthesis_mode": answer["synthesis_mode"],
            }
        },
        "live_store_mutations": [],
    }


def render_question_run_markdown(run: dict[str, Any]) -> str:
    answer = run["answer"]
    memory_note = run["memory_note"]
    source_availability = run["source_availability"]
    lines = [
        f"# On-demand Research Question Loop: {run['thread_id']}",
        "",
        f"- Run ID: `{run['run_id']}`",
        f"- 생성 시각: `{run['created_at']}`",
        f"- 질문: {run['question']}",
        f"- 상태: `{run['status']}`",
        f"- Synthesis: `{answer['synthesis_mode']}`",
        "",
        "## 답변",
        "",
        answer["text"],
        "",
        "## 사용한 기억",
        "",
    ]
    reuse = memory_note.get("reuse_provenance", [])
    if not reuse:
        lines.append("- 재사용된 prior memory note 없음")
    for item in reuse:
        stores = ", ".join(item.get("reused_from", []))
        lines.append(f"- `{item['citation']}` 출처 {stores}: {item.get('used_for', '')}")
    lines.extend(["", "## 새 외부 근거", ""])
    for label in ("scout", "rag", "kg"):
        items = memory_note.get("answer", {}).get("fresh_evidence", {}).get(label, [])
        lines.append(f"### {label.upper()}")
        if not items:
            lines.append("- 새 근거 없음")
        for item in items:
            lines.append(f"- `{item['citation']}` **{item['title']}**: {item['text']}")
        lines.append("")
    lines.extend(["## 약한 근거와 보류할 주장", ""])
    for item in memory_note.get("weak_or_deferred_claims", []):
        lines.append(f"- `{item['id']}` {item['text']} ({item['reason']})")
    lines.extend(["", "## Work Package Draft", ""])
    if run.get("work_package_draft"):
        draft = run["work_package_draft"]
        lines.append(f"- Work package ID: `{draft['work_package_id']}`")
        lines.append(f"- Artifact ref: `{draft['artifact_ref']}`")
        lines.append("- 다음 실행 단위가 별도 draft artifact로 저장된다.")
    else:
        lines.append("- 생성하지 않음")
    lines.extend(["", "## 다음 질문/행동", ""])
    lines.extend(f"- {item}" for item in memory_note.get("next_questions", []))
    lines.extend(["", "## Source Availability", ""])
    lines.append(f"- fresh_evidence_count: `{source_availability.get('fresh_evidence_count')}`")
    lines.append(f"- memory_reuse_count: `{source_availability.get('memory_reuse_count')}`")
    reason = source_availability.get("fresh_evidence_missing_reason")
    if reason:
        lines.append(f"- fresh_evidence_missing_reason: `{reason}`")
    lines.extend(["", "## Live Memory Write", ""])
    for store, result in run["live_write_results"].items():
        text = result.get("error") or result.get("reason") or ""
        suffix = f" — {text}" if text else ""
        lines.append(f"- {store}: `{result.get('status')}`{suffix}")
    return "\n".join(lines) + "\n"


def render_work_package_draft_markdown(draft: dict[str, Any]) -> str:
    lines = [
        f"# 질문 기반 Work Package Draft: {draft['thread_id']}",
        "",
        f"- Work package ID: `{draft['work_package_id']}`",
        f"- Run ID: `{draft['run_id']}`",
        f"- 생성 시각: `{draft['created_at']}`",
        f"- 질문: {draft['question']}",
        f"- Synthesis: `{draft['synthesis']['synthesis_mode']}`",
        "",
        "## 목적",
        "",
        draft["objective"],
        "",
        "## 실행 초안",
        "",
        draft["synthesis"]["text"],
        "",
        "## 작업 단위",
        "",
    ]
    for task in draft["tasks"]:
        lines.append(f"- `{task['id']}` {task['text']}")
    lines.extend(["", "## 산출물", ""])
    lines.extend(f"- {item}" for item in draft["deliverables"])
    lines.extend(["", "## Stop Conditions", ""])
    lines.extend(f"- {item}" for item in draft["stop_conditions"])
    lines.extend(["", "## Source Refs", ""])
    if not draft["source_refs"]:
        lines.append("- 없음")
    lines.extend(f"- `{item}`" for item in draft["source_refs"])
    return "\n".join(lines) + "\n"


def build_question_answer_prompt(
    *,
    thread: dict[str, Any],
    question: str,
    citations: list[dict[str, str]],
    prior_notes: list[dict[str, Any]],
    thread_memory: list[dict[str, Any]],
    source_bundle: dict[str, Any],
    weak_or_deferred_claims: list[dict[str, Any]],
) -> str:
    payload = {
        "thread": {
            "thread_id": thread["thread_id"],
            "topic": thread["topic"],
            "research_state": thread["research_state"],
            "focus": thread_focus_label(thread),
        },
        "question": question,
        "citations": citations[:12],
        "prior_memory_notes": [
            {
                "memory_note_id": item.get("memory_note_id"),
                "summary": item.get("summary"),
                "artifact_ref": item.get("artifact_ref"),
            }
            for item in prior_notes[:5]
        ],
        "thread_memory": thread_memory[:8],
        "fresh_evidence": {
            "scout": source_bundle["scout"][:5],
            "rag": source_bundle["rag"][:5],
            "kg": source_bundle["kg"][:5],
        },
        "memory_reuse_sources": source_bundle.get("memory_reuse_sources", {}),
        "weak_or_deferred_claims": weak_or_deferred_claims,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def build_work_package_prompt(
    *,
    thread: dict[str, Any],
    question: str,
    answer: dict[str, Any],
    citations: list[dict[str, str]],
    source_bundle: dict[str, Any],
    recommended_checks: list[dict[str, Any]],
) -> str:
    payload = {
        "thread": {
            "thread_id": thread["thread_id"],
            "topic": thread["topic"],
            "research_state": thread["research_state"],
        },
        "question": question,
        "answer": answer,
        "citations": citations[:12],
        "fresh_evidence_refs": [
            item["citation"]
            for item in source_bundle["scout"] + source_bundle["rag"] + source_bundle["kg"]
        ][:10],
        "recommended_checks": recommended_checks,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def fallback_question_answer(
    *,
    thread: dict[str, Any],
    question: str,
    citations: list[dict[str, str]],
    prior_notes: list[dict[str, Any]],
    thread_memory: list[dict[str, Any]],
    source_bundle: dict[str, Any],
    weak_or_deferred_claims: list[dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    evidence_sources = source_bundle["scout"] + source_bundle["rag"] + source_bundle["kg"]
    memory_count = len(prior_notes) + len(thread_memory)
    if evidence_sources:
        basis = f"새 근거 `{evidence_sources[0]['citation']}`를 포함해 {len(evidence_sources)}개의 fresh evidence를 확인했다."
    elif memory_count:
        basis = f"새 외부 근거는 없고 기존 기억 {memory_count}개를 기준으로 답한다."
    else:
        basis = "사용 가능한 기존 기억과 새 근거가 제한적이므로 답변은 보수적으로 유지한다."
    weak = weak_or_deferred_claims[0]["text"] if weak_or_deferred_claims else "출처 없는 확정 주장은 만들지 않는다."
    citation_text = ", ".join(item["id"] for item in citations[:6]) or "citation 없음"
    text = (
        f"질문: {question}\n\n"
        f"현재 `{thread['thread_id']}` 기억 기준 답변은 다음과 같다. {basis} "
        f"따라서 지금은 제공된 citation 범위에서 다음 실행 질문을 좁히는 것이 우선이다.\n\n"
        f"- 근거 refs: {citation_text}\n"
        f"- 보류할 주장: {weak}\n"
        "- 다음 행동: 아래 work package draft에서 검증 가능한 작은 작업 단위로 분리한다."
    )
    return {
        "synthesis_mode": "fallback",
        "synthesis_reason": reason,
        "synthesis_model": "",
        "text": text,
        "citation_refs": [item["id"] for item in citations[:10]],
        "fresh_evidence": {
            "scout": source_bundle["scout"],
            "rag": source_bundle["rag"],
            "kg": source_bundle["kg"],
        },
        "guardrails": QUESTION_GUARDRAILS,
    }


def fallback_work_package_text(
    *,
    thread: dict[str, Any],
    question: str,
    answer: dict[str, Any],
    recommended_checks: list[dict[str, Any]],
) -> str:
    check_text = recommended_checks[0]["text"] if recommended_checks else "가장 관련 있는 citation을 하나 골라 원문/메모와 대조한다."
    return (
        f"`{thread['thread_id']}` 질문 `{question}`의 다음 실행 단위는 답변에서 사용한 근거를 하나씩 검증하는 것이다.\n\n"
        f"1. 첫 확인 대상: {check_text}\n"
        "2. 답변에서 확정한 내용과 보류한 내용을 분리한다.\n"
        "3. 다음 question loop가 재사용할 수 있도록 claim boundary와 citation refs를 짧게 남긴다.\n\n"
        f"답변 요약: {first_meaningful_line(answer['text'])}"
    )


def build_work_package_tasks(*, question: str, recommended_checks: list[dict[str, Any]]) -> list[dict[str, str]]:
    tasks = [
        {
            "id": "task.claim_boundary",
            "text": f"질문 `{question}`에 대한 답변에서 확정 가능한 주장과 보류할 주장을 분리한다.",
        },
        {
            "id": "task.citation_review",
            "text": "답변의 citation refs가 실제 근거 문장 또는 memory note에 대응하는지 확인한다.",
        },
        {
            "id": "task.next_memory",
            "text": "다음 질문 loop가 재사용할 수 있는 한 문장 memory note 후보를 작성한다.",
        },
    ]
    for idx, check in enumerate(recommended_checks[:2], start=1):
        tasks.append({"id": f"task.recommended_check.{idx}", "text": check["text"]})
    return tasks[:5]


def build_question_next_questions(
    *,
    question: str,
    answer: dict[str, Any],
    thread: dict[str, Any],
    work_package_draft: dict[str, Any] | None,
) -> list[str]:
    questions = []
    if work_package_draft is not None:
        questions.append(f"`{work_package_draft['work_package_id']}` 실행 후 `{question}`에 대한 답변을 어떻게 수정해야 하는가?")
    questions.append(f"`{question}`에 답하는 데 가장 약한 citation은 무엇이고, 어떤 source intake가 필요한가?")
    questions.append(f"{thread_focus_label(thread)}에서 다음으로 확인해야 할 반례 또는 비교 기준은 무엇인가?")
    if answer["synthesis_mode"] == "fallback":
        questions.append("LLM synthesis 실패/비활성 상태에서 만든 fallback 답변을 어떤 근거로 보강해야 하는가?")
    return questions[:4]


def first_meaningful_line(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip(" -#`")
        if cleaned:
            return cleaned[:500]
    return "질문 답변 요약 없음"


def build_question_run_id(*, thread_id: str, question: str, created_at: str) -> str:
    return _safe_id(f"question_{thread_id}_{created_at}_{question}")[:96]


def build_question_memory_note_id(*, thread_id: str, run_id: str) -> str:
    return _safe_id(f"memory_note_{thread_id}_{run_id}")[:120]


def build_work_package_id(*, thread_id: str, run_id: str, question: str) -> str:
    slug = _safe_id(question).lower()[:48] or "question_work_package"
    digest = _safe_id(run_id)[-12:]
    return _safe_id(f"work_package_{thread_id}_{slug}_{digest}")[:120]


async def _generate_answer(**kwargs: Any) -> str:
    from llm.pool import generate_answer

    return await generate_answer(**kwargs)


def _model_for_agent(agent_name: str) -> str | None:
    model, model_heavy = profile_manager.get_models(agent_name)
    return model_heavy or model


def _looks_like_llm_error(text: str) -> bool:
    cleaned = (text or "").strip()
    return not cleaned or cleaned.startswith("[ERROR]")


def _safe_id(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("._") or "question_loop"


QUESTION_GUARDRAILS = [
    "제공된 citation 밖의 확정 주장을 만들지 않는다.",
    "내부 memory note와 새 외부 evidence를 구분한다.",
    "약한 근거와 다음 검증 질문을 분리한다.",
    "사용자가 읽는 설명은 한국어로 작성한다.",
]

QUESTION_ANSWER_SYSTEM_PROMPT = """너는 CEML_RA의 on-demand research colleague다.
입력 JSON에 포함된 research_thread, prior memory, fresh evidence, citation만 사용해 한국어로 답한다.
제공된 citation 밖의 확정 주장을 만들지 말고, 약한 근거와 다음 실행 질문을 분리한다.
출력은 Markdown으로 작성하되 반드시 '현재 답변', '근거', '보류할 주장', '다음 행동'을 포함한다."""

WORK_PACKAGE_SYSTEM_PROMPT = """너는 CEML_RA의 project subagent다.
사용자 질문과 제공된 답변/citation만 사용해 다음 연구 실행 단위를 한국어 Work Package로 만든다.
새 연구값을 상상하지 말고, 검증 작업, 필요한 citation review, stop condition, 다음 artifact 형태를 분리한다."""
