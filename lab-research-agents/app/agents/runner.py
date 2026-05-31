"""
Lab Research Agents — Agent Runner

Retrieves context from Qdrant, formats it with citations, loads the
agent-specific system prompt, calls the LLM, and returns the answer.
"""

from typing import Optional

from app.agents.prompts import get_agent_prompt
from app.llm.openai_client import generate_answer
from app.retrieval.hybrid_retriever import hybrid_search


def _format_context(results) -> tuple[str, str]:
    """
    Format retrieved Qdrant results into a numbered context block and a
    citation summary.

    Returns:
        (context_block, citation_summary)
    """
    if not results:
        return ("검색된 문서가 없습니다.", "")

    context_lines: list[str] = []
    citation_lines: list[str] = []

    for i, point in enumerate(results, start=1):
        payload = point.payload or {}
        title = payload.get("title", "unknown")
        source = payload.get("source_file", "unknown")
        page = payload.get("page")
        doc_type = payload.get("document_type", "unknown")
        project = payload.get("project", "unknown")
        text = payload.get("text", "")

        page_str = f"p.{page}" if page is not None else "p.N/A"
        header = f"[{i}] {title} | {source} | {page_str} | type={doc_type} | project={project}"

        context_lines.append(f"{header}\n{text}")
        citation_lines.append(f"[{i}] {title} ({source}, {page_str}, {doc_type}, {project})")

    context_block = "\n\n---\n\n".join(context_lines)
    citation_summary = "\n".join(citation_lines)

    return context_block, citation_summary


def _build_user_prompt(question: str, context_block: str) -> str:
    """Build the user prompt with retrieved context and instructions."""
    return f"""아래는 내부 문서에서 검색된 관련 내용입니다.

---
{context_block}
---

## 질문
{question}

## 지시사항
- 위의 검색된 컨텍스트를 근거로 활용하세요.
- 검색된 내용이 질문에 답하기에 부족하면, 명시적으로 "검색된 근거가 부족합니다"라고 말하세요.
- 인용을 날조하지 마세요. 위에 제공된 [번호] 형식의 인용만 사용하세요.
- 응답 마지막에 "참고한 내부 문서" 섹션을 포함하고, 실제 사용한 인용 번호를 나열하세요.
"""


def run_agent(
    agent_mode: str,
    question: str,
    project: str = "all",
    document_type: str = "all",
    top_k: int = 8,
) -> dict:
    """
    Run the specified agent: retrieve context, format, call LLM.

    Args:
        agent_mode: One of "literature", "proposal", "manuscript", "lecture".
        question: The user's question.
        project: Project filter (or "all" for no filter).
        document_type: Document type filter (or "all" for no filter).
        top_k: Number of chunks to retrieve.

    Returns:
        dict with keys:
            - "answer": The LLM's response text.
            - "citations": Formatted citation summary.
            - "raw_results": Raw Qdrant result objects.
    """
    # 1. Retrieve (hybrid: vector + BM25 keyword search)
    if agent_mode == "scout":
        # Scout mode: always search paper-scout auto-collected papers
        results = hybrid_search(
            query=question,
            limit=top_k,
            project="paper-scout",
            document_type="paper",
        )
    else:
        results = hybrid_search(
            query=question,
            limit=top_k,
            project=project if project != "all" else None,
            document_type=document_type if document_type != "all" else None,
        )

    # 2. Format context
    context_block, citation_summary = _format_context(results)

    # 3. Load agent prompt
    system_prompt = get_agent_prompt(agent_mode)

    # 4. Build user prompt
    user_prompt = _build_user_prompt(question, context_block)

    # 5. Generate answer
    answer = generate_answer(system_prompt=system_prompt, user_prompt=user_prompt)

    return {
        "answer": answer,
        "citations": citation_summary,
        "raw_results": results,
    }
