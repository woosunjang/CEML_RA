"""
Lab Orchestrator — API Server

Main FastAPI server on port 8000.
Receives chat requests, runs orchestration, returns responses.
"""

import logging
import json
import re
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from orchestrator.schemas import ChatRequest, ChatResponse
from orchestrator.graph import orchestrate, orchestrate_stream
from orchestrator.memory import memory_store
from orchestrator.router import get_all_agent_status
from agents.registry import registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SAFE_THREAD_ID = re.compile(r"^[0-9A-Za-z._-]+$")

app = FastAPI(
    title="CEML Lab Orchestrator",
    description="Multi-agent research assistant orchestration API",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "orchestrator"}


@app.get("/agents")
async def list_agents():
    """List all registered agents with their status."""
    agents = registry.list_agents()
    status = await get_all_agent_status()
    return {
        "agents": [
            {
                "name": a.name,
                "display_name": a.display_name,
                "description": a.description,
                "icon": a.icon,
                "capabilities": a.capabilities,
                "online": status.get(a.name, False),
            }
            for a in agents
        ]
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Main chat endpoint (non-streaming)."""
    logger.info(f"Chat request: {request.message[:100]}...")
    response = await orchestrate(request)
    logger.info(f"Chat response: agent={response.agent_name}, len={len(response.content)}")
    return response


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE streaming chat endpoint."""
    from starlette.responses import StreamingResponse

    logger.info(f"Stream request: {request.message[:100]}...")

    return StreamingResponse(
        orchestrate_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/sessions")
async def list_sessions():
    """List conversation sessions with metadata."""
    return {"sessions": memory_store.list_sessions_detail()}


@app.get("/sessions/{conversation_id}/messages")
async def get_session_messages(conversation_id: str):
    """Get all messages for a specific session (for UI conversation restore)."""
    messages = memory_store.get_session_messages(conversation_id)
    if messages is None:
        return {"error": "Session not found", "conversation_id": conversation_id}
    return {
        "conversation_id": conversation_id,
        "messages": messages,
    }


@app.delete("/sessions/{conversation_id}")
async def delete_session(conversation_id: str):
    """Delete a conversation session."""
    memory_store.delete(conversation_id)
    return {"status": "deleted", "conversation_id": conversation_id}


# ---- Research Threads (read-only artifact review) ----

def _validate_research_thread_id(thread_id: str) -> str:
    if not SAFE_THREAD_ID.fullmatch(thread_id):
        raise HTTPException(status_code=400, detail="Invalid research_thread id")
    return thread_id


@app.get("/research/threads")
async def list_research_thread_artifacts():
    """List available research_thread artifacts from the configured artifact root."""
    from orchestrator.research_thread import list_research_threads, research_threads_dir, resolve_artifacts_dir

    threads = list_research_threads()
    return {
        "threads": threads,
        "count": len(threads),
        "artifacts_dir": str(resolve_artifacts_dir()),
        "research_threads_dir": str(research_threads_dir()),
        "read_only": True,
    }


@app.get("/research/threads/{thread_id}")
async def get_research_thread_artifact(thread_id: str):
    """Load one research_thread JSON artifact."""
    from orchestrator.research_thread import load_research_thread, research_thread_paths

    thread_id = _validate_research_thread_id(thread_id)
    paths = research_thread_paths(thread_id)
    try:
        thread = load_research_thread(thread_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="research_thread not found") from None
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "thread": thread,
        "json_path": str(paths.json_path),
        "markdown_path": str(paths.markdown_path),
        "read_only": True,
    }


@app.get("/research/threads/{thread_id}/markdown")
async def get_research_thread_markdown(thread_id: str):
    """Load one research_thread Markdown artifact, rendering from JSON if needed."""
    from orchestrator.research_thread import load_research_thread, render_research_thread_markdown, research_thread_paths

    thread_id = _validate_research_thread_id(thread_id)
    paths = research_thread_paths(thread_id)
    try:
        thread = load_research_thread(thread_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="research_thread not found") from None
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if paths.markdown_path.exists():
        markdown = paths.markdown_path.read_text(encoding="utf-8")
        source = "artifact"
    else:
        markdown = render_research_thread_markdown(thread)
        source = "rendered_from_json"

    return {
        "thread_id": thread_id,
        "markdown": markdown,
        "markdown_path": str(paths.markdown_path),
        "source": source,
        "read_only": True,
    }


@app.get("/research/threads/{thread_id}/context")
async def get_research_thread_context_bundle(
    thread_id: str,
    trigger_type: str = "on_demand",
    trigger_summary: str = "read-only research context review",
):
    """Build a read-only Research Context Bundle preview for one thread."""
    from orchestrator.research_context_bundle import preview_or_write_research_context_bundle

    thread_id = _validate_research_thread_id(thread_id)
    try:
        payload = preview_or_write_research_context_bundle(
            thread_id=thread_id,
            trigger_type=trigger_type,
            trigger_summary=trigger_summary,
            execute=False,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="research_thread not found") from None
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload["read_only"] = True
    return payload


def _evidence_matrix_request(body: dict) -> tuple[str, str, int, bool]:
    trigger_type = str(body.get("trigger_type", "on_demand"))
    trigger_summary = str(body.get("trigger_summary", "UI evidence matrix review")).strip()
    if not trigger_summary:
        raise HTTPException(status_code=400, detail="trigger_summary is required")
    raw_max_rows = body.get("max_rows", 12)
    try:
        max_rows = int(raw_max_rows)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="max_rows must be an integer") from None
    if max_rows < 1 or max_rows > 50:
        raise HTTPException(status_code=400, detail="max_rows must be between 1 and 50")
    confirm_artifact_write = body.get("confirm_artifact_write") is True
    return trigger_type, trigger_summary, max_rows, confirm_artifact_write


def _run_evidence_matrix_action(thread_id: str, body: dict, *, execute: bool):
    from orchestrator.research_evidence_matrix import preview_or_write_evidence_matrix

    thread_id = _validate_research_thread_id(thread_id)
    trigger_type, trigger_summary, max_rows, confirm_artifact_write = _evidence_matrix_request(body)
    if execute and not confirm_artifact_write:
        raise HTTPException(status_code=400, detail="confirm_artifact_write=true is required for evidence matrix writes")
    try:
        return preview_or_write_evidence_matrix(
            thread_id=thread_id,
            trigger_type=trigger_type,
            trigger_summary=trigger_summary,
            execute=execute,
            max_rows=max_rows,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="research_thread not found") from None
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/research/threads/{thread_id}/evidence-matrix/preview")
async def preview_research_thread_evidence_matrix(thread_id: str, body: dict = Body(default={})):
    """Build a read-only Evidence Matrix review surface preview for one thread."""
    return _run_evidence_matrix_action(thread_id, body, execute=False)


@app.post("/research/threads/{thread_id}/evidence-matrix/write")
async def write_research_thread_evidence_matrix(thread_id: str, body: dict = Body(...)):
    """Write an Evidence Matrix local artifact after explicit confirmation."""
    return _run_evidence_matrix_action(thread_id, body, execute=True)


@app.post("/research/loops/preview")
async def preview_research_loop_packet(body: dict = Body(...)):
    """Build a read-only Research Loop Packet preview without writing artifacts."""
    from orchestrator.research_loop_packet import preview_or_write_research_loop_packet

    thread_id = _validate_research_thread_id(str(body.get("thread_id", "")))
    trigger_type = str(body.get("trigger_type", "on_demand"))
    trigger_summary = str(body.get("trigger_summary", "")).strip()
    if not trigger_summary:
        raise HTTPException(status_code=400, detail="trigger_summary is required")
    try:
        payload = preview_or_write_research_loop_packet(
            thread_id=thread_id,
            trigger_type=trigger_type,
            trigger_summary=trigger_summary,
            execute=False,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="research_thread not found") from None
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload["read_only"] = True
    return payload


@app.post("/research/subagent-envelopes/preview")
async def preview_subagent_output_envelope(body: dict = Body(...)):
    """Build a read-only Subagent Output Envelope preview from an inline loop packet."""
    from orchestrator.subagent_output_envelope import build_subagent_output_envelope, render_subagent_output_envelope_markdown

    loop_packet = body.get("loop_packet")
    if not isinstance(loop_packet, dict):
        raise HTTPException(status_code=400, detail="loop_packet object is required")
    try:
        envelope = build_subagent_output_envelope(
            loop_packet=loop_packet,
            role=str(body.get("role", "")),
            output_type=str(body.get("output_type", "")),
            summary=str(body.get("summary", "")),
            loop_packet_ref="inline:api-preview",
            missing_evidence=body.get("missing_evidence"),
            counterarguments=body.get("counterarguments"),
            failure_modes=body.get("failure_modes"),
            artifact_candidates=body.get("artifact_candidates"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "schema_version": envelope["schema_version"],
        "status": "would_write",
        "dry_run": True,
        "thread_id": envelope["thread_id"],
        "loop_packet_id": envelope["loop_packet_id"],
        "envelope_id": envelope["envelope_id"],
        "envelope": envelope,
        "preview_markdown": render_subagent_output_envelope_markdown(envelope),
        "live_store_mutations": [],
        "read_only": True,
    }


def _patch_review_request(body: dict) -> tuple[dict, str, str, bool]:
    patch = body.get("patch")
    if not isinstance(patch, dict):
        raise HTTPException(status_code=400, detail="patch object is required")
    reviewer = str(body.get("reviewer", "local_reviewer")).strip() or "local_reviewer"
    review_note = str(body.get("review_note", "")).strip()
    confirm_artifact_write = body.get("confirm_artifact_write") is True
    return patch, reviewer, review_note, confirm_artifact_write


def _run_patch_review_action(thread_id: str, body: dict, *, action: str):
    from orchestrator.research_patch_review import process_research_patch_review

    thread_id = _validate_research_thread_id(thread_id)
    patch, reviewer, review_note, confirm_artifact_write = _patch_review_request(body)
    try:
        return process_research_patch_review(
            thread_id=thread_id,
            patch=patch,
            action=action,
            reviewer=reviewer,
            review_note=review_note,
            confirm_artifact_write=confirm_artifact_write,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="research_thread not found") from None
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/research/threads/{thread_id}/patches/preview")
async def preview_research_thread_patch_review(thread_id: str, body: dict = Body(...)):
    """Preview a research_thread patch review without writing artifacts."""
    return _run_patch_review_action(thread_id, body, action="preview")


@app.post("/research/threads/{thread_id}/patches/apply")
async def apply_research_thread_patch_review(thread_id: str, body: dict = Body(...)):
    """Apply a research_thread patch to local artifacts after explicit confirmation."""
    return _run_patch_review_action(thread_id, body, action="apply")


@app.post("/research/threads/{thread_id}/patches/reject")
async def reject_research_thread_patch_review(thread_id: str, body: dict = Body(...)):
    """Record a rejected research_thread patch without changing the thread artifact."""
    return _run_patch_review_action(thread_id, body, action="reject")


def _knowledge_accumulation_request(body: Optional[dict]) -> tuple[str, bool, int, bool, bool]:
    body = body or {}
    purpose = str(body.get("purpose", "research thread knowledge accumulation")).strip()
    if not purpose:
        raise HTTPException(status_code=400, detail="purpose is required")
    include_pending_review = body.get("include_pending_review") is True
    raw_max_records = body.get("max_records", 50)
    try:
        max_records = int(raw_max_records)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="max_records must be an integer") from None
    if max_records < 1 or max_records > 200:
        raise HTTPException(status_code=400, detail="max_records must be between 1 and 200")
    confirm_artifact_write = body.get("confirm_artifact_write") is True
    confirm_archival_enqueue = body.get("confirm_archival_enqueue") is True
    return purpose, include_pending_review, max_records, confirm_artifact_write, confirm_archival_enqueue


def _run_knowledge_accumulation_action(thread_id: str, body: Optional[dict], *, execute: bool, enqueue_archival: bool):
    from orchestrator.research_knowledge_accumulation import preview_or_write_knowledge_records

    thread_id = _validate_research_thread_id(thread_id)
    purpose, include_pending_review, max_records, confirm_artifact_write, confirm_archival_enqueue = _knowledge_accumulation_request(body)
    if execute and not confirm_artifact_write:
        raise HTTPException(status_code=400, detail="confirm_artifact_write=true is required for knowledge record writes")
    if enqueue_archival and not confirm_archival_enqueue:
        raise HTTPException(status_code=400, detail="confirm_archival_enqueue=true is required for archival queue writes")
    try:
        return preview_or_write_knowledge_records(
            thread_id=thread_id,
            purpose=purpose,
            execute=execute,
            enqueue_archival=enqueue_archival,
            include_pending_review=include_pending_review,
            max_records=max_records,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="research_thread not found") from None
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/research/threads/{thread_id}/knowledge/preview")
async def preview_research_thread_knowledge_records(thread_id: str, body: Optional[dict] = Body(default=None)):
    """Preview portable knowledge records from reviewed research_thread objects."""
    return _run_knowledge_accumulation_action(thread_id, body, execute=False, enqueue_archival=False)


@app.post("/research/threads/{thread_id}/knowledge/write")
async def write_research_thread_knowledge_records(thread_id: str, body: dict = Body(...)):
    """Write portable knowledge records as local durable artifacts."""
    return _run_knowledge_accumulation_action(thread_id, body, execute=True, enqueue_archival=False)


@app.post("/research/threads/{thread_id}/knowledge/enqueue-archival")
async def enqueue_research_thread_knowledge_records(thread_id: str, body: dict = Body(...)):
    """Write knowledge records and enqueue reviewed records for the archival worker."""
    return _run_knowledge_accumulation_action(thread_id, body, execute=True, enqueue_archival=True)


def _weekly_loop_request(body: Optional[dict]) -> dict:
    body = body or {}
    raw_days = body.get("days", 7)
    raw_scout_limit = body.get("scout_limit", 5)
    raw_rag_limit = body.get("rag_limit", 5)
    raw_kg_limit = body.get("kg_limit", 5)
    try:
        days = int(raw_days)
        scout_limit = int(raw_scout_limit)
        rag_limit = int(raw_rag_limit)
        kg_limit = int(raw_kg_limit)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="days and source limits must be integers") from None
    if days < 1 or days > 31:
        raise HTTPException(status_code=400, detail="days must be between 1 and 31")
    if min(scout_limit, rag_limit, kg_limit) < 0:
        raise HTTPException(status_code=400, detail="source limits must be non-negative")
    return {
        "query": body.get("query"),
        "days": days,
        "execute": body.get("execute") is True,
        "use_live_memory": body.get("use_live_memory", True) is True,
        "scout_limit": scout_limit,
        "rag_limit": rag_limit,
        "kg_limit": kg_limit,
    }


@app.post("/research/threads/{thread_id}/weekly-loop/run")
async def run_research_thread_weekly_loop(thread_id: str, body: Optional[dict] = Body(default=None)):
    """Run or preview the Weekly Useful Research Loop v0."""
    from orchestrator.research_weekly_loop import preview_or_run_weekly_loop

    thread_id = _validate_research_thread_id(thread_id)
    kwargs = _weekly_loop_request(body)
    try:
        return await preview_or_run_weekly_loop(thread_id=thread_id, **kwargs)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="research_thread not found") from None
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/workspaces")
async def list_workspaces():
    """List available workspaces."""
    from orchestrator.workspace import workspace_manager
    return {"workspaces": workspace_manager.list_workspaces()}


@app.get("/projects")
async def list_projects():
    """List all registered projects."""
    from agents.project.project_store import list_projects
    return {"projects": list_projects()}


@app.get("/deadlines")
async def get_deadlines():
    """Get all deadlines sorted by D-day."""
    from agents.project.project_store import get_all_deadlines
    return {"deadlines": get_all_deadlines()}


# ---- Model Profile Management ----

@app.get("/model-profile")
async def get_model_profile():
    """Get current model profile status."""
    from orchestrator.model_profiles import profile_manager
    return profile_manager.get_status()


@app.post("/model-profile")
async def set_model_profile(request: dict):
    """Switch model profile.

    Body options:
      {"profile": "cost"}                          — switch all agents
      {"profile": "performance", "agent": "writing"} — switch one agent
    """
    from orchestrator.model_profiles import profile_manager

    profile = request.get("profile")
    agent = request.get("agent")

    if not profile:
        return {"error": "profile is required", "available": ["cost", "performance"]}

    if agent:
        ok = profile_manager.set_agent_profile(agent, profile)
        msg = f"Agent '{agent}' → profile '{profile}'" if ok else f"Unknown profile: {profile}"
    else:
        ok = profile_manager.set_profile(profile)
        msg = f"Global profile → '{profile}'" if ok else f"Unknown profile: {profile}"

    return {
        "success": ok,
        "message": msg,
        "status": profile_manager.get_status(),
    }


# Compatibility aliases for UI (which uses /models/profiles)
@app.get("/models/profiles")
async def get_model_profiles_compat():
    """Compatibility: get model profiles (UI uses this path)."""
    from orchestrator.model_profiles import profile_manager
    return profile_manager.get_status()


@app.post("/models/profile")
async def set_model_profile_compat(request: dict):
    """Compatibility: set model profile (UI uses this path)."""
    return await set_model_profile(request)

# ---- Archival Memory (Graphiti) ----

@app.get("/memory/search")
async def search_archival_memory(q: str, limit: int = 5):
    """Search long-term archival memory (Graphiti knowledge graph)."""
    from orchestrator.archival import archival_memory
    results = await archival_memory.search(q, limit)
    return {"query": q, "results": results, "count": len(results)}


@app.get("/memory/entities")
async def list_entities(limit: int = 20):
    """List entities extracted from conversations."""
    from orchestrator.archival import archival_memory
    graph_data = await archival_memory.get_graph_data(limit)
    # Return nodes as entities for backward compat
    return {"entities": graph_data["nodes"], "count": len(graph_data["nodes"])}


@app.get("/memory/graph")
async def get_knowledge_graph(limit: int = 100):
    """Get knowledge graph data for visualization (nodes + edges)."""
    from orchestrator.archival import archival_memory
    data = await archival_memory.get_graph_data(limit)
    return data


# ---- Knowledge Brief / Scout Knowledge ----

@app.get("/knowledge/briefs")
async def list_knowledge_briefs(limit: int = 30):
    """List generated proactive Scout/Knowledge briefs."""
    from integrations.knowledge_brief import list_knowledge_briefs
    return {"briefs": list_knowledge_briefs(limit)}


@app.get("/knowledge/briefs/latest")
async def get_latest_knowledge_brief():
    """Return the newest generated KnowledgeBrief artifact."""
    from integrations.knowledge_brief import load_latest_brief
    brief = load_latest_brief()
    if not brief:
        return {"error": "No knowledge briefs found"}
    return brief


@app.post("/knowledge/briefs/generate")
async def generate_knowledge_brief_endpoint(body: Optional[dict] = Body(default=None)):
    """Generate a proactive KnowledgeBrief from Scout evidence."""
    from integrations.knowledge_brief import generate_knowledge_brief

    body = body or {}
    brief = generate_knowledge_brief(
        date=body.get("date"),
        days=int(body.get("days", 1)),
        query=body.get("query", ""),
        min_score=float(body.get("min_score", 70)),
        promote=bool(body.get("promote", True)),
        write_files=bool(body.get("write_files", True)),
    )
    return brief


@app.get("/knowledge/search")
async def search_knowledge(q: str, limit: int = 5):
    """Search Scout DB, Qdrant RAG, and archival memory together."""
    from integrations.knowledge_brief import search_knowledge
    return await search_knowledge(q, limit)


@app.get("/autonomy/actions")
async def list_autonomy_actions(limit: int = 100):
    """List recent autonomous local actions."""
    from integrations.autonomy import list_autonomy_actions
    return {"actions": list_autonomy_actions(limit)}


# ---- Debate Engine ----

@app.get("/debate/status")
async def debate_status():
    """Get debate engine status and configuration."""
    from orchestrator.debate import debate_engine
    debate_engine._ensure_loaded()
    cfg = debate_engine._config
    return {
        "enabled": debate_engine.enabled,
        "panelists": [
            {"name": p.name, "model": p.model, "provider": p.provider}
            for p in debate_engine._panelists
        ],
        "rounds": cfg.get("rounds", 3),
        "auto_trigger": cfg.get("auto_trigger", True),
        "complexity_threshold": cfg.get("complexity", {}).get("threshold", 0.7),
    }


@app.post("/debate/classify")
async def classify_question(q: str):
    """Test complexity classification for a question (iMAD)."""
    from orchestrator.debate import debate_engine
    should, score, reason = await debate_engine.should_debate(q)
    return {
        "question": q,
        "should_debate": should,
        "complexity_score": score,
        "reason": reason,
    }


@app.get("/debate/stream")
async def debate_stream(q: str, rounds: int = 3):
    """Stream debate progress as SSE events.

    Events: debate_start, round_start, panelist_done, judge_start, debate_done
    """
    import json
    from starlette.responses import StreamingResponse
    from orchestrator.debate import debate_engine
    from orchestrator.memory import memory_store

    memory = memory_store.get_or_create(None)

    async def event_generator():
        async for event in debate_engine.run_stream(
            question=q,
            context=await memory.build_llm_context(query=q),
            num_rounds=rounds,
        ):
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---- Pipeline ----

@app.get("/pipelines")
async def list_pipelines():
    """List available pipeline templates."""
    from orchestrator.pipeline import pipeline_executor
    return {"pipelines": pipeline_executor.list_pipelines()}


@app.get("/pipeline/checkpoint/{run_id}")
async def get_checkpoint(run_id: str):
    """Get checkpoint status for a paused pipeline."""
    from orchestrator.pipeline import pipeline_executor
    cp = pipeline_executor.get_checkpoint(run_id)
    if not cp:
        return {"error": "No active checkpoint", "run_id": run_id}
    return cp


@app.post("/pipeline/checkpoint/{run_id}/respond")
async def respond_checkpoint(run_id: str, body: dict):
    """Respond to a HITL checkpoint (proceed/modify/abort)."""
    from orchestrator.pipeline import pipeline_executor
    action = body.get("action", "proceed")
    mods = body.get("modifications")
    return await pipeline_executor.respond_checkpoint(run_id, action, mods)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
