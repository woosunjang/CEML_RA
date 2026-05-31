"""
lab-paper-scout: Paper summarizer using Gemini API
"""
from __future__ import annotations

import json
import logging
import time
from typing import Dict, List, Optional

from google import genai

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """당신은 재료공학 연구 분석 전문가입니다.
아래 논문의 내용을 분석하여 다음 JSON 형식으로 출력해 주세요.

**출력 형식 (반드시 유효한 JSON으로):**
```json
{{
  "tldr": "1문장 핵심 요약 (한국어, 20단어 이내)",
  "summary_kr": "한국어 요약 (3~5문장, 핵심 내용 위주)",
  "key_contribution": "이 논문의 핵심 기여/새로운 점 (한국어, 1~2문장)",
  "methodology": "사용된 방법론 요약 (한국어, 1~2문장)",
  "key_results": "주요 결과/수치 (한국어, 1~2문장)",
  "lab_relevance": "CEML 연구실 관점에서 활용 가능성 (한국어, 1~2문장. 관련 없으면 빈 문자열)",
  "tags": ["관련 키워드 태그 3~5개 (영어)"],
  "relevance_score": 0
}}
```

**relevance_score 기준:**
- 아래에 제공된 관심 토픽과의 관련도를 0~100으로 매겨 주세요.
- 100: 토픽의 핵심 논문 / 0: 전혀 무관

**lab_relevance 기준:**
- 아래 토픽의 키워드와 직접적으로 관련된 방법론, 데이터, 또는 결과가 있는 경우에만 작성
- 관련 없으면 빈 문자열 ""로 출력

---

**관심 토픽:** {topics}

**논문 제목:** {title}

**초록:** {abstract}

**본문 (발췌):**
{body_text}
"""


class Summarizer:
    """Analyzes papers using Gemini API."""

    def __init__(self, config: Dict):
        api_config = config.get("api", {})
        self.model_name = api_config.get("gemini_model", "gemini-2.5-flash")
        self.throttle = api_config.get("throttle_seconds", 2)
        self.client = genai.Client()

    def analyze(
        self, paper: Dict, extracted: Optional[Dict], topics: List[Dict]
    ) -> Optional[Dict]:
        title = paper.get("title") or "Unknown"
        abstract = paper.get("abstract") or ""

        body_text = ""
        if extracted and extracted.get("sections"):
            for section in extracted["sections"][:5]:
                body_text += f"\n### {section['name']}\n{section['text'][:2000]}\n"
        elif abstract:
            body_text = abstract

        body_text = body_text[:8000]

        # Format topics with display_name and keywords for better context
        if topics:
            topic_parts = []
            for t in topics:
                display = t.get("display_name") or t.get("name", "")
                kw = t.get("keywords", [])
                if kw:
                    topic_parts.append(f"{display} ({', '.join(kw[:3])})")
                else:
                    topic_parts.append(display)
            topic_str = "; ".join(topic_parts)
        else:
            topic_str = "일반 재료공학"

        prompt = ANALYSIS_PROMPT.format(
            topics=topic_str,
            title=title,
            abstract=abstract[:2000],
            body_text=body_text,
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )

            text = response.text.strip()

            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            analysis = json.loads(text)
            logger.info(
                f"  Analyzed: {title[:60]}... "
                f"(relevance: {analysis.get('relevance_score', '?')})"
            )

            time.sleep(self.throttle)
            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"  JSON parse error for '{title[:40]}': {e}")
            return None
        except Exception as e:
            logger.error(f"  Analysis failed for '{title[:40]}': {e}")
            return None
