"""
lab-paper-scout: PDF text and metadata extractor
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Extracts text, metadata, and figure captions from PDFs."""

    def extract(self, pdf_path: str, output_dir: Path, paper_id: str) -> Optional[Dict]:
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            logger.error(f"Failed to open PDF {pdf_path}: {e}")
            return None

        meta = doc.metadata or {}
        title = meta.get("title", "").strip()
        author = meta.get("author", "").strip()

        full_text = ""
        page_texts = []
        for page in doc:
            text = page.get_text("text")
            page_texts.append(text)
            full_text += text + "\n\n"

        if not title and page_texts:
            first_lines = page_texts[0].strip().split("\n")
            if first_lines:
                title = first_lines[0].strip()[:200]

        figure_captions = self._extract_figure_captions(full_text)
        sections = self._split_sections(full_text)

        doc.close()

        result = {
            "id": paper_id,
            "title": title,
            "authors_from_pdf": author,
            "total_pages": len(page_texts),
            "full_text_length": len(full_text),
            "sections": sections,
            "figure_captions": figure_captions,
            "abstract": self._extract_abstract(full_text),
        }

        output_path = output_dir / f"{paper_id}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(
            f"  Extracted: {title[:60]}... "
            f"({len(page_texts)} pages, {len(sections)} sections)"
        )
        return result

    def _extract_abstract(self, text: str) -> str:
        patterns = [
            r"(?i)abstract\s*\n+(.*?)(?=\n\s*(?:introduction|keywords|1\.|1\s))",
            r"(?i)abstract[:\s]+(.*?)(?=\n\n)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                abstract = match.group(1).strip()
                if 50 < len(abstract) < 3000:
                    return abstract
        return ""

    def _split_sections(self, text: str) -> List[Dict]:
        pattern = r"\n\s*(\d+\.?\s+[A-Z][^\n]{3,80})\s*\n"
        matches = list(re.finditer(pattern, text))

        if len(matches) < 2:
            return [{"name": "Full Text", "text": text[:10000]}]

        sections = []
        for i, match in enumerate(matches):
            name = match.group(1).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_text = text[start:end].strip()

            if len(section_text) > 5000:
                section_text = section_text[:5000] + "... [truncated]"

            sections.append({"name": name, "text": section_text})

        return sections

    def _extract_figure_captions(self, text: str) -> List[str]:
        pattern = r"(?i)((?:fig(?:ure)?|table)\s*\.?\s*\d+[.:]\s*[^\n]+)"
        matches = re.findall(pattern, text)
        return [m.strip() for m in matches[:20]]
