"""
Lab Orchestrator — Multi-LLM Debate Engine

Implements iMAD (Intelligent Multi-Agent Debate):
  1. Complexity classifier decides if debate is needed
  2. 3 panelists (GPT, Claude, Gemini) debate in 3 rounds
  3. Judge synthesizes final answer

Usage:
    from orchestrator.debate import debate_engine
    result = await debate_engine.run(question, context)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from llm.pool import generate_answer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "debate.yaml"


def _load_config() -> dict:
    """Load debate configuration."""
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f).get("debate", {})
    return {}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class PanelistConfig:
    name: str
    role: str
    provider: str
    model: str


@dataclass
class DebateMessage:
    panelist: str
    round_num: int
    content: str
    elapsed_ms: float = 0.0


@dataclass
class DebateResult:
    question: str
    final_answer: str
    rounds: list[list[DebateMessage]] = field(default_factory=list)
    judge_reasoning: str = ""
    total_elapsed_ms: float = 0.0
    complexity_score: float = 0.0
    debated: bool = True


# ---------------------------------------------------------------------------
# Complexity Classifier (iMAD)
# ---------------------------------------------------------------------------
COMPLEXITY_PROMPT = """You are a question complexity classifier for academic research.
Rate the complexity of the following question on a scale of 0.0 to 1.0.

Criteria:
- 0.0-0.3: Simple factual question, lookup, definition
- 0.4-0.6: Moderate analysis, single-perspective answer sufficient
- 0.7-1.0: Complex reasoning, multiple perspectives needed, trade-offs, methodology comparison

Respond with ONLY a JSON object: {"score": 0.XX, "reason": "brief reason"}
"""


async def classify_complexity(
    question: str,
    config: dict,
) -> tuple[float, str]:
    """Classify question complexity for iMAD triggering.

    Returns (score, reason).
    """
    complexity_cfg = config.get("complexity", {})
    classifier_model = complexity_cfg.get("classifier_model", "gpt-5.4-nano")
    boost_keywords = complexity_cfg.get("boost_keywords", [])

    # Keyword boost: check if any boost keywords are present
    keyword_boost = 0.0
    question_lower = question.lower()
    for kw in boost_keywords:
        if kw.lower() in question_lower:
            keyword_boost = 0.15
            break

    try:
        response = await generate_answer(
            system_prompt=COMPLEXITY_PROMPT,
            user_prompt=question,
            model=classifier_model,
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        import json
        data = json.loads(response)
        score = min(1.0, float(data.get("score", 0.5)) + keyword_boost)
        reason = data.get("reason", "")
        return score, reason

    except Exception as e:
        logger.warning(f"Complexity classification failed: {e}")
        # Fallback: use keyword heuristic only
        return 0.5 + keyword_boost, "classification_failed"


# ---------------------------------------------------------------------------
# Round protocols
# ---------------------------------------------------------------------------
ROUND1_PROMPT = """## 당신의 역할
{role}

## 질문
{question}

{context_section}

## 지시사항
이 질문에 대해 당신의 전문적 관점에서 독립적으로 답변하세요.
- 핵심 논점을 명확히 제시하세요.
- 근거를 들어 주장을 뒷받침하세요.
- 한국어로 작성하되, 영어 기술 용어는 그대로 사용하세요.
"""

ROUND2_PROMPT = """## 당신의 역할
{role}

## 원래 질문
{question}

## Round 1 — 다른 참가자들의 답변
{other_responses}

## 지시사항
다른 참가자들의 답변을 읽고 **비판적으로 검토**하세요:
1. 동의하는 부분과 그 이유
2. 반대하거나 보완이 필요한 부분과 그 이유
3. 놓친 관점이나 추가할 논점
한국어로 작성하되, 영어 기술 용어는 그대로 사용하세요.
"""

ROUND3_PROMPT = """## 당신의 역할
{role}

## 원래 질문
{question}

## Round 1 — 초기 답변
{round1_responses}

## Round 2 — 상호 비판
{round2_responses}

## 지시사항
이전 라운드의 토론을 바탕으로 **최종 입장**을 정리하세요:
1. 비판을 수용하거나 반박하세요.
2. 최종 결론을 명확히 진술하세요.
3. 남은 불확실성이 있다면 명시하세요.
한국어로 작성하되, 영어 기술 용어는 그대로 사용하세요.
"""

JUDGE_PROMPT_TEMPLATE = """## 종합자 역할
{judge_prompt}

## 사용자의 원래 질문
{question}

## 전문가 토론 결과

### Round 3 — 최종 입장

{round3_responses}

## 지시사항
위 토론 결과를 종합하여 사용자에게 최종 답변을 작성하세요.
"""


# ---------------------------------------------------------------------------
# Debate Engine
# ---------------------------------------------------------------------------
class DebateEngine:
    """Multi-LLM Debate Engine with iMAD complexity gating."""

    def __init__(self):
        self._config: dict = {}
        self._panelists: list[PanelistConfig] = []
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self._config = _load_config()
            self._panelists = [
                PanelistConfig(**p)
                for p in self._config.get("panelists", [])
            ]
            self._loaded = True

    @property
    def enabled(self) -> bool:
        self._ensure_loaded()
        return self._config.get("enabled", False)

    async def should_debate(self, question: str) -> tuple[bool, float, str]:
        """Determine if a question warrants debate (iMAD).

        Returns (should_debate, complexity_score, reason).
        """
        self._ensure_loaded()

        if not self.enabled:
            return False, 0.0, "debate_disabled"

        if not self._config.get("auto_trigger", True):
            return True, 1.0, "auto_trigger_disabled"

        threshold = self._config.get("complexity", {}).get("threshold", 0.7)
        score, reason = await classify_complexity(question, self._config)

        return score >= threshold, score, reason

    async def run(
        self,
        question: str,
        context: str = "",
        force: bool = False,
        num_rounds: Optional[int] = None,
    ) -> DebateResult:
        """Run the full debate pipeline.

        Args:
            question: User's question.
            context: Additional context (memory, workspace, etc.).
            force: Skip complexity check and force debate.
            num_rounds: Override number of debate rounds (2 or 3).

        Returns:
            DebateResult with final answer and debate history.
        """
        self._ensure_loaded()
        start_time = time.time()

        # iMAD gating
        if not force:
            should, score, reason = await self.should_debate(question)
            if not should:
                logger.info(
                    f"Debate skipped (score={score:.2f}, reason={reason})"
                )
                # Fall through to single-model response
                answer = await generate_answer(
                    system_prompt="You are a research assistant. 한국어로 답변하세요.",
                    user_prompt=question,
                    model=self._config.get("judge", {}).get("model"),
                )
                return DebateResult(
                    question=question,
                    final_answer=answer,
                    complexity_score=score,
                    debated=False,
                    total_elapsed_ms=(time.time() - start_time) * 1000,
                )
        else:
            score = 1.0

        context_section = f"## 배경 정보\n{context}" if context else ""
        effective_rounds = num_rounds or self._config.get("rounds", 3)
        effective_rounds = max(1, min(3, effective_rounds))  # clamp 1-3
        all_rounds: list[list[DebateMessage]] = []

        # ── Round 1: Independent responses (parallel) ──
        logger.info("Debate Round 1: Independent responses")
        r1_tasks = []
        for p in self._panelists:
            prompt = ROUND1_PROMPT.format(
                role=p.role,
                question=question,
                context_section=context_section,
            )
            r1_tasks.append(self._call_panelist(p, prompt, round_num=1))

        round1 = await asyncio.gather(*r1_tasks)
        all_rounds.append(round1)

        # ── Round 2: Cross-critique ──
        if effective_rounds >= 2:
            logger.info("Debate Round 2: Cross-critique")
            r2_tasks = []
            for i, p in enumerate(self._panelists):
                other_responses = self._format_others(round1, exclude=p.name)
                prompt = ROUND2_PROMPT.format(
                    role=p.role,
                    question=question,
                    other_responses=other_responses,
                )
                r2_tasks.append(self._call_panelist(p, prompt, round_num=2))

            round2 = await asyncio.gather(*r2_tasks)
            all_rounds.append(round2)

        # ── Round 3: Final position ──
        if effective_rounds >= 3:
            logger.info("Debate Round 3: Final position")
            r1_text = self._format_all(round1)
            r2_text = self._format_all(round2) if effective_rounds >= 2 else ""
            r3_tasks = []
            for p in self._panelists:
                prompt = ROUND3_PROMPT.format(
                    role=p.role,
                    question=question,
                    round1_responses=r1_text,
                    round2_responses=r2_text,
                )
                r3_tasks.append(self._call_panelist(p, prompt, round_num=3))

            round3 = await asyncio.gather(*r3_tasks)
            all_rounds.append(round3)

        # ── Judge: Synthesize ──
        logger.info("Debate: Judge synthesizing")
        final_round = all_rounds[-1]
        r3_text = self._format_all(final_round)

        judge_cfg = self._config.get("judge", {})
        judge_prompt = JUDGE_PROMPT_TEMPLATE.format(
            judge_prompt=judge_cfg.get("prompt", "종합하세요."),
            question=question,
            round3_responses=r3_text,
        )

        final_answer = await generate_answer(
            system_prompt="",
            user_prompt=judge_prompt,
            model=judge_cfg.get("model", "gpt-5.4-mini"),
            provider=judge_cfg.get("provider"),
            temperature=0.3,
        )

        total_ms = (time.time() - start_time) * 1000
        logger.info(f"Debate completed in {total_ms:.0f}ms")

        return DebateResult(
            question=question,
            final_answer=final_answer,
            rounds=all_rounds,
            complexity_score=score,
            debated=True,
            total_elapsed_ms=total_ms,
        )

    async def _call_panelist(
        self,
        panelist: PanelistConfig,
        prompt: str,
        round_num: int,
    ) -> DebateMessage:
        """Call a single panelist and return their response."""
        start = time.time()
        try:
            response = await generate_answer(
                system_prompt="",
                user_prompt=prompt,
                model=panelist.model,
                provider=panelist.provider,
                temperature=0.4,
            )
        except Exception as e:
            logger.error(f"Panelist {panelist.name} failed: {e}")
            response = f"[{panelist.name} 응답 실패: {e}]"

        elapsed = (time.time() - start) * 1000
        logger.info(
            f"  {panelist.name} (R{round_num}): "
            f"{len(response)} chars, {elapsed:.0f}ms"
        )
        return DebateMessage(
            panelist=panelist.name,
            round_num=round_num,
            content=response,
            elapsed_ms=elapsed,
        )

    def _format_others(
        self, messages: list[DebateMessage], exclude: str
    ) -> str:
        """Format other panelists' responses (excluding one)."""
        parts = []
        for m in messages:
            if m.panelist != exclude:
                parts.append(f"### {m.panelist}\n{m.content}")
        return "\n\n".join(parts)

    def _format_all(self, messages: list[DebateMessage]) -> str:
        """Format all panelists' responses."""
        parts = []
        for m in messages:
            parts.append(f"### {m.panelist}\n{m.content}")
        return "\n\n".join(parts)

    def reload_config(self):
        """Hot-reload debate configuration."""
        self._loaded = False
        self._ensure_loaded()
        logger.info("Debate config reloaded")

    async def run_stream(
        self,
        question: str,
        context: str = "",
        num_rounds: Optional[int] = None,
    ):
        """Run debate with SSE-style event streaming.

        Yields dicts: {"event": str, "data": dict}
        Events: debate_start, round_start, panelist_done, judge_start, debate_done
        """
        self._ensure_loaded()
        start_time = time.time()
        effective_rounds = num_rounds or self._config.get("rounds", 3)
        effective_rounds = max(1, min(3, effective_rounds))

        yield {"event": "debate_start", "data": {
            "panelists": [p.name for p in self._panelists],
            "rounds": effective_rounds,
        }}

        context_section = f"## 배경 정보\n{context}" if context else ""
        all_rounds: list[list[DebateMessage]] = []

        # ── Round 1 ──
        yield {"event": "round_start", "data": {"round": 1, "type": "independent"}}
        r1_tasks = []
        for p in self._panelists:
            prompt = ROUND1_PROMPT.format(
                role=p.role, question=question, context_section=context_section,
            )
            r1_tasks.append(self._call_panelist(p, prompt, round_num=1))
        round1 = await asyncio.gather(*r1_tasks)
        all_rounds.append(round1)
        for m in round1:
            yield {"event": "panelist_done", "data": {
                "panelist": m.panelist, "round": 1,
                "length": len(m.content), "elapsed_ms": m.elapsed_ms,
            }}

        # ── Round 2 ──
        round2 = []
        if effective_rounds >= 2:
            yield {"event": "round_start", "data": {"round": 2, "type": "cross_critique"}}
            r2_tasks = []
            for p in self._panelists:
                other = self._format_others(round1, exclude=p.name)
                prompt = ROUND2_PROMPT.format(
                    role=p.role, question=question, other_responses=other,
                )
                r2_tasks.append(self._call_panelist(p, prompt, round_num=2))
            round2 = await asyncio.gather(*r2_tasks)
            all_rounds.append(round2)
            for m in round2:
                yield {"event": "panelist_done", "data": {
                    "panelist": m.panelist, "round": 2,
                    "length": len(m.content), "elapsed_ms": m.elapsed_ms,
                }}

        # ── Round 3 ──
        if effective_rounds >= 3:
            yield {"event": "round_start", "data": {"round": 3, "type": "final_position"}}
            r1_text = self._format_all(round1)
            r2_text = self._format_all(round2) if effective_rounds >= 2 else ""
            r3_tasks = []
            for p in self._panelists:
                prompt = ROUND3_PROMPT.format(
                    role=p.role, question=question,
                    round1_responses=r1_text, round2_responses=r2_text,
                )
                r3_tasks.append(self._call_panelist(p, prompt, round_num=3))
            round3 = await asyncio.gather(*r3_tasks)
            all_rounds.append(round3)
            for m in round3:
                yield {"event": "panelist_done", "data": {
                    "panelist": m.panelist, "round": 3,
                    "length": len(m.content), "elapsed_ms": m.elapsed_ms,
                }}

        # ── Judge ──
        yield {"event": "judge_start", "data": {}}
        final_round = all_rounds[-1]
        r_text = self._format_all(final_round)
        judge_cfg = self._config.get("judge", {})
        judge_prompt = JUDGE_PROMPT_TEMPLATE.format(
            judge_prompt=judge_cfg.get("prompt", "종합하세요."),
            question=question, round3_responses=r_text,
        )
        final_answer = await generate_answer(
            system_prompt="", user_prompt=judge_prompt,
            model=judge_cfg.get("model", "gpt-5.4-mini"),
            provider=judge_cfg.get("provider"), temperature=0.3,
        )
        total_ms = (time.time() - start_time) * 1000

        yield {"event": "debate_done", "data": {
            "final_answer": final_answer,
            "total_elapsed_ms": total_ms,
            "rounds_completed": len(all_rounds),
        }}


# Module-level singleton
debate_engine = DebateEngine()
