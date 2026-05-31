"""
Teaching Agent — Quiz Builder

Pydantic models for structured quiz generation and JSON parsing.
"""

import json
import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class QuizQuestion(BaseModel):
    """A single quiz question with answer and explanation."""
    number: int
    type: Literal["multiple_choice", "short_answer", "true_false"]
    question: str
    options: list[str] = Field(default_factory=list)
    answer: str
    explanation: str
    difficulty: Literal["basic", "intermediate", "advanced"] = "intermediate"
    concept: str = ""


class Quiz(BaseModel):
    """A complete quiz with metadata and questions."""
    title: str
    topic: str = ""
    target_level: str = "undergraduate"
    questions: list[QuizQuestion]


def parse_quiz_response(raw: str) -> Optional[Quiz]:
    """Parse LLM output into a structured Quiz.

    Tries to extract JSON from the response, handling common LLM output
    patterns like markdown code fences.

    Returns None if parsing fails.
    """
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3].rstrip()

    # Try to find JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        logger.warning("No JSON object found in quiz response")
        return None

    json_str = text[start:end]

    try:
        data = json.loads(json_str)
        return Quiz.model_validate(data)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to parse quiz JSON: {e}")
        return None


def format_quiz_markdown(quiz: Quiz) -> str:
    """Format a Quiz object as readable Markdown."""
    lines = [f"# {quiz.title}", ""]
    if quiz.topic:
        lines.append(f"**주제**: {quiz.topic}")
    lines.append(f"**대상**: {quiz.target_level}")
    lines.append(f"**문항 수**: {len(quiz.questions)}")
    lines.append("")

    for q in quiz.questions:
        difficulty_badge = {"basic": "🟢", "intermediate": "🟡", "advanced": "🔴"}
        badge = difficulty_badge.get(q.difficulty, "⚪")
        lines.append(f"---\n\n### 문제 {q.number} {badge} ({q.difficulty})")
        lines.append(f"\n**[{q.type}]** {q.question}\n")

        if q.options:
            for opt in q.options:
                lines.append(f"- {opt}")
            lines.append("")

        lines.append(f"<details><summary>정답 보기</summary>\n")
        lines.append(f"**정답**: {q.answer}\n")
        lines.append(f"**해설**: {q.explanation}")
        if q.concept:
            lines.append(f"\n**관련 개념**: {q.concept}")
        lines.append(f"\n</details>\n")

    return "\n".join(lines)
