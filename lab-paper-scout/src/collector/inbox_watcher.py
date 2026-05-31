"""
lab-paper-scout: Inbox watcher
Monitors the inbox directory for manually added PDFs.
"""
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote

import fitz  # PyMuPDF

from src.processor.document_store import DocumentStore

logger = logging.getLogger(__name__)


class InboxWatcher:
    """Watches the inbox directory for new PDF files."""

    def __init__(self, inbox_path: Path, archive_path: Path, store: DocumentStore):
        self.inbox_path = inbox_path
        self.silent_path = inbox_path / "silent"
        self.archive_path = archive_path
        self.store = store
        # Ensure silent inbox exists
        self.silent_path.mkdir(parents=True, exist_ok=True)

    def check_inbox(self) -> List[Dict]:
        """
        Check for new PDF files in the inbox.
        - inbox/*.pdf → included in reports
        - inbox/silent/*.pdf → processed but excluded from reports
        Returns list of newly registered paper dicts.
        """
        new_papers = []

        # Regular inbox: include in reports
        for pdf_file in sorted(self.inbox_path.glob("*.pdf")):
            paper = self._register_pdf(pdf_file, exclude_report=False)
            if paper:
                new_papers.append(paper)

        # Silent inbox: process but exclude from reports
        for pdf_file in sorted(self.silent_path.glob("*.pdf")):
            paper = self._register_pdf(pdf_file, exclude_report=True)
            if paper:
                new_papers.append(paper)
                logger.info(f"  (silent — 보고서 미포함)")

        if new_papers:
            logger.info(f"Inbox: found {len(new_papers)} new PDF(s).")

        return new_papers

    # Metadata titles that should be ignored (case-insensitive startswith)
    _BAD_TITLE_PREFIXES = (
        "microsoft word",
        "microsoft powerpoint",
        "powerpoint presentation",
        "untitled",
        "slide ",
    )

    # Metadata titles that are journal/series names, not paper titles
    _BAD_TITLE_KEYWORDS = [
        "iop conference series",
        "conference proceedings",
        "elsevier",
        "springer",
        "wiley",
        "arxiv:",
        "doi:",
    ]

    def _extract_title(self, pdf_path: Path) -> str:
        """Extract title from PDF metadata or first-page text, fall back to cleaned filename.

        Strategy order:
            1. PDF metadata 'title' field (with junk filtering)
            2. First-page text (first substantial line)
            3. Cleaned-up filename (last resort)
        """
        try:
            doc = fitz.open(str(pdf_path))
            meta = doc.metadata or {}

            # Strategy 1: PDF metadata title
            title = (meta.get("title") or "").strip()
            if title and len(title) > 5 and self._is_good_metadata_title(title):
                doc.close()
                return title

            # Strategy 2: First page text — take the first substantial line(s)
            if doc.page_count > 0:
                title_from_text = self._extract_title_from_page(doc[0])
                if title_from_text:
                    doc.close()
                    return title_from_text

            doc.close()
        except Exception:
            pass

        # Strategy 3: Clean up filename as last resort
        return self._title_from_filename(pdf_path)

    def _is_good_metadata_title(self, title: str) -> bool:
        """Check if a metadata title looks like a real paper title."""
        lower = title.lower()

        # Known bad prefixes
        if lower.startswith(self._BAD_TITLE_PREFIXES):
            return False

        # Known journal/series names masquerading as titles
        for kw in self._BAD_TITLE_KEYWORDS:
            if kw in lower:
                return False

        # Pure numbers, single word, or looks like a filename
        if title.replace(" ", "").replace("-", "").replace("_", "").isdigit():
            return False
        if "." in title and title.rsplit(".", 1)[-1].lower() in ("pdf", "doc", "docx", "pptx"):
            return False

        return True

    def _extract_title_from_page(self, page) -> str:
        """Extract title from the first page text of a PDF."""
        text = page.get_text("text").strip()
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

        candidate_lines = []
        for line in lines[:15]:  # Check first 15 lines
            # Skip very short lines (page numbers, headers)
            if len(line) < 8:
                continue
            # Skip lines that look like metadata/headers
            lower = line.lower()
            if lower.startswith(("doi:", "http", "www.", "arxiv:", "volume", "journal",
                                 "copyright", "©", "published", "received", "accepted",
                                 "available online", "open access", "research article",
                                 "review article", "original", "contents lists")):
                continue
            # Skip pure numbers
            if line.replace(".", "").replace(",", "").replace(" ", "").isdigit():
                continue
            # Skip author-like lines (multiple commas + short segments = author list)
            if line.count(",") >= 3 and all(len(s.strip()) < 30 for s in line.split(",")):
                continue
            # Skip affiliation-like lines
            if any(kw in lower for kw in ("university", "department", "institute",
                                          "laboratory", "e-mail", "@")):
                continue

            candidate_lines.append(line)
            # Title is usually 1-2 lines; stop when we have enough
            total = " ".join(candidate_lines)
            if len(candidate_lines) >= 2 or len(total) > 80:
                break

        if candidate_lines:
            title_from_text = " ".join(candidate_lines)
            if 10 < len(title_from_text) < 300:
                return title_from_text

        return ""

    @staticmethod
    def _title_from_filename(pdf_path: Path) -> str:
        """Extract a usable title from the filename as a last resort."""
        stem = unquote(pdf_path.stem)  # decode URL-encoded chars

        # Remove common prefixes/suffixes patterns
        for sep in [" - ", " _ "]:
            parts = stem.split(sep)
            if len(parts) >= 4:
                # Pattern like "Journal - Year - Author - Title"
                stem = sep.join(parts[3:]) if len(parts[3:]) > 0 else stem
                break

        # Remove "Microsoft PowerPoint -" prefix
        import re
        stem = re.sub(r'^Microsoft[_ ]PowerPoint[_ ]-[_ ]', '', stem, flags=re.IGNORECASE)
        # Remove trailing "(1)", "(2)" etc
        stem = re.sub(r'\(\d+\)\s*$', '', stem)
        # Remove "DO_NOT_PRINT" etc.
        stem = re.sub(r'DO[_ ]NOT[_ ]PRINT', '', stem, flags=re.IGNORECASE)

        return stem.replace("_", " ").replace("-", " ").strip()

    @staticmethod
    def _sanitize_filename(title: str, max_len: int = 80) -> str:
        """Convert a title to a safe, readable filename."""
        import re
        # Replace unsafe chars with underscores
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title)
        # Collapse whitespace/underscores
        safe = re.sub(r'[\s_]+', '_', safe).strip('_')
        # Truncate
        if len(safe) > max_len:
            safe = safe[:max_len].rsplit('_', 1)[0]
        return safe

    def _register_pdf(self, pdf_path: Path, exclude_report: bool = False) -> Optional[Dict]:
        """Register a PDF from the inbox into the document store.

        Flow:
            1. Extract title from PDF metadata / first page text.
            2. Detect if the file is Supplementary Information (SI).
            3. Rename the file in-place (inbox) to a clean title-based name.
            4. Deduplicate: same title AND same file content → skip.
               Same title but different content → register with suffix.
            5. Move the renamed file to archive.
            6. Register in the document store.
        """
        import hashlib

        title = self._extract_title(pdf_path)
        original_name = pdf_path.name

        # ── Step 1: Detect SI ────────────────────────────────────
        si_label = self._detect_si(pdf_path, original_name)
        if si_label:
            title = f"{title} ({si_label})"

        clean_name = self._sanitize_filename(title) + ".pdf"

        # ── Step 2: Rename in inbox ──────────────────────────────
        if pdf_path.name != clean_name:
            renamed_path = pdf_path.parent / clean_name
            if renamed_path.exists() and renamed_path != pdf_path:
                renamed_path = pdf_path.parent / (
                    self._sanitize_filename(title) + f"_{uuid.uuid4().hex[:6]}.pdf"
                )
            try:
                pdf_path = pdf_path.rename(renamed_path)
                logger.info(f"  Renamed: {original_name} → {pdf_path.name}")
            except OSError as e:
                logger.warning(f"  Rename failed ({e}), using original name.")

        # ── Step 3: Deduplicate by title + content ───────────────
        title_hash = hashlib.md5(title.lower().encode()).hexdigest()[:12]
        paper_id = f"inbox_{title_hash}"
        file_hash = self._file_hash(pdf_path)

        if self.store.paper_exists(paper_id):
            # Same title exists — is the content also the same?
            existing = self.store.get_paper_by_id(paper_id)
            existing_file = Path(existing["pdf_url"]) if existing else None

            if existing_file and existing_file.exists():
                existing_hash = self._file_hash(existing_file)
                if file_hash == existing_hash:
                    # Truly identical file — safe to skip
                    logger.info(f"  Skipped (identical file): {title[:60]}")
                    pdf_path.unlink(missing_ok=True)
                    return None

            # Different content, same title — register with suffix
            if not si_label:
                # SI not detected; use generic suffix
                title = f"{title} (2)"
            # else: SI label already applied, title is already distinct

            # Recalculate paper_id with the updated title
            title_hash = hashlib.md5(title.lower().encode()).hexdigest()[:12]
            paper_id = f"inbox_{title_hash}"
            clean_name = self._sanitize_filename(title) + ".pdf"

            # If even this new paper_id exists, add file hash to guarantee uniqueness
            if self.store.paper_exists(paper_id):
                paper_id = f"inbox_{title_hash}_{file_hash[:6]}"

            logger.info(f"  Same title, different file → registered as: {title[:60]}")

        # ── Step 4: Move to archive ──────────────────────────────
        archive_dest = self.archive_path / clean_name
        if archive_dest.exists():
            archive_name = self._sanitize_filename(title) + f"_{uuid.uuid4().hex[:6]}.pdf"
            archive_dest = self.archive_path / archive_name
        shutil.move(str(pdf_path), str(archive_dest))
        logger.info(f"  Archived: {archive_dest.name}")

        # ── Step 5: Register ─────────────────────────────────────
        paper = {
            "id": paper_id,
            "title": title,
            "authors": [],
            "source": "manual_inbox",
            "url": "",
            "pdf_url": str(archive_dest),
            "year": None,
            "abstract": "",
            "topics": [],
            "exclude_report": exclude_report,
        }

        self.store.add_paper(paper)
        logger.info(f"  Registered inbox PDF: {title}")

        return paper

    # ─── SI Detection ─────────────────────────────────────────

    _SI_FILENAME_PATTERNS = [
        "supporting_information", "supplementary_information",
        "supplementary_material", "supplementary_data",
        "electronic_supplementary", "_si_", "_si.", "_esi_", "_esi.",
        "-si-", "-si.", "-esi-", "-esi.",
    ]

    _SI_TEXT_KEYWORDS = [
        "supporting information",
        "supplementary information",
        "supplementary materials",
        "supplementary data",
        "electronic supplementary information",
        "supplementary figures",
        "supplementary tables",
    ]

    def _detect_si(self, pdf_path: Path, original_name: str) -> str:
        """Detect if a PDF is supplementary information.

        Returns:
            'SI' if detected, '' if not.
        """
        # Strategy 1: Filename patterns (most reliable)
        name_lower = original_name.lower().replace(" ", "_")
        for pattern in self._SI_FILENAME_PATTERNS:
            if pattern in name_lower:
                return "SI"

        # Strategy 2: First 3 pages text
        try:
            doc = fitz.open(str(pdf_path))
            pages_to_check = min(3, doc.page_count)
            text = ""
            for i in range(pages_to_check):
                text += doc[i].get_text("text").lower() + "\n"
            doc.close()

            for keyword in self._SI_TEXT_KEYWORDS:
                if keyword in text:
                    return "SI"
        except Exception:
            pass

        return ""

    # ─── File Hashing ─────────────────────────────────────────

    @staticmethod
    def _file_hash(path: Path, chunk_size: int = 8192) -> str:
        """Compute MD5 hash of a file for content-based deduplication."""
        import hashlib
        h = hashlib.md5()
        try:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    h.update(chunk)
        except OSError:
            return ""
        return h.hexdigest()


