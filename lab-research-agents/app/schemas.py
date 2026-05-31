"""
Lab Research Agents — Data Schemas

Pydantic v2 models for documents, chunks, and enums.
"""

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DocumentType(StrEnum):
    """Allowed document types for metadata tagging."""
    PAPER = "paper"
    REVIEW = "review"
    PROPOSAL = "proposal"
    MANUSCRIPT = "manuscript"
    RESPONSE_LETTER = "response_letter"
    LECTURE_SLIDE = "lecture_slide"
    LECTURE_NOTE = "lecture_note"
    MEMO = "memo"
    OTHER = "other"


class AgentMode(StrEnum):
    """Available agent modes."""
    LITERATURE = "literature"
    PROPOSAL = "proposal"
    MANUSCRIPT = "manuscript"
    LECTURE = "lecture"
    SCOUT = "scout"


# ---------------------------------------------------------------------------
# Document Metadata
# ---------------------------------------------------------------------------

class DocumentMetadata(BaseModel):
    """Metadata for an ingested document."""
    document_id: str
    title: str
    source_file: str
    document_type: DocumentType
    project: str = "general"
    year: Optional[int] = None


# ---------------------------------------------------------------------------
# Chunk Metadata
# ---------------------------------------------------------------------------

class ChunkMetadata(BaseModel):
    """Metadata for a single text chunk stored in the vector DB."""
    chunk_id: str
    document_id: str
    title: str
    source_file: str
    document_type: DocumentType
    project: str = "general"
    year: Optional[int] = None
    page: Optional[int] = None
    section: Optional[str] = None
    chunk_index: int = 0
    text: str = ""
