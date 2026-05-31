"""
Writing Agent — Research Proposal, Manuscript, Abstract, Review Response

Sub-modes:
  - proposal: Research proposal with structured sections
  - manuscript: Scientific manuscript writing/revision
  - abstract: Structured abstract generation
  - review_response: Point-by-point reviewer response
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents.base import BaseAgent, AgentTask, AgentResult
from agents.writing.prompts import (
    PROPOSAL_PROMPT, MANUSCRIPT_PROMPT, ABSTRACT_PROMPT, REVIEW_RESPONSE_PROMPT,
)
from llm.pool import generate_answer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sub-mode detection keywords
# ---------------------------------------------------------------------------
_PROPOSAL_KEYWORDS = [
    "제안서", "proposal", "과제 신청", "연구비", "과제",
]
_ABSTRACT_KEYWORDS = [
    "초록", "abstract", "요약문",
]
_REVIEW_KEYWORDS = [
    "리뷰 응답", "리뷰어", "reviewer", "rebuttal", "심사", "리비전",
    "review response", "revision",
]
_MANUSCRIPT_KEYWORDS = [
    "원고", "논문 작성", "manuscript", "집필", "섹션",
    "introduction", "discussion", "conclusion",
]

_SUBMODE_PROMPTS = {
    "proposal": PROPOSAL_PROMPT,
    "manuscript": MANUSCRIPT_PROMPT,
    "abstract": ABSTRACT_PROMPT,
    "review_response": REVIEW_RESPONSE_PROMPT,
}


def _detect_submode(instruction: str) -> str:
    """Detect writing sub-mode from instruction keywords."""
    lower = instruction.lower()

    scores = {
        "abstract": sum(1 for kw in _ABSTRACT_KEYWORDS if kw in lower),
        "review_response": sum(1 for kw in _REVIEW_KEYWORDS if kw in lower),
        "proposal": sum(1 for kw in _PROPOSAL_KEYWORDS if kw in lower),
        "manuscript": sum(1 for kw in _MANUSCRIPT_KEYWORDS if kw in lower),
    }

    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return "manuscript"  # default


class WritingAgent(BaseAgent):
    name = "writing"
    description = "논문·제안서·리뷰 응답·초록"
    icon = "✍️"
    capabilities = [
        "proposal_writing", "manuscript_review", "abstract_generation",
        "review_response", "제안서", "논문", "초록", "리뷰",
        "proposal", "manuscript", "abstract", "writing",
    ]

    async def execute(self, task: AgentTask) -> AgentResult:
        submode = _detect_submode(task.instruction)
        logger.info(f"WritingAgent sub-mode: {submode}")

        try:
            # RAG: search for relevant research content
            rag_context, citations = await self._search_context(task)

            # Detect full manuscript request → section-by-section writing
            instruction_lower = task.instruction.lower()
            is_full_manuscript = (
                submode == "manuscript"
                and any(kw in instruction_lower for kw in [
                    "전체", "full", "처음부터", "논문 작성", "manuscript 작성",
                    "서론부터", "introduction부터",
                ])
            )

            if is_full_manuscript:
                return await self._section_write(task, rag_context, citations)

            # Build user prompt
            user_prompt = self._build_user_prompt(
                task.instruction, rag_context, task.parent_results
            )

            # Select prompt
            system_prompt = _SUBMODE_PROMPTS[submode]

            # Generate with dynamic model selection
            chat_history = task.context.get("chat_history", [])
            selected_model = self.select_model(task)
            logger.info(f"WritingAgent using model: {selected_model}")
            answer = await generate_answer(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=selected_model,
                chat_history=chat_history,
            )

            # Save only if response contains explicit artifact marker
            content = answer
            artifacts: list[dict] = []
            artifact_content = self._extract_artifact(answer)
            if artifact_content:
                saved_path = self._save_artifact(submode, artifact_content)
                if saved_path:
                    content += f"\n\n---\n📁 **산출물 저장**: `{saved_path}`"
                    artifacts.append({
                        "type": f"writing_{submode}",
                        "filename": Path(saved_path).name,
                        "data": artifact_content,
                    })

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
            logger.error(f"WritingAgent error: {e}", exc_info=True)
            return AgentResult(
                task_id=task.task_id, agent_name=self.name,
                status="failed", error=str(e),
            )

    # ------------------------------------------------------------------
    # Section-by-section writing (full manuscript)
    # ------------------------------------------------------------------

    _SECTIONS = [
        ("Introduction", "서론: 연구 배경, 기존 연구 리뷰, 연구 목적 및 기여를 명시하세요."),
        ("Methods", "방법론: 실험 설계, 계산 방법, 데이터 처리 과정을 재현 가능한 수준으로 기술하세요."),
        ("Results", "결과: 주요 실험/계산 결과를 객관적으로 서술하세요. 그래프/테이블 설명을 포함하세요."),
        ("Discussion", "논의: 결과의 해석, 기존 연구와의 비교, 한계점, 시사점을 논하세요."),
        ("Conclusion", "결론: 핵심 발견 요약, 학술적 기여, 향후 연구 방향을 제시하세요."),
    ]

    async def _section_write(
        self, task: AgentTask, rag_context: str, citations: list[dict],
    ) -> AgentResult:
        """Write manuscript section by section for coherence.

        Each section receives the previous sections as context,
        ensuring logical flow and consistent terminology.
        """
        selected_model = self.select_model(task)
        logger.info(f"WritingAgent section-by-section mode, model: {selected_model}")

        written_sections: list[str] = []
        all_content_parts: list[str] = []

        for section_name, section_guide in self._SECTIONS:
            # Build section-specific prompt
            section_prompt = (
                f"## 전체 요청\n{task.instruction}\n\n"
                f"## 현재 작성할 섹션\n**{section_name}**\n\n"
                f"### 작성 가이드\n{section_guide}\n\n"
            )

            if written_sections:
                section_prompt += (
                    f"## 이미 작성된 섹션 (일관성 유지)\n"
                    f"{''.join(written_sections)}\n\n"
                )

            if task.parent_results:
                parent_text = "\n\n".join(
                    f"### {r.get('agent_name', 'unknown')} 결과:\n{r.get('content', '')[:1500]}"
                    for r in task.parent_results
                )
                section_prompt += f"## 참고 자료 (이전 에이전트 분석 결과)\n{parent_text}\n\n"

            if rag_context:
                section_prompt += f"## 검색된 참고 문헌\n{rag_context}\n\n"

            section_prompt += (
                "### 규칙\n"
                "- 이 섹션만 작성하세요 (다른 섹션 제목을 포함하지 마세요)\n"
                "- 인용은 [1], [2] 형식\n"
                "- 한국어 작성, 기술 용어 영어 병기\n"
                "- 학술 논문 스타일 유지\n"
            )

            answer = await generate_answer(
                system_prompt=_SUBMODE_PROMPTS["manuscript"],
                user_prompt=section_prompt,
                model=selected_model,
            )

            section_text = f"\n\n## {section_name}\n\n{answer}"
            written_sections.append(section_text)
            all_content_parts.append(section_text)
            logger.info(f"Section '{section_name}' completed ({len(answer)} chars)")

        # Combine all sections
        full_content = f"# {task.instruction[:60]}\n" + "".join(all_content_parts)

        # Save as artifact
        artifacts: list[dict] = []
        saved_path = self._save_artifact("manuscript_full", full_content)
        if saved_path:
            full_content += f"\n\n---\n📁 **전체 원고 저장**: `{saved_path}`"
            artifacts.append({
                "type": "writing_manuscript_full",
                "filename": Path(saved_path).name,
                "data": full_content,
            })

        return AgentResult(
            task_id=task.task_id,
            agent_name=self.name,
            status="completed",
            content=full_content,
            citations=citations,
            artifacts=artifacts,
            metadata={"submode": "manuscript", "mode": "section_by_section",
                       "sections_written": len(self._SECTIONS)},
        )

    # ------------------------------------------------------------------
    # RAG
    # ------------------------------------------------------------------

    async def _search_context(
        self, task: AgentTask
    ) -> tuple[str, list[dict]]:
        """Search Qdrant for relevant content."""
        try:
            from integrations.hybrid_retriever import hybrid_search

            results = hybrid_search(
                query=task.instruction,
                limit=8,
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
        parts = [f"## 요청\n{instruction}"]

        if parent_results:
            parent_text = "\n\n".join(
                f"### {r.get('agent_name', 'unknown')} 결과:\n{r.get('content', '')[:2000]}"
                for r in parent_results
            )
            parts.append(
                f"## 참고 자료 (이전 에이전트 분석 결과)\n"
                f"아래 분석 결과를 기반으로 작성하세요.\n\n{parent_text}"
            )

        if rag_context:
            parts.append(f"## 검색된 참고 문헌\n{rag_context}")

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Artifact extraction & file save
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_artifact(content: str) -> Optional[str]:
        """Extract artifact only if [ARTIFACT]...[/ARTIFACT] markers exist."""
        import re
        match = re.search(
            r"\[ARTIFACT\]\s*(.*?)\s*\[/ARTIFACT\]", content, re.DOTALL
        )
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _save_artifact(submode: str, content: str) -> Optional[str]:
        """Save extracted artifact to file."""
        from orchestrator.config import GENERATED_WRITING_DIR
        save_dir = GENERATED_WRITING_DIR
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ts}_{submode}.md"
            save_path = save_dir / filename
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
        high = [
            "제안서", "proposal", "원고", "manuscript", "리뷰 응답",
            "초록", "abstract", "rebuttal", "집필",
        ]
        for kw in high:
            if kw in lower:
                return 0.85
        mid = ["작성", "써줘", "draft", "write", "리비전"]
        for kw in mid:
            if kw in lower:
                return 0.6
        return 0.0
