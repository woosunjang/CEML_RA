"""
Presentation Agent — PPTX Slide Deck Generation

Features:
  - JSON structured output (reduced parsing failures)
  - Theme customization (dark_academic, light_clean, navy_gold, minimal_gray)
  - Optional image generation (Google Gemini / OpenAI gpt-image)
  - 2-pass image prompt enhancement
  - 16:9 widescreen standard
"""

import base64
import gc
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents.base import BaseAgent, AgentTask, AgentResult
from agents.presentation.prompts import (
    PRESENTATION_PROMPT, OUTLINE_PROMPT, CHUNK_PROMPT,
    PROSE_MODE_INSTRUCTION, BULLET_MODE_INSTRUCTION,
)
from agents.presentation.pptx_builder import (
    parse_slides_json, build_pptx, format_slides_markdown, detect_theme,
)
from llm.pool import generate_answer

logger = logging.getLogger(__name__)

# Threshold: if requested slides >= this, use chunked generation
CHUNK_THRESHOLD = 12
CHUNK_SIZE = 5

# Script executed in a subprocess for each chunk.
# Subprocess dies after completion → OS reclaims 100% of memory.
_CHUNK_SUBPROCESS_SCRIPT = '''
import sys, json, asyncio
if len(sys.argv) > 3:
    sys.path.insert(0, sys.argv[3])
else:
    sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(".env")

from llm.pool import generate_answer
from agents.presentation.prompts import CHUNK_PROMPT
from agents.presentation.pptx_builder import parse_slides_json

job_file, result_file = sys.argv[1], sys.argv[2]
with open(job_file) as f:
    job = json.load(f)

outline_text = json.dumps(job["chunk_outline"], ensure_ascii=False, indent=2)
chunk_prompt = CHUNK_PROMPT.format(
    content_mode_instruction=job["mode_instruction"],
    start_num=job["start_num"],
    end_num=job["end_num"],
)

user_msg_parts = [
    f"## 원래 요청\\n{job['instruction']}",
    f"## 전체 발표 제목\\n{job['title']}"
]

if job.get("parent_results"):
    parent_text = "\\n\\n".join(
        f"### {r.get('agent_name', 'unknown')} 결과:\\n{r.get('content', '')[:2000]}"
        for r in job["parent_results"]
    )
    user_msg_parts.append(
        f"## 참고 자료 (이전 에이전트 결과)\\n"
        f"아래 내용을 기반으로 발표 자료를 구성하세요.\\n\\n{parent_text}"
    )

if job.get("rag_context"):
    user_msg_parts.append(f"## 검색된 참고 문헌\\n{job['rag_context']}")

user_msg_parts.append(
    f"## 이 청크의 슬라이드 아웃라인\\n{outline_text}\\n\\n"
    f"슬라이드 {job['start_num']}~{job['end_num']}의 상세 내용을 생성하세요."
)

user_msg = "\\n\\n".join(user_msg_parts)

async def run():
    raw = await generate_answer(
        system_prompt=chunk_prompt,
        user_prompt=user_msg,
        model=job["model"],
        response_format={"type": "json_object"},
    )
    data = parse_slides_json(raw)
    slides = data.get("slides", []) if data else []
    with open(result_file, "w") as f:
        json.dump(slides, f, ensure_ascii=False)

asyncio.run(run())
'''

# ---------------------------------------------------------------------------
# Explicit opt-in: 사용자가 명시적으로 요청한 경우에만 파일/이미지 생성
# ---------------------------------------------------------------------------

# PPTX 파일 생성을 트리거하는 명시적 키워드
_PPTX_KEYWORDS = [
    "pptx", "ppt", "파워포인트", "powerpoint",
    "파일로", "파일 만들", "파일 생성",
    "다운로드", "download",
]

# 이미지 생성을 트리거하는 명시적 키워드
_IMAGE_KEYWORDS = [
    "이미지 생성", "이미지 만들", "이미지 포함", "이미지도",
    "그림 생성", "그림 만들", "그림 포함", "그림도",
    "다이어그램 생성", "다이어그램 만들", "다이어그램 포함",
    "image generat", "with image", "include image",
    "generate diagram", "include diagram",
]


def _wants_pptx(instruction: str) -> bool:
    """Check if user explicitly requested PPTX file generation."""
    lower = instruction.lower()
    return any(kw in lower for kw in _PPTX_KEYWORDS)


def _wants_images(instruction: str) -> bool:
    """Check if user explicitly requested image generation."""
    lower = instruction.lower()
    return any(kw in lower for kw in _IMAGE_KEYWORDS)


# 마크다운 저장을 트리거하는 명시적 키워드
_SAVE_KEYWORDS = [
    "저장", "save", "파일로", "파일 생성", "파일 만들",
    "마크다운으로", "markdown", "md로", "기록",
]


def _wants_save(instruction: str) -> bool:
    """Check if user explicitly requested saving the output."""
    lower = instruction.lower()
    return any(kw in lower for kw in _SAVE_KEYWORDS)


class PresentationAgent(BaseAgent):
    name = "presentation"
    description = "PPT·포스터·다이어그램"
    icon = "📽️"
    capabilities = [
        "slide_generation", "poster_layout", "diagram_creation",
        "ppt", "발표", "슬라이드", "포스터", "presentation",
    ]

    async def execute(self, task: AgentTask) -> AgentResult:
        logger.info("PresentationAgent executing")
        generate_pptx = _wants_pptx(task.instruction)
        generate_images = _wants_images(task.instruction)
        save_output = _wants_save(task.instruction)

        try:
            # RAG
            rag_context, citations = await self._search_context(task)

            # Detect requested slide count
            requested_slides = self._detect_slide_count(task.instruction)
            selected_model = self.select_model(task)
            logger.info(f"PresentationAgent using model: {selected_model}, "
                        f"requested_slides={requested_slides}")

            chat_history = task.context.get("chat_history", [])

            # Choose generation strategy based on slide count
            if requested_slides >= CHUNK_THRESHOLD:
                slide_data = await self._chunked_generate(
                    task.instruction, rag_context, task.parent_results,
                    selected_model, chat_history, requested_slides,
                )
            else:
                slide_data = await self._single_generate(
                    task.instruction, rag_context, task.parent_results,
                    selected_model, chat_history,
                )

            # Post-process
            content, artifacts = await self._postprocess_data(
                slide_data, task.instruction, generate_pptx, generate_images,
                save_output,
            )

            return AgentResult(
                task_id=task.task_id,
                agent_name=self.name,
                status="completed",
                content=content,
                citations=citations,
                artifacts=artifacts,
            )

        except Exception as e:
            logger.error(f"PresentationAgent error: {e}", exc_info=True)
            return AgentResult(
                task_id=task.task_id, agent_name=self.name,
                status="failed", error=str(e),
            )

    # ------------------------------------------------------------------
    # Generation strategies
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_slide_count(instruction: str) -> int:
        """Extract requested slide count from instruction."""
        import re
        m = re.search(r'(\d{1,3})\s*슬라이드|(\d{1,3})\s*slide', instruction.lower())
        if m:
            return int(m.group(1) or m.group(2))
        return 10  # default

    async def _single_generate(
        self, instruction, rag_context, parent_results, model, chat_history
    ) -> Optional[dict]:
        """Original single-call generation for small slide counts."""
        user_prompt = self._build_user_prompt(instruction, rag_context, parent_results)
        answer = await generate_answer(
            system_prompt=PRESENTATION_PROMPT,
            user_prompt=user_prompt,
            model=model,
            chat_history=chat_history,
            response_format={"type": "json_object"},
        )
        result = parse_slides_json(answer)
        del answer
        gc.collect()
        return result

    async def _chunked_generate(
        self, instruction, rag_context, parent_results,
        model, chat_history, total_slides,
    ) -> Optional[dict]:
        """Memory-safe chunked generation using temp files.

        Each chunk result is written to a temp file and the in-memory
        data is deleted immediately. Final assembly reads from files.
        This prevents Python's allocator from accumulating memory.
        """
        import tempfile

        logger.info(f"Using chunked generation: {total_slides} slides "
                    f"in chunks of {CHUNK_SIZE}")

        # --- Step 1: Generate outline only (small response) ---
        outline_user = self._build_user_prompt(instruction, rag_context, parent_results)
        outline_raw = await generate_answer(
            system_prompt=OUTLINE_PROMPT,
            user_prompt=outline_user,
            model=model,
            chat_history=chat_history,
            response_format={"type": "json_object"},
        )
        outline = parse_slides_json(outline_raw)
        del outline_raw, outline_user
        gc.collect()

        if not outline or "outline" not in outline:
            logger.error("Outline generation failed")
            return None

        logger.info(f"Outline generated: {len(outline['outline'])} slides")

        # Detect content mode from instruction
        prose_keywords = ["자세하게", "상세", "줄글", "해설", "설명", "prose", "detailed"]
        is_prose = any(kw in instruction.lower() for kw in prose_keywords)
        mode_instruction = PROSE_MODE_INSTRUCTION if is_prose else BULLET_MODE_INSTRUCTION

        # --- Step 2: Generate content in chunks via subprocess ---
        outline_items = outline["outline"]
        total = len(outline_items)
        chunk_files = []

        for chunk_start in range(0, total, CHUNK_SIZE):
            chunk_end = min(chunk_start + CHUNK_SIZE, total)
            chunk_outline = outline_items[chunk_start:chunk_end]

            logger.info(f"Generating chunk: slides {chunk_start+1}-{chunk_end}")

            # Write chunk job to temp file
            job = {
                "instruction": instruction,
                "title": outline.get("title", ""),
                "chunk_outline": chunk_outline,
                "mode_instruction": mode_instruction,
                "start_num": chunk_start + 1,
                "end_num": chunk_end,
                "model": model,
                "rag_context": rag_context,
                "parent_results": parent_results,
            }

            job_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, dir="/tmp"
            )
            json.dump(job, job_file, ensure_ascii=False)
            job_file.close()

            result_file = job_file.name + ".result"

            # Run chunk generation in subprocess (non-blocking)
            try:
                from orchestrator.config import PROJECT_ROOT
                import asyncio as _aio
                proc = await _aio.create_subprocess_exec(
                    sys.executable, "-c",
                    _CHUNK_SUBPROCESS_SCRIPT,
                    job_file.name,
                    result_file,
                    str(PROJECT_ROOT),
                    stdout=_aio.subprocess.PIPE,
                    stderr=_aio.subprocess.PIPE,
                    cwd=str(PROJECT_ROOT),
                )

                try:
                    _, stderr = await _aio.wait_for(
                        proc.communicate(), timeout=120
                    )
                except _aio.TimeoutError:
                    proc.kill()
                    logger.error(f"Chunk {chunk_start+1}-{chunk_end} timed out")
                    continue

                if proc.returncode != 0:
                    err_msg = stderr.decode()[:500] if stderr else "unknown"
                    logger.error(f"Chunk subprocess failed: {err_msg}")

                # Read result
                result_path = Path(result_file)
                if result_path.exists():
                    chunk_files.append(result_file)
                else:
                    logger.warning(f"Chunk {chunk_start+1}-{chunk_end}: no result file")
                    # Fallback
                    fallback = [
                        {
                            "title": item.get("title", ""),
                            "layout": item.get("layout", "title_and_content"),
                            "content": item.get("keywords", ""),
                            "notes": "",
                        }
                        for item in chunk_outline
                    ]
                    with open(result_file, "w") as f:
                        json.dump(fallback, f, ensure_ascii=False)
                    chunk_files.append(result_file)

            except Exception as e:
                logger.error(f"Chunk {chunk_start+1}-{chunk_end} error: {e}")
            finally:
                Path(job_file.name).unlink(missing_ok=True)

            gc.collect()

        # --- Step 3: Assemble from files ---
        all_slides = []
        for cf in chunk_files:
            try:
                with open(cf) as f:
                    slides = json.load(f)
                all_slides.extend(slides)
                logger.info(f"Loaded {len(slides)} slides from {Path(cf).name}")
            except Exception as e:
                logger.error(f"Failed to load chunk file {cf}: {e}")
            finally:
                Path(cf).unlink(missing_ok=True)

        result = {
            "title": outline.get("title", "Untitled"),
            "subtitle": outline.get("subtitle", ""),
            "theme": outline.get("theme", "dark_academic"),
            "slides": all_slides,
        }
        del outline, all_slides
        gc.collect()

        logger.info(f"Chunked generation complete: {len(result['slides'])} slides")
        return result

    # ------------------------------------------------------------------
    # RAG
    # ------------------------------------------------------------------

    async def _search_context(
        self, task: AgentTask
    ) -> tuple[str, list[dict]]:
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
    def _format_context(results: list) -> str:
        parts = []
        for i, r in enumerate(results, 1):
            if hasattr(r, "payload") and r.payload is not None:
                payload = r.payload
            elif isinstance(r, dict):
                payload = r.get("payload", r)
            else:
                payload = r

            title = payload.get("title", "Untitled") if isinstance(payload, dict) else getattr(payload, "title", "Untitled")
            text = payload.get("text", "") if isinstance(payload, dict) else getattr(payload, "text", "")
            text = text[:600]
            parts.append(f"[{i}] {title}\n{text}")
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _extract_citations(results: list) -> list[dict]:
        citations = []
        for i, r in enumerate(results, 1):
            if hasattr(r, "payload") and r.payload is not None:
                payload = r.payload
                score = getattr(r, "score", 0.0)
            elif isinstance(r, dict):
                payload = r.get("payload", r)
                score = r.get("score", 0.0)
            else:
                payload = r
                score = 0.0

            if isinstance(payload, dict):
                title = payload.get("title", "Untitled")
                source = payload.get("source", "")
                doc_type = payload.get("document_type", "")
            else:
                title = getattr(payload, "title", "Untitled")
                source = getattr(payload, "source", "")
                doc_type = getattr(payload, "document_type", "")

            citations.append({
                "number": i,
                "title": title,
                "source": source,
                "document_type": doc_type,
                "score": score,
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
                f"## 참고 자료 (이전 에이전트 결과)\n"
                f"아래 내용을 기반으로 발표 자료를 구성하세요.\n\n{parent_text}"
            )

        if rag_context:
            parts.append(f"## 검색된 참고 문헌\n{rag_context}")

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    async def _postprocess_data(
        self, slide_data: Optional[dict], instruction: str,
        generate_pptx: bool, generate_images: bool,
        save_output: bool = False,
    ) -> tuple[str, list[dict]]:
        artifacts: list[dict] = []

        if slide_data and slide_data.get("slides"):
            # Detect theme from data or instruction
            theme_name = slide_data.get("theme") or detect_theme(instruction)

            # Build markdown preview (always)
            content = format_slides_markdown(slide_data, theme_name)
            slide_count = len(slide_data.get("slides", []))

            # Optional: generate images (only if explicitly requested)
            images = None
            if generate_images:
                logger.info("Image generation explicitly requested")
                images = await self._generate_slide_images(slide_data)

            # Optional: build PPTX (only if explicitly requested)
            if generate_pptx:
                logger.info("PPTX generation explicitly requested")
                try:
                    pptx_bytes = build_pptx(slide_data, theme_name, images)
                    title = slide_data.get("title", "presentation")
                    filename = f"{self._slugify(title)}.pptx"

                    # Save to filesystem
                    saved_path = self._save_pptx(filename, pptx_bytes)

                    # Add to artifacts
                    artifacts.append({
                        "type": "pptx",
                        "filename": filename,
                        "data": base64.b64encode(pptx_bytes).decode("utf-8"),
                        "size_bytes": len(pptx_bytes),
                    })

                    img_count = sum(1 for img in (images or []) if img is not None)
                    header = (
                        f"📽️ **PowerPoint 생성 완료**\n\n"
                        f"- 제목: {slide_data.get('title', '')}\n"
                        f"- 슬라이드 수: {slide_count}\n"
                        f"- 테마: `{theme_name}`\n"
                        f"- 파일 크기: {len(pptx_bytes) / 1024:.1f} KB\n"
                    )
                    if img_count > 0:
                        header += f"- 생성된 이미지: {img_count}장\n"
                    if saved_path:
                        header += f"- 📁 저장 위치: `{saved_path}`\n"
                    header += "\n---\n\n### 슬라이드 미리보기\n\n"

                    content = header + content

                except Exception as e:
                    logger.error(f"PPTX generation failed: {e}")
                    content = f"⚠️ PPTX 파일 생성 실패 (미리보기만 제공)\n\n{content}"
            else:
                # No PPTX requested — just markdown preview
                header = (
                    f"📋 **발표자료 구성안** ({slide_count}슬라이드)\n\n"
                    f"*PPT 파일이 필요하면 `ppt 파일로 만들어줘`라고 요청하세요.*\n\n"
                    f"---\n\n"
                )
                content = header + content

            # Save markdown to file if explicitly requested
            if save_output:
                title = slide_data.get("title", "presentation")
                saved_md = self._save_markdown(title, content)
                if saved_md:
                    content = f"📁 **마크다운 저장 완료**: `{saved_md}`\n\n" + content
        else:
            content = "⚠️ 슬라이드 생성에 실패했습니다. 다시 시도해 주세요."
            logger.warning("Slide data is None or empty")

        return content, artifacts

    async def _generate_slide_images(
        self, slide_data: dict
    ) -> Optional[list[Optional[bytes]]]:
        """Generate images for slides using ImageGenerator."""
        try:
            from agents.presentation.image_generator import ImageGenerator
            from orchestrator.config import IMAGE_PROVIDER

            generator = ImageGenerator(provider=IMAGE_PROVIDER)

            # Save images alongside PPTX
            from orchestrator.config import GENERATED_PRESENTATION_DIR
            save_dir = GENERATED_PRESENTATION_DIR / "images"

            images = await generator.generate_for_slides(
                slide_data.get("slides", []),
                output_dir=str(save_dir),
            )
            return images

        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return None

    @staticmethod
    def _save_pptx(filename: str, data: bytes) -> Optional[str]:
        from orchestrator.config import GENERATED_PRESENTATION_DIR
        save_dir = GENERATED_PRESENTATION_DIR
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = save_dir / f"{ts}_{filename}"
            save_path.write_bytes(data)
            logger.info(f"PPTX saved: {save_path}")
            return str(save_path)
        except Exception as e:
            logger.warning(f"Failed to save PPTX: {e}")
            return None

    @staticmethod
    def _slugify(text: str) -> str:
        slug = re.sub(r"[^\w\s가-힣-]", "", text)
        slug = re.sub(r"\s+", "_", slug).strip("_")
        return slug[:50] or "presentation"

    @staticmethod
    def _save_markdown(title: str, content: str) -> Optional[str]:
        """Save markdown content to generated/presentations/ folder."""
        from orchestrator.config import GENERATED_PRESENTATION_DIR
        save_dir = GENERATED_PRESENTATION_DIR
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^\w\s가-힣-]", "", title)
            slug = re.sub(r"\s+", "_", slug).strip("_")[:50] or "presentation"
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ts}_{slug}.md"
            save_path = save_dir / filename
            save_path.write_text(content, encoding="utf-8")
            logger.info(f"Markdown saved: {save_path}")
            return str(save_path)
        except Exception as e:
            logger.warning(f"Failed to save markdown: {e}")
            return None

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def can_handle(self, instruction: str) -> float:
        lower = instruction.lower()
        high = ["ppt", "발표", "슬라이드", "포스터", "presentation", "slide"]
        for kw in high:
            if kw in lower:
                return 0.85
        if "다이어그램" in lower or "diagram" in lower:
            return 0.6
        return 0.0
