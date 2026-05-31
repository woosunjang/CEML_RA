"""
Lab Research Agents — Text Chunker v0.2

Section-aware chunking: detects academic paper structure
(Abstract, Introduction, Methods, Results, etc.) and splits
at section boundaries first, then applies size-based splitting
within each section.

Fallback: if no sections are detected, uses character-based
sliding window (same as v0.1).
"""

import re
import uuid
from typing import Optional

from app.schemas import ChunkMetadata, DocumentType


# ---------------------------------------------------------------------------
# Section detection patterns
# ---------------------------------------------------------------------------

# Common section headings in academic papers (case-insensitive)
_SECTION_PATTERNS = [
    # Numbered sections: "1. Introduction", "2.1 Methods", "III. Results"
    r"^(?:\d+\.?\d*\.?\s+|[IVX]+\.\s+)",
    # Markdown-style: "## Introduction", "### Methods"
    r"^#{1,4}\s+",
]

# Known section keywords (used to label detected sections)
_SECTION_KEYWORDS = {
    "abstract": "Abstract",
    "introduction": "Introduction",
    "background": "Background",
    "related work": "Related Work",
    "literature review": "Literature Review",
    "method": "Methods",
    "methodology": "Methods",
    "experimental": "Experimental",
    "materials and methods": "Methods",
    "computational": "Computational Methods",
    "result": "Results",
    "results and discussion": "Results & Discussion",
    "discussion": "Discussion",
    "conclusion": "Conclusion",
    "summary": "Summary",
    "acknowledgment": "Acknowledgments",
    "acknowledgement": "Acknowledgments",
    "reference": "References",
    "bibliography": "References",
    "appendix": "Appendix",
    "supplementary": "Supplementary",
    "supporting information": "Supporting Information",
}


# ---------------------------------------------------------------------------
# Section-aware splitting
# ---------------------------------------------------------------------------

def _detect_section_label(line: str) -> Optional[str]:
    """Try to map a heading line to a known section label."""
    # Strip numbering and markdown markers
    cleaned = re.sub(r"^(?:\d+\.?\d*\.?\s*|[IVX]+\.\s*|#{1,4}\s*)", "", line).strip()
    cleaned_lower = cleaned.lower().rstrip("s").rstrip(".")  # normalize plurals/dots

    for keyword, label in _SECTION_KEYWORDS.items():
        if keyword in cleaned_lower:
            return label

    # If not a known keyword but looks like a heading, use it as-is
    if len(cleaned) > 2 and len(cleaned) < 80:
        return cleaned

    return None


# Single-word headings that should be recognized without numbering
_STANDALONE_HEADINGS = {
    "abstract", "introduction", "background", "methods", "methodology",
    "method",  # singular
    "experimental", "results", "result",  # singular
    "discussion", "conclusion", "conclusions",
    "summary", "acknowledgments", "acknowledgements", "acknowledgment",
    "references", "reference",  # both forms
    "bibliography", "appendix", "supplementary",
}


def _is_section_heading(line: str) -> bool:
    """Check if a line looks like a section heading."""
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return False

    # Check structural patterns (numbered, markdown headers)
    for pattern in _SECTION_PATTERNS:
        if re.match(pattern, stripped):
            return True

    # Check standalone known heading words (e.g., "Abstract", "CONCLUSION")
    if stripped.lower() in _STANDALONE_HEADINGS:
        return True

    # Check if it's an ALL-CAPS line (common in papers)
    words = stripped.split()
    if (2 <= len(words) <= 8
        and stripped.upper() == stripped
        and not stripped.replace(" ", "").isdigit()):
        return True

    return False


def _split_into_sections(full_text: str) -> list[dict]:
    """Split text into sections based on detected headings.

    Returns:
        List of {"section": str|None, "text": str} dicts.
    """
    lines = full_text.split("\n")
    sections = []
    current_section = None
    current_lines = []

    for line in lines:
        if _is_section_heading(line):
            # Save previous section
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    sections.append({
                        "section": current_section,
                        "text": text,
                    })
            # Start new section
            current_section = _detect_section_label(line)
            current_lines = [line]
        else:
            current_lines.append(line)

    # Don't forget the last section
    if current_lines:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append({
                "section": current_section,
                "text": text,
            })

    return sections


# ---------------------------------------------------------------------------
# Core chunking functions
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[str]:
    """
    Split text into overlapping chunks by character count.
    Tries to break at sentence boundaries when possible.

    Args:
        text: The full text to chunk.
        chunk_size: Maximum characters per chunk.
        overlap: Number of overlapping characters between consecutive chunks.

    Returns:
        List of text chunks.
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # If text fits in one chunk, return as-is
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        # Try to break at a sentence boundary (. ! ? followed by space/newline)
        if end < text_len:
            # Look backwards from 'end' for a sentence boundary
            search_start = max(start + chunk_size // 2, start)  # don't break too early
            best_break = end
            for i in range(end, search_start, -1):
                if text[i - 1] in ".!?\n" and (i >= text_len or text[i] in " \n\t"):
                    best_break = i
                    break
            end = best_break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Advance with overlap
        if end >= text_len:
            break
        start = max(start + 1, end - overlap)

    return chunks


def chunk_text_section_aware(
    full_text: str,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[dict]:
    """Split text into chunks with section awareness.

    First splits into sections by detecting headings, then applies
    size-based chunking within each section. Each chunk carries
    its section label.

    Args:
        full_text: The complete document text.
        chunk_size: Maximum characters per chunk.
        overlap: Overlap characters between chunks.

    Returns:
        List of {"section": str|None, "text": str} dicts.
    """
    sections = _split_into_sections(full_text)

    # If no sections detected (e.g., plain text), fall back to simple chunking
    if len(sections) <= 1:
        return [{"section": None, "text": c} for c in chunk_text(full_text, chunk_size, overlap)]

    result = []
    for sec in sections:
        section_label = sec["section"]
        section_text = sec["text"]

        # Skip References section (usually not useful for retrieval)
        if section_label in ("References", "Bibliography"):
            continue

        chunks = chunk_text(section_text, chunk_size, overlap)
        for c in chunks:
            result.append({"section": section_label, "text": c})

    return result if result else [{"section": None, "text": c} for c in chunk_text(full_text, chunk_size, overlap)]


# ---------------------------------------------------------------------------
# Build ChunkMetadata objects
# ---------------------------------------------------------------------------

def build_chunks(
    pages: list[dict],
    document_id: str,
    title: str,
    source_file: str,
    document_type: str,
    project: str = "general",
    year: Optional[int] = None,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[ChunkMetadata]:
    """
    Build ChunkMetadata objects from parsed pages.

    Uses section-aware chunking: joins all pages into a single text,
    detects section boundaries, then chunks within each section.
    Page numbers are estimated from character positions.

    Args:
        pages: Output from a parser — list of {"page": int|None, "text": str}.
        document_id: UUID of the parent document.
        title: Document title.
        source_file: Original filename.
        document_type: One of DocumentType values.
        project: Project tag.
        year: Optional publication year.
        chunk_size: Characters per chunk.
        overlap: Overlap characters.

    Returns:
        List of ChunkMetadata ready for embedding and storage.
    """
    # Build full text and page boundary map
    full_text_parts = []
    page_boundaries = []  # (char_start, char_end, page_num)
    offset = 0

    for page_info in pages:
        page_num = page_info.get("page")
        text = page_info.get("text", "")
        if text:
            start = offset
            full_text_parts.append(text)
            offset += len(text) + 1  # +1 for the joining newline
            page_boundaries.append((start, offset - 1, page_num))

    full_text = "\n".join(full_text_parts)

    if not full_text.strip():
        return []

    # Section-aware chunking on full text
    section_chunks = chunk_text_section_aware(full_text, chunk_size, overlap)

    # Build metadata for each chunk
    all_chunks: list[ChunkMetadata] = []
    search_offset = 0

    for chunk_index, sc in enumerate(section_chunks):
        chunk_text_str = sc["text"]
        section_label = sc["section"]

        # Estimate page number from chunk position in full text
        chunk_pos = full_text.find(chunk_text_str[:50], search_offset)
        if chunk_pos >= 0:
            search_offset = chunk_pos
        page_num = _estimate_page(chunk_pos if chunk_pos >= 0 else 0, page_boundaries)

        chunk = ChunkMetadata(
            chunk_id=str(uuid.uuid4()),
            document_id=document_id,
            title=title,
            source_file=source_file,
            document_type=DocumentType(document_type),
            project=project,
            year=year,
            page=page_num,
            section=section_label,
            chunk_index=chunk_index,
            text=chunk_text_str,
        )
        all_chunks.append(chunk)

    return all_chunks


def _estimate_page(char_pos: int, page_boundaries: list[tuple]) -> Optional[int]:
    """Estimate which page a character position belongs to."""
    for start, end, page_num in page_boundaries:
        if start <= char_pos <= end:
            return page_num
    # If no match, return the last page
    if page_boundaries:
        return page_boundaries[-1][2]
    return None
