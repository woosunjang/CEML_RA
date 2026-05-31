"""
Presentation Agent — Image Generator

Generates diagram/chart images for slides using Google or OpenAI APIs.
Includes 2-pass prompt enhancement for quality improvement.
"""

import base64
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Negative prompt rules (injected into every image prompt)
# ---------------------------------------------------------------------------
NEGATIVE_RULES = """
Style constraints:
- Clean vector-style flat design, white background
- Font: Noto Sans (English), Noto Sans KR (Korean)
- NO grid lines, NO 3D render, NO depth of field
- NO photorealistic, NO cartoon, NO anime, NO sketch, NO painting style
- NO blurry, NO pixelated, NO low resolution, NO grainy
- NO watermark, NO signature, NO logo, NO username
- NO cluttered, NO busy background, NO excessive detail
- NO neon, NO glowing, NO oversaturated colors
- NO disconnected parts, NO asymmetrical layout
Content constraints:
- NO title headers inside the figure
- NO footer notes inside the figure
- NO long sentences inside the figure
- ONLY short labels on diagram elements
- One concept per diagram
""".strip()


class ImageGenerator:
    """Generates images for presentation slides."""

    def __init__(self, provider: str = "google", model: Optional[str] = None):
        self.provider = provider
        self.model = model
        self._google_client = None
        self._openai_client = None

    def _get_google_client(self):
        if self._google_client is None:
            from google import genai
            from orchestrator.config import GOOGLE_API_KEY
            self._google_client = genai.Client(api_key=GOOGLE_API_KEY)
        return self._google_client

    def _get_openai_client(self):
        if self._openai_client is None:
            import openai
            from orchestrator.config import OPENAI_API_KEY
            self._openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
        return self._openai_client

    async def generate(self, prompt: str, provider: Optional[str] = None) -> Optional[bytes]:
        """Generate an image from a text prompt.

        Tries the primary provider first, then auto-falls back to the other
        if the primary fails (API error, quota, etc.).

        Args:
            prompt: Image description prompt.
            provider: Override provider (google | openai).

        Returns:
            PNG bytes or None on failure.
        """
        primary = provider or self.provider
        fallback = "openai" if primary == "google" else "google"
        enhanced = await self.enhance_prompt(prompt)

        # Try primary provider
        result = await self._try_provider(primary, enhanced)
        if result is not None:
            return result

        # Auto-fallback to the other provider
        logger.warning(f"Primary provider '{primary}' failed, switching to '{fallback}'")
        result = await self._try_provider(fallback, enhanced)
        if result is not None:
            logger.info(f"Fallback to '{fallback}' succeeded")
            return result

        logger.error("Both image providers failed")
        return None

    async def _try_provider(self, provider: str, prompt: str) -> Optional[bytes]:
        """Attempt image generation with a single provider."""
        try:
            if provider == "google":
                return await self._generate_google(prompt)
            elif provider == "openai":
                return await self._generate_openai(prompt)
            else:
                logger.error(f"Unknown image provider: {provider}")
                return None
        except Exception as e:
            logger.error(f"Image generation failed ({provider}): {e}")
            return None

    async def _generate_google(self, prompt: str) -> Optional[bytes]:
        """Generate image using Google Gemini/Imagen API."""
        from orchestrator.config import IMAGE_MODEL_GOOGLE

        client = self._get_google_client()
        model = self.model or IMAGE_MODEL_GOOGLE

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={"response_modalities": ["IMAGE"]},
        )

        # Extract image bytes from response
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    return part.inline_data.data

        logger.warning("No image data in Google response")
        return None

    async def _generate_openai(self, prompt: str) -> Optional[bytes]:
        """Generate image using OpenAI gpt-image API."""
        from orchestrator.config import IMAGE_MODEL_OPENAI

        client = self._get_openai_client()
        model = self.model or IMAGE_MODEL_OPENAI

        response = client.images.generate(
            model=model,
            prompt=prompt,
            n=1,
            size="1536x1024",  # landscape for slides
            response_format="b64_json",
        )

        if response.data:
            b64_data = response.data[0].b64_json
            if b64_data:
                return base64.b64decode(b64_data)

        logger.warning("No image data in OpenAI response")
        return None

    async def enhance_prompt(self, raw_prompt: str) -> str:
        """Enhance an image prompt using LLM (2-pass).

        Takes a raw visual description and makes it more specific
        and suitable for image generation.
        """
        from llm.pool import generate_answer

        system = (
            "You are an image prompt engineer. "
            "Rewrite the following image description into a precise, "
            "detailed prompt for AI image generation. "
            "Focus on technical diagram clarity for academic presentations. "
            "Output ONLY the enhanced prompt, nothing else.\n\n"
            f"Apply these rules:\n{NEGATIVE_RULES}"
        )

        try:
            enhanced = await generate_answer(
                system_prompt=system,
                user_prompt=f"Original prompt: {raw_prompt}",
                temperature=0.2,
            )
            return enhanced.strip()
        except Exception as e:
            logger.warning(f"Prompt enhancement failed, using original: {e}")
            return f"{raw_prompt}\n\n{NEGATIVE_RULES}"

    async def generate_for_slides(
        self, slides: list[dict], output_dir: Optional[str] = None,
        max_images: int = 5,
    ) -> list[Optional[bytes]]:
        """Generate images for slides that have a 'visual' field.

        To prevent OOM on long presentations, at most `max_images` images
        are generated.  Slides are prioritised by position (early slides
        first).

        Args:
            slides: List of slide dicts with optional 'visual' field.
            output_dir: Optional directory to save generated images.
            max_images: Maximum number of images to generate (default 5).

        Returns:
            List of PNG bytes (or None for slides without visuals).
        """
        import gc

        images: list[Optional[bytes]] = []
        save_dir = None
        generated_count = 0

        if output_dir:
            save_dir = Path(output_dir)
            save_dir.mkdir(parents=True, exist_ok=True)

        for i, slide in enumerate(slides):
            visual = slide.get("visual", "")
            if not visual or visual.strip() == "":
                images.append(None)
                continue

            if generated_count >= max_images:
                logger.info(
                    f"Skipping image for slide {i+1} (limit {max_images} reached)"
                )
                images.append(None)
                continue

            logger.info(f"Generating image for slide {i+1}: {visual[:60]}...")
            img_bytes = await self.generate(visual)
            images.append(img_bytes)
            generated_count += 1

            # Save to disk if requested
            if img_bytes and save_dir:
                img_path = save_dir / f"slide_{i+1}.png"
                img_path.write_bytes(img_bytes)
                logger.info(f"Saved: {img_path}")

            # Release memory after each image to avoid OOM
            gc.collect()

        logger.info(f"Image generation complete: {generated_count}/{len(slides)} slides")
        return images

