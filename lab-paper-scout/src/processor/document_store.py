"""
lab-paper-scout: Document store backed by SQLite
Tracks all collected papers, their processing status, and metadata.

Resilience features:
  - WAL mode for concurrent read/write access
  - 30-second lock timeout (default is 5s)
  - Automatic retry on transient lock errors (up to 3 attempts)
"""
import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Retry settings for transient DB locks
_MAX_RETRIES = 3
_RETRY_DELAY = 2  # seconds


class DocumentStore:
    """SQLite-backed store for paper metadata and processing state."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            timeout=30,  # wait up to 30s for lock release (default 5s)
        )
        self._conn.row_factory = sqlite3.Row
        # WAL mode: allows concurrent readers while writing
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_db()

    def _commit_with_retry(self):
        """Commit with automatic retry on transient lock errors."""
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._conn.commit()
                return
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "readonly" in str(e).lower():
                    if attempt < _MAX_RETRIES:
                        logger.warning(
                            f"DB commit failed (attempt {attempt}/{_MAX_RETRIES}): {e}. "
                            f"Retrying in {_RETRY_DELAY}s..."
                        )
                        time.sleep(_RETRY_DELAY * attempt)  # progressive backoff
                    else:
                        logger.error(f"DB commit failed after {_MAX_RETRIES} attempts: {e}")
                        raise
                else:
                    raise  # non-lock error — reraise immediately

    def _init_db(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS papers (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                authors TEXT,
                source TEXT,
                url TEXT,
                pdf_url TEXT,
                year INTEGER,
                abstract TEXT,
                topics_json TEXT DEFAULT '[]',
                relevance_score REAL DEFAULT 0.0,
                status TEXT DEFAULT 'collected',
                summary TEXT,
                analysis_json TEXT,
                collected_at TEXT,
                processed_at TEXT,
                analyzed_at TEXT,
                exclude_report INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_status ON papers(status);
            CREATE INDEX IF NOT EXISTS idx_collected ON papers(collected_at);
        """)
        # Migrate: add columns if missing (for existing DBs)
        for col, default in [("exclude_report", "0"), ("fail_count", "0"), ("chased", "0")]:
            try:
                self._conn.execute(f"ALTER TABLE papers ADD COLUMN {col} INTEGER DEFAULT {default}")
            except Exception:
                pass  # column already exists
        # Text columns
        for col in ["venue"]:
            try:
                self._conn.execute(f"ALTER TABLE papers ADD COLUMN {col} TEXT DEFAULT ''")
            except Exception:
                pass
        self._conn.commit()

    def paper_exists(self, paper_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM papers WHERE id = ?", (paper_id,)
        ).fetchone()
        return row is not None

    def get_paper_by_id(self, paper_id: str) -> dict | None:
        """Return a paper by its ID, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM papers WHERE id = ?", (paper_id,)
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _is_mdpi(paper: dict) -> bool:
        """Return True if paper is from MDPI publisher."""
        url = (paper.get("url") or "").lower()
        venue = (paper.get("venue") or "").lower()
        return "10.3390/" in url or "mdpi.com" in url or "mdpi" in venue

    def add_paper(self, paper: dict) -> bool:
        """Add a paper if it doesn't already exist. Returns True if added.
        Papers from MDPI (DOI prefix 10.3390/) are silently rejected."""
        if self.paper_exists(paper["id"]):
            return False

        # Reject MDPI at ingestion — never store in DB
        if self._is_mdpi(paper):
            logger.debug(f"  Skipped MDPI paper: {paper.get('title', '')[:60]}")
            return False

        self._conn.execute(
            """INSERT INTO papers
               (id, title, authors, source, url, pdf_url, year, abstract,
                topics_json, status, collected_at, exclude_report, venue)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'collected', ?, ?, ?)""",
            (
                paper["id"],
                paper["title"],
                json.dumps(paper.get("authors", []), ensure_ascii=False),
                paper.get("source", "unknown"),
                paper.get("url", ""),
                paper.get("pdf_url", ""),
                paper.get("year"),
                paper.get("abstract", ""),
                json.dumps(paper.get("topics", []), ensure_ascii=False),
                datetime.now().isoformat(),
                1 if paper.get("exclude_report") else 0,
                paper.get("venue", ""),
            ),
        )
        self._commit_with_retry()
        return True

    def mark_processed(self, paper_id: str, extracted_json_path: str):
        self._conn.execute(
            """UPDATE papers
               SET status = 'processed', processed_at = ?
               WHERE id = ?""",
            (datetime.now().isoformat(), paper_id),
        )
        self._commit_with_retry()

    def mark_analyzed(self, paper_id: str, summary: str, analysis: dict):
        self._conn.execute(
            """UPDATE papers
               SET status = 'analyzed', analyzed_at = ?,
                   summary = ?, analysis_json = ?, relevance_score = ?
               WHERE id = ?""",
            (
                datetime.now().isoformat(),
                summary,
                json.dumps(analysis, ensure_ascii=False),
                analysis.get("relevance_score", 0),
                paper_id,
            ),
        )
        self._commit_with_retry()

    def get_papers_by_status(self, status: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM papers WHERE status = ? ORDER BY collected_at DESC",
            (status,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_papers_since(self, since: str) -> list[dict]:
        """Get all papers collected since a given ISO datetime string."""
        rows = self._conn.execute(
            "SELECT * FROM papers WHERE collected_at >= ? ORDER BY relevance_score DESC",
            (since,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_analyzed_papers_since(self, since: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT * FROM papers
               WHERE status = 'analyzed' AND collected_at >= ?
               ORDER BY relevance_score DESC""",
            (since,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_reportable_papers_since(self, since: str, by_analyzed: bool = False) -> list[dict]:
        """Get analyzed papers eligible for reports (exclude_report=0).
        If by_analyzed=True, filter by analyzed_at instead of collected_at."""
        time_col = "analyzed_at" if by_analyzed else "collected_at"
        rows = self._conn.execute(
            f"""SELECT * FROM papers
               WHERE status = 'analyzed' AND {time_col} >= ?
                     AND (exclude_report IS NULL OR exclude_report = 0)
               ORDER BY relevance_score DESC""",
            (since,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_survey_papers_since(self, since: str, min_score: int = 50) -> list[dict]:
        """Get analyzed backfill/citation papers with relevance >= min_score."""
        rows = self._conn.execute(
            """SELECT * FROM papers
               WHERE status = 'analyzed' AND collected_at >= ?
                     AND exclude_report = 1
                     AND source IN ('backfill', 'citation_chase')
                     AND relevance_score >= ?
               ORDER BY relevance_score DESC""",
            (since, min_score),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_failed(self, paper_id: str, error_msg: str):
        """Mark a paper as failed, increment fail counter."""
        self._conn.execute(
            """UPDATE papers
               SET status = 'failed',
                   fail_count = COALESCE(fail_count, 0) + 1,
                   analysis_json = ?
               WHERE id = ?""",
            (json.dumps({"error": error_msg}, ensure_ascii=False), paper_id),
        )
        self._commit_with_retry()

    def get_retryable_papers(self, max_retries: int = 3) -> list[dict]:
        """Get failed papers that haven't exceeded max retries."""
        rows = self._conn.execute(
            """SELECT * FROM papers
               WHERE status = 'failed'
                     AND COALESCE(fail_count, 0) < ?
               ORDER BY collected_at DESC""",
            (max_retries,),
        ).fetchall()
        return [dict(row) for row in rows]

    def reset_for_retry(self, paper_id: str):
        """Reset a failed paper to 'processed' for retry."""
        self._conn.execute(
            "UPDATE papers SET status = 'processed' WHERE id = ?",
            (paper_id,),
        )
        self._commit_with_retry()

    def close(self):
        self._conn.close()

    def get_chaseable_papers(self, min_score: int = 70) -> list[dict]:
        """Get analyzed papers eligible for citation chasing."""
        rows = self._conn.execute(
            """SELECT * FROM papers
               WHERE status = 'analyzed'
                     AND relevance_score >= ?
                     AND COALESCE(chased, 0) = 0
               ORDER BY relevance_score DESC""",
            (min_score,),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_chased(self, paper_id: str):
        """Mark a paper's citations as chased."""
        self._conn.execute(
            "UPDATE papers SET chased = 1 WHERE id = ?",
            (paper_id,),
        )
        self._commit_with_retry()

    def get_inbox_papers(self) -> list[dict]:
        """Return all manually ingested inbox papers, ordered by collected_at desc."""
        rows = self._conn.execute(
            """SELECT id, title, status, relevance_score, collected_at, analyzed_at
               FROM papers
               WHERE source = 'manual_inbox'
               ORDER BY collected_at DESC""",
        ).fetchall()
        return [dict(row) for row in rows]

    def fix_paper_title(self, paper_id: str, new_title: str) -> str:
        """Update a paper's title and recalculate its paper_id.

        Returns the new paper_id, or raises ValueError if paper_id not found
        or if a paper with the target title already exists.
        """
        import hashlib

        # Verify paper exists
        row = self._conn.execute(
            "SELECT * FROM papers WHERE id = ?", (paper_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Paper not found: {paper_id}")

        # Compute new ID (same scheme as inbox_watcher)
        title_hash = hashlib.md5(new_title.lower().encode()).hexdigest()[:12]
        new_id = f"inbox_{title_hash}"

        # If new_id already exists (different paper), refuse to overwrite
        if new_id != paper_id:
            existing = self._conn.execute(
                "SELECT id FROM papers WHERE id = ?", (new_id,)
            ).fetchone()
            if existing:
                raise ValueError(
                    f"A paper with the target title already exists in DB (id={new_id}). "
                    "Delete the duplicate first."
                )

        self._conn.execute(
            "UPDATE papers SET id = ?, title = ? WHERE id = ?",
            (new_id, new_title, paper_id),
        )
        self._commit_with_retry()
        return new_id

    def get_stats(self) -> dict:
        """Return comprehensive DB statistics for the status dashboard."""
        stats = {}

        # Total papers
        stats["total"] = self._conn.execute(
            "SELECT COUNT(*) FROM papers"
        ).fetchone()[0]

        # By status
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM papers GROUP BY status ORDER BY cnt DESC"
        ).fetchall()
        stats["by_status"] = {r["status"]: r["cnt"] for r in rows}

        # By source
        rows = self._conn.execute(
            "SELECT source, COUNT(*) as cnt FROM papers GROUP BY source ORDER BY cnt DESC"
        ).fetchall()
        stats["by_source"] = {r["source"]: r["cnt"] for r in rows}

        # Relevance score distribution
        for label, lo, hi in [("90+", 90, 999), ("70-89", 70, 89), ("50-69", 50, 69), ("<50", 0, 49)]:
            cnt = self._conn.execute(
                "SELECT COUNT(*) FROM papers WHERE relevance_score BETWEEN ? AND ?",
                (lo, hi)
            ).fetchone()[0]
            stats.setdefault("score_dist", {})[label] = cnt

        # Latest collection and analysis
        stats["latest_collected"] = self._conn.execute(
            "SELECT MAX(collected_at) FROM papers"
        ).fetchone()[0]
        stats["latest_analyzed"] = self._conn.execute(
            "SELECT MAX(analyzed_at) FROM papers WHERE status='analyzed'"
        ).fetchone()[0]

        # Failed papers count
        stats["failed"] = self._conn.execute(
            "SELECT COUNT(*) FROM papers WHERE status='failed'"
        ).fetchone()[0]

        # Papers collected today
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        stats["today_collected"] = self._conn.execute(
            "SELECT COUNT(*) FROM papers WHERE collected_at >= ?", (today,)
        ).fetchone()[0]
        stats["today_analyzed"] = self._conn.execute(
            "SELECT COUNT(*) FROM papers WHERE analyzed_at >= ?", (today,)
        ).fetchone()[0]

        # DB file size
        if self.db_path.exists():
            stats["db_size_mb"] = self.db_path.stat().st_size / (1024 * 1024)

        return stats

    def close(self):
        self._conn.close()
