"""
Teaching Agent — Lecture Design, Quiz Generation, Notebook Creation

Sub-modes:
  - lecture: Structured lecture/slide design with RAG
  - quiz: JSON-structured quiz with answer + explanation
  - notebook: Jupyter notebook (.ipynb) generation
"""

import json
import logging
import re
from typing import Optional

from agents.base import BaseAgent, AgentTask, AgentResult
from agents.teaching.prompts import LECTURE_PROMPT, QUIZ_PROMPT, NOTEBOOK_PROMPT
from agents.teaching.quiz_builder import parse_quiz_response, format_quiz_markdown
from agents.teaching.notebook_builder import (
    build_notebook_from_response,
    notebook_to_json,
)
from llm.pool import generate_answer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sub-mode detection keywords
# ---------------------------------------------------------------------------
_QUIZ_KEYWORDS = [
    "퀴즈", "시험", "문제", "평가", "과제", "출제",
    "quiz", "exam", "test", "assessment", "question",
]
_NOTEBOOK_KEYWORDS = [
    "노트북", "실습", "코드", "jupyter", "colab", "notebook",
    "코딩", "프로그래밍", "파이썬",
]
_LECTURE_KEYWORDS = [
    "강의", "수업", "슬라이드", "커리큘럼", "강좌", "세미나",
    "lecture", "slide", "curriculum", "seminar", "teaching",
]


def _detect_submode(instruction: str) -> str:
    """Detect sub-mode from instruction keywords."""
    lower = instruction.lower()

    quiz_score = sum(1 for kw in _QUIZ_KEYWORDS if kw in lower)
    notebook_score = sum(1 for kw in _NOTEBOOK_KEYWORDS if kw in lower)
    lecture_score = sum(1 for kw in _LECTURE_KEYWORDS if kw in lower)

    if quiz_score > notebook_score and quiz_score > lecture_score:
        return "quiz"
    if notebook_score > quiz_score and notebook_score > lecture_score:
        return "notebook"
    return "lecture"


class TeachingAgent(BaseAgent):
    name = "teaching"
    description = "강의 설계·노트북·퀴즈"
    icon = "🎓"
    capabilities = [
        "lecture_design", "quiz_generation", "notebook_creation",
        "curriculum", "강의", "수업", "퀴즈", "과제", "노트북",
        "lecture", "teaching", "커리큘럼",
    ]

    async def execute(self, task: AgentTask) -> AgentResult:
        submode = _detect_submode(task.instruction)
        logger.info(f"TeachingAgent sub-mode: {submode}")

        try:
            # RAG: search for relevant educational/research content
            rag_context, citations = await self._search_context(task)

            # Build user prompt
            user_prompt = self._build_user_prompt(
                task.instruction, rag_context, task.parent_results
            )

            # Select prompt by sub-mode
            if submode == "quiz":
                system_prompt = QUIZ_PROMPT
            elif submode == "notebook":
                system_prompt = NOTEBOOK_PROMPT
            else:
                system_prompt = LECTURE_PROMPT

            # Generate with dynamic model selection
            chat_history = task.context.get("chat_history", [])
            selected_model = self.select_model(task)
            logger.info(f"TeachingAgent using model: {selected_model}")
            answer = await generate_answer(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=selected_model,
                chat_history=chat_history,
            )

            # Post-process by sub-mode
            content, artifacts = self._postprocess(submode, answer, task.instruction)

            return AgentResult(
                task_id=task.task_id,
                agent_name=self.name,
                status="completed",
                content=content,
                citations=citations,
                artifacts=artifacts,
                metadata={"submode": submode},
            )

        except Exception as e:
            logger.error(f"TeachingAgent error: {e}", exc_info=True)
            return AgentResult(
                task_id=task.task_id,
                agent_name=self.name,
                status="failed",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # RAG integration
    # ------------------------------------------------------------------

    async def _search_context(
        self, task: AgentTask
    ) -> tuple[str, list[dict]]:
        """Search Qdrant for relevant content. Graceful fallback if empty."""
        try:
            from integrations.hybrid_retriever import hybrid_search

            results = hybrid_search(
                query=task.instruction,
                limit=6,
                document_type=task.filters.get("document_type"),
            )

            if not results:
                return "", []

            context = self._format_context(results)
            citations = self._extract_citations(results)
            return context, citations

        except Exception as e:
            logger.warning(f"RAG search failed (continuing without): {e}")
            return "", []

    @staticmethod
    def _format_context(results: list[dict]) -> str:
        """Format search results as numbered context block."""
        parts = []
        for i, r in enumerate(results, 1):
            payload = r.get("payload", r)
            title = payload.get("title", "Untitled")
            text = payload.get("text", "")[:800]
            doc_type = payload.get("document_type", "")
            parts.append(f"[{i}] {title} ({doc_type})\n{text}")
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _extract_citations(results: list[dict]) -> list[dict]:
        """Extract citation metadata from search results."""
        citations = []
        for i, r in enumerate(results, 1):
            payload = r.get("payload", r)
            citations.append({
                "number": i,
                "title": payload.get("title", "Untitled"),
                "source": payload.get("source", ""),
                "document_type": payload.get("document_type", ""),
                "score": r.get("score", 0.0),
            })
        return citations

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_prompt(
        instruction: str,
        rag_context: str,
        parent_results: Optional[list[dict]],
    ) -> str:
        """Build the complete user prompt with context."""
        parts = [f"## 요청\n{instruction}"]

        if parent_results:
            parent_text = "\n\n".join(
                f"### {r.get('agent_name', 'unknown')} 결과:\n{r.get('content', '')[:2000]}"
                for r in parent_results
            )
            parts.append(
                f"## 참고 자료 (이전 에이전트 결과)\n"
                f"아래 연구 자료를 기반으로 교육 콘텐츠를 설계하세요.\n\n{parent_text}"
            )

        if rag_context:
            parts.append(f"## 검색된 참고 문헌\n{rag_context}")

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    def _postprocess(
        self, submode: str, raw_answer: str, instruction: str
    ) -> tuple[str, list[dict]]:
        """Post-process LLM output based on sub-mode.

        Returns (content_markdown, artifacts_list).
        """
        artifacts: list[dict] = []

        if submode == "quiz":
            quiz = parse_quiz_response(raw_answer)
            if quiz:
                content = format_quiz_markdown(quiz)
                quiz_data = quiz.model_dump()
                filename = "quiz.json"
                artifacts.append({
                    "type": "quiz_json",
                    "filename": filename,
                    "data": quiz_data,
                })
                # Save to filesystem
                saved_path = self._save_artifact(filename, json.dumps(quiz_data, ensure_ascii=False, indent=2))
                if saved_path:
                    content += f"\n\n---\n📁 **저장 완료**: `{saved_path}`"
            else:
                content = raw_answer
                logger.warning("Quiz JSON parsing failed, returning raw response")

        elif submode == "notebook":
            title = self._extract_title(instruction)
            notebook = build_notebook_from_response(title, raw_answer)
            notebook_json = notebook_to_json(notebook)
            cell_count = len(notebook.get("cells", []))
            filename = f"{self._slugify(title)}.ipynb"

            artifacts.append({
                "type": "notebook",
                "filename": filename,
                "data": notebook_json,
            })
            # Save to filesystem
            saved_path = self._save_artifact(filename, notebook_json)

            content = (
                f"📓 **Jupyter 노트북 생성 완료**\n\n"
                f"- 제목: {title}\n"
                f"- 셀 수: {cell_count}\n"
            )
            if saved_path:
                content += f"- 📁 저장 위치: `{saved_path}`\n"
            content += (
                f"\n아래 artifact에서 `.ipynb` 파일을 다운로드할 수도 있습니다.\n\n"
                f"---\n\n### 노트북 미리보기\n\n{raw_answer}"
            )

        else:
            # lecture: pass through markdown as-is
            content = raw_answer

        return content, artifacts

    @staticmethod
    def _extract_title(instruction: str) -> str:
        """Extract a notebook/lecture title from the instruction."""
        # Remove common prefixes
        cleaned = re.sub(
            r"^(만들어|생성|작성|설계|구성)[줘주세요해]+[\s.,]*",
            "", instruction
        )
        # Truncate if too long
        title = cleaned.strip()[:60] or "Untitled Notebook"
        return title

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to a safe filename slug."""
        slug = re.sub(r"[^\w\s가-힣-]", "", text)
        slug = re.sub(r"\s+", "_", slug).strip("_")
        return slug[:50] or "notebook"

    @staticmethod
    def _save_artifact(filename: str, content: str) -> Optional[str]:
        """Save artifact to filesystem. Returns saved path or None."""
        from datetime import datetime
        from orchestrator.config import GENERATED_TEACHING_DIR

        save_dir = GENERATED_TEACHING_DIR
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
            # Add timestamp prefix to avoid overwrites
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = save_dir / f"{ts}_{filename}"
            save_path.write_text(content, encoding="utf-8")
            logger.info(f"Artifact saved: {save_path}")
            return str(save_path)
        except Exception as e:
            logger.warning(f"Failed to save artifact: {e}")
            return None

    # ------------------------------------------------------------------
    # Keyword routing
    # ------------------------------------------------------------------

    def can_handle(self, instruction: str) -> float:
        lower = instruction.lower()

        high_keywords = [
            "강의", "수업", "퀴즈", "lecture", "teaching",
            "커리큘럼", "노트북", "notebook", "시험",
        ]
        for kw in high_keywords:
            if kw in lower:
                return 0.85

        mid_keywords = ["과제", "실습", "교육", "세미나", "코드 예제"]
        for kw in mid_keywords:
            if kw in lower:
                return 0.6

        return 0.0
