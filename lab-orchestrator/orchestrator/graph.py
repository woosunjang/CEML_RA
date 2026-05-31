"""
Lab Orchestrator — Main Orchestration Graph

Implements the Planner → Router → Executor → Synthesizer pipeline.
Uses async execution without LangGraph dependency for initial version.
"""

import asyncio
import logging
import os
import uuid
from typing import Optional

from agents.base import AgentTask, AgentResult
from orchestrator.schemas import ChatRequest, ChatResponse, ExecutionPlan
from orchestrator.planner import create_plan
from orchestrator.router import call_agent
from orchestrator.memory import SharedMemory, memory_store
from orchestrator.workspace import workspace_manager
from llm.pool import generate_answer

logger = logging.getLogger(__name__)

SYNTHESIZER_PROMPT = """You are a research assistant synthesizer.
You receive results from one or more specialized agents and must create
a unified, coherent response for the user.

## Rules
- Combine agent outputs into a single well-structured response.
- Preserve all citations and references from the agents.
- If an agent failed, note it briefly and continue with available results.
- Respond in Korean by default, with English technical terms.
- Do NOT add preambles like "Based on the agent results..."
"""


def _enqueue_archival(
    conversation_id: str,
    user_message: str,
    assistant_message: str,
    agent_name: str = "orchestrator",
):
    """Write an archival ingestion job to the file queue.

    A separate archival_worker process picks up and processes these.
    This keeps Graphiti entirely out of the orchestrator process memory.
    """
    try:
        import json as _json
        from datetime import datetime as _dt
        from orchestrator.config import ARCHIVAL_QUEUE_DIR

        ARCHIVAL_QUEUE_DIR.mkdir(parents=True, exist_ok=True)

        MAX_LEN = 2000
        user_text = user_message[:MAX_LEN]
        asst_text = assistant_message[:MAX_LEN]
        if len(assistant_message) > MAX_LEN:
            asst_text += f"\n[... {len(assistant_message) - MAX_LEN}자 생략]"

        job = {
            "conversation_id": conversation_id,
            "user_message": user_text,
            "assistant_message": asst_text,
            "agent_name": agent_name,
            "timestamp": _dt.utcnow().isoformat(),
        }

        ts = _dt.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        job_file = ARCHIVAL_QUEUE_DIR / f"{ts}.json"
        job_file.write_text(_json.dumps(job, ensure_ascii=False), encoding="utf-8")
        logger.debug(f"Archival job enqueued: {job_file.name}")

    except Exception as e:
        logger.warning(f"Failed to enqueue archival job: {e}")


async def orchestrate(request: ChatRequest) -> ChatResponse:
    """Main orchestration pipeline.

    1. Planner: Decompose user instruction into tasks
    2. Router: Route each task to the appropriate agent
    3. Executor: Execute tasks in dependency order
    4. Synthesizer: Combine results into a unified response

    Special mode: debate — routes to Multi-LLM Debate Engine.
    """
    # Get or create conversation memory
    memory = memory_store.get_or_create(request.conversation_id)
    memory.add_user_message(request.message)

    # ── Debate mode ──
    if request.mode == "debate":
        return await _run_debate(request, memory)

    # ── Pipeline mode (explicit) ──
    if request.mode == "pipeline" or request.pipeline_id:
        return await _run_pipeline(request, memory)

    # Step 1: Plan
    plan = await create_plan(
        instruction=request.message,
        agent_override=request.agent_override,
    )
    logger.info(f"Plan: {plan.reasoning} ({len(plan.tasks)} tasks)")

    # ── Pipeline detected by planner ──
    if plan.pipeline_id:
        return await _run_pipeline(request, memory, plan.pipeline_id)

    # ── General conversation (no specialized agent) ──
    if plan.tasks and plan.tasks[0].agent == "none":
        return await _handle_general_chat(request, memory, plan)

    execution_steps = []
    all_citations = []
    agent_results = []

    # Step 2-3: Route and Execute
    completed_agents: dict[str, dict] = {}

    for task_plan in plan.tasks:
        # Check dependencies
        parent_results = []
        for dep in task_plan.depends_on:
            if dep in completed_agents:
                parent_results.append(completed_agents[dep])

        # Build task with workspace context
        base_filters = task_plan.filters or request.filters
        base_context = {
            "conversation_id": memory.conversation_id,
            "chat_history": memory.get_recent_context(n_turns=3),
        }
        ws_filters, ws_context = workspace_manager.inject_context(
            base_filters, base_context, request.workspace
        )

        task = AgentTask(
            task_id=str(uuid.uuid4()),
            instruction=task_plan.task,
            context=ws_context,
            parent_results=parent_results,
            filters=ws_filters,
        )

        # Execute
        step_info = {
            "agent": task_plan.agent,
            "task": task_plan.task,
            "status": "executing",
        }
        execution_steps.append(step_info)

        import time as _time
        _t0 = _time.time()
        result = await call_agent(task_plan.agent, task)
        _elapsed = _time.time() - _t0

        step_info["status"] = result.status
        if result.error:
            step_info["error"] = result.error
            # Alert on agent failure
            try:
                from integrations.slack_notifier import notify_error
                asyncio.create_task(
                    notify_error(
                        task_plan.agent,
                        f"에이전트 호출 실패: {result.error[:200]}",
                        f"Task: {task_plan.task[:300]}",
                    )
                )
            except Exception:
                pass

        # Track usage
        try:
            from integrations.usage_tracker import tracker
            asyncio.create_task(
                tracker.log_agent_call(
                    agent_name=task_plan.agent,
                    status=result.status,
                    elapsed_sec=_elapsed,
                    instruction=task_plan.task[:200],
                    error=result.error or "",
                )
            )
        except Exception:
            pass

        if result.status == "completed":
            completed_agents[task_plan.agent] = result.model_dump()
            memory.store_agent_result(result.model_dump())
            all_citations.extend(result.citations)
            agent_results.append(result)

    # Step 4: Synthesize
    if len(agent_results) == 1 and agent_results[0].status == "completed":
        # Single agent — pass through directly
        final_content = agent_results[0].content
        final_agent = agent_results[0].agent_name
    elif len(agent_results) > 1:
        # Multiple agents — synthesize
        final_content = await _synthesize(agent_results, request.message)
        final_agent = "orchestrator"
    else:
        # No successful results
        final_content = "요청을 처리할 수 없었습니다. 에이전트 연결 상태를 확인해주세요."
        final_agent = "orchestrator"

    memory.add_assistant_message(final_content, agent_name=final_agent)

    # Auto-summarize if conversation is getting long
    if memory.needs_summarization():
        await _auto_summarize(memory)

    # Archival: enqueue for separate worker process (no Graphiti in this process)
    _enqueue_archival(
        conversation_id=memory.conversation_id,
        user_message=request.message,
        assistant_message=final_content,
        agent_name=final_agent,
    )

    # Track conversation
    try:
        from integrations.usage_tracker import tracker
        asyncio.create_task(
            tracker.log_conversation(
                conversation_id=memory.conversation_id,
                message=request.message[:200],
                agent_name=final_agent,
                mode=request.mode or "normal",
            )
        )
    except Exception:
        pass

    # Chat log (markdown file)
    try:
        from integrations.chat_logger import log_turn
        log_turn(
            user_message=request.message,
            assistant_message=final_content,
            agent_name=final_agent,
            conversation_id=memory.conversation_id,
            mode=request.mode or "normal",
            source="web",
        )
    except Exception:
        pass

    # Persist session to disk
    memory_store.save(memory.conversation_id)

    return ChatResponse(
        conversation_id=memory.conversation_id,
        content=final_content,
        agent_name=final_agent,
        citations=all_citations,
        execution_steps=execution_steps,
        metadata={
            "plan_reasoning": plan.reasoning,
            "is_multi_agent": plan.is_multi_agent,
            "num_tasks": len(plan.tasks),
        },
    )


async def _auto_summarize(memory):
    """Auto-summarize old messages using a cheap model.

    Uses gpt-4.1-nano to compress conversation history.
    Called when message count exceeds threshold.
    """
    from orchestrator.memory import SharedMemory

    # Get messages that will be compressed (all except recent 6)
    keep_count = 6
    if len(memory.messages) <= keep_count:
        return

    old_messages = memory.messages[:-keep_count]
    old_text = "\n".join(
        f"[{m['role']}]: {m['content'][:300]}" for m in old_messages
    )

    try:
        summary = await generate_answer(
            system_prompt=(
                "대화 내용을 핵심 사실, 결정사항, 주요 요청 중심으로 "
                "5~10문장으로 요약하세요. 한국어로 작성."
            ),
            user_prompt=old_text,
            model="gpt-4.1-nano",  # Cheapest model for summarization
            temperature=0.1,
        )
        memory.compress(summary)
        logger.info(f"Auto-summarized {len(old_messages)} messages")
    except Exception as e:
        logger.warning(f"Auto-summarization failed: {e}")


async def _synthesize(results: list[AgentResult], original_question: str) -> str:
    """Synthesize multiple agent results into a unified response."""
    parts = []
    for r in results:
        parts.append(f"### {r.agent_name} 결과:\n{r.content}")

    combined = "\n\n---\n\n".join(parts)

    user_prompt = f"""## 사용자 원래 질문
{original_question}

## 에이전트 결과들
{combined}

위 결과들을 통합하여 하나의 구조화된 응답을 작성해주세요."""

    return await generate_answer(
        system_prompt=SYNTHESIZER_PROMPT,
        user_prompt=user_prompt,
    )


GENERAL_CHAT_PROMPT = """You are a friendly research lab assistant named CEML Bot.
You handle greetings, casual conversation, and general questions.
- Respond in Korean by default (with English technical terms when appropriate).
- Keep responses concise and natural.
- If the user seems to need a specialized function (paper search, writing, project management, etc.),
  briefly mention what you can do.
- Do NOT generate any reports, documents, or artifacts for casual messages.
"""


async def _handle_general_chat(
    request: ChatRequest,
    memory,
    plan,
) -> ChatResponse:
    """Handle general conversation without routing to any specialized agent."""
    chat_history = memory.get_recent_context(n_turns=3)

    content = await generate_answer(
        system_prompt=GENERAL_CHAT_PROMPT,
        user_prompt=request.message,
        model="gpt-4.1-nano",  # Cheapest & fastest for chitchat
        temperature=0.7,
        chat_history=chat_history,
    )

    agent_name = "orchestrator"
    memory.add_assistant_message(content, agent_name=agent_name)

    # Track usage
    try:
        from integrations.usage_tracker import tracker
        asyncio.create_task(
            tracker.log_conversation(
                conversation_id=memory.conversation_id,
                message=request.message[:200],
                agent_name=agent_name,
                mode="general",
            )
        )
    except Exception:
        pass

    # Chat log
    try:
        from integrations.chat_logger import log_turn
        log_turn(
            user_message=request.message,
            assistant_message=content,
            agent_name=agent_name,
            conversation_id=memory.conversation_id,
            mode="general",
            source="slack",
        )
    except Exception:
        pass

    # Archival: enqueue for separate worker process
    _enqueue_archival(
        conversation_id=memory.conversation_id,
        user_message=request.message,
        assistant_message=content,
        agent_name=agent_name,
    )

    memory_store.save(memory.conversation_id)

    return ChatResponse(
        conversation_id=memory.conversation_id,
        content=content,
        agent_name=agent_name,
        metadata={
            "plan_reasoning": plan.reasoning,
            "is_multi_agent": False,
            "mode": "general",
        },
    )


async def orchestrate_stream(request: ChatRequest):
    """Streaming orchestration — yields SSE events.

    Event types:
      - plan: execution plan with agent list
      - step: agent execution status update
      - token: content token from LLM
      - citations: citation list
      - done: final metadata
      - error: error message
    """
    import json
    from llm.pool import generate_answer_stream

    memory = memory_store.get_or_create(request.conversation_id)
    memory.add_user_message(request.message)

    # Step 1: Plan
    plan = await create_plan(
        instruction=request.message,
        agent_override=request.agent_override,
    )

    yield _sse_event("plan", {
        "tasks": [{"agent": t.agent, "task": t.task} for t in plan.tasks],
        "reasoning": plan.reasoning,
        "conversation_id": memory.conversation_id,
    })

    all_citations = []
    agent_results = []
    completed_agents: dict[str, dict] = {}

    for i, task_plan in enumerate(plan.tasks):
        yield _sse_event("step", {
            "agent": task_plan.agent, "index": i, "status": "executing",
        })

        parent_results = [
            completed_agents[dep] for dep in task_plan.depends_on
            if dep in completed_agents
        ]

        base_filters = task_plan.filters or request.filters
        base_context = {
            "conversation_id": memory.conversation_id,
            "chat_history": memory.get_recent_context(n_turns=3),
        }
        ws_filters, ws_context = workspace_manager.inject_context(
            base_filters, base_context, request.workspace
        )

        task = AgentTask(
            task_id=str(uuid.uuid4()),
            instruction=task_plan.task,
            context=ws_context,
            parent_results=parent_results,
            filters=ws_filters,
        )

        result = await call_agent(task_plan.agent, task)

        if result.status == "completed":
            completed_agents[task_plan.agent] = result.model_dump()
            memory.store_agent_result(result.model_dump())
            all_citations.extend(result.citations)
            agent_results.append(result)

        yield _sse_event("step", {
            "agent": task_plan.agent, "index": i, "status": result.status,
            "error": result.error,
        })

    # Stream the final content
    if len(agent_results) == 1:
        # Single agent — stream content token by token
        final_agent = agent_results[0].agent_name
        yield _sse_event("agent", {"name": final_agent})

        # Re-stream: for single agent, content is already complete
        # Send it in chunks to simulate streaming
        content = agent_results[0].content
        chunk_size = 20
        for j in range(0, len(content), chunk_size):
            yield _sse_event("token", {"text": content[j:j+chunk_size]})

    elif len(agent_results) > 1:
        final_agent = "orchestrator"
        yield _sse_event("agent", {"name": final_agent})

        content = await _synthesize(agent_results, request.message)
        chunk_size = 20
        for j in range(0, len(content), chunk_size):
            yield _sse_event("token", {"text": content[j:j+chunk_size]})
    else:
        final_agent = "orchestrator"
        content = "요청을 처리할 수 없었습니다."
        yield _sse_event("token", {"text": content})

    memory.add_assistant_message(content, agent_name=final_agent)
    memory_store.save(memory.conversation_id)

    if all_citations:
        yield _sse_event("citations", {"citations": all_citations})

    yield _sse_event("done", {
        "conversation_id": memory.conversation_id,
        "agent_name": final_agent,
        "metadata": {
            "plan_reasoning": plan.reasoning,
            "is_multi_agent": plan.is_multi_agent,
        },
    })


def _sse_event(event_type: str, data: dict) -> str:
    import json
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _run_debate(request: ChatRequest, memory) -> ChatResponse:
    """Run Multi-LLM Debate pipeline."""
    from orchestrator.debate import debate_engine

    logger.info(f"Debate mode: '{request.message[:50]}...'")

    # Build context from memory
    context = await memory.build_llm_context(query=request.message)

    result = await debate_engine.run(
        question=request.message,
        context=context,
        force=True,  # mode=debate means user explicitly requested
        num_rounds=request.debate_rounds,
    )

    # Build metadata
    debate_meta = {
        "mode": "debate",
        "debated": result.debated,
        "complexity_score": result.complexity_score,
        "total_elapsed_ms": result.total_elapsed_ms,
    }
    if result.debated and result.rounds:
        debate_meta["rounds"] = [
            [
                {
                    "panelist": m.panelist,
                    "round": m.round_num,
                    "length": len(m.content),
                    "elapsed_ms": m.elapsed_ms,
                }
                for m in round_msgs
            ]
            for round_msgs in result.rounds
        ]

    agent_name = "debate" if result.debated else "orchestrator"
    memory.add_assistant_message(result.final_answer, agent_name=agent_name)

    # Auto-summarize if needed
    if memory.needs_summarization():
        await _auto_summarize(memory)

    # Archival: enqueue for separate worker process
    _enqueue_archival(
        conversation_id=memory.conversation_id,
        user_message=request.message,
        assistant_message=result.final_answer,
        agent_name=agent_name,
    )

    memory_store.save(memory.conversation_id)

    return ChatResponse(
        conversation_id=memory.conversation_id,
        content=result.final_answer,
        agent_name=agent_name,
        metadata=debate_meta,
    )


async def _run_pipeline(
    request: ChatRequest,
    memory,
    pipeline_id: Optional[str] = None,
) -> ChatResponse:
    """Run a pipeline (sequential agent chaining)."""
    from orchestrator.pipeline import pipeline_executor

    pid = pipeline_id or request.pipeline_id
    if not pid:
        # Try to match from message
        pid = pipeline_executor.match_pipeline(request.message)

    if not pid:
        return ChatResponse(
            conversation_id=memory.conversation_id,
            content="❌ 매칭되는 파이프라인을 찾을 수 없습니다.",
            agent_name="orchestrator",
        )

    logger.info(f"Pipeline mode: {pid}")

    # Build variables
    variables = {
        "topic": request.message,
        "message": request.message,
        **request.pipeline_vars,
    }

    result = await pipeline_executor.run(pid, variables)

    # Alert on pipeline failure
    if result.status == "failed":
        try:
            from integrations.slack_notifier import notify_error
            failed_steps = [
                sr.agent_name for sr in result.step_results if sr.status == "failed"
            ]
            asyncio.create_task(
                notify_error(
                    "pipeline",
                    f"파이프라인 실패: {pid}",
                    f"실패 단계: {', '.join(failed_steps)}",
                )
            )
        except Exception:
            pass

    # Build execution steps
    exec_steps = []
    for i, sr in enumerate(result.step_results):
        exec_steps.append({
            "agent": sr.agent_name,
            "task": sr.task_id,
            "status": sr.status,
            "content_length": len(sr.content),
        })

    # Build metadata
    meta = {
        "mode": "pipeline",
        "pipeline_id": pid,
        "run_id": result.run_id,
        "status": result.status,
        "artifacts": {k: len(v) for k, v in result.artifacts.items()},
    }

    # Store in memory
    memory.add_assistant_message(result.final_content, "pipeline")
    memory_store.save(memory.conversation_id)

    return ChatResponse(
        conversation_id=memory.conversation_id,
        content=result.final_content,
        agent_name="pipeline",
        execution_steps=exec_steps,
        metadata=meta,
    )
