"""
Lab Research Agents — Scout DB Reader

Read-only access to lab-paper-scout's SQLite database,
providing recent papers, stats, and search functionality
for the Streamlit UI.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from app.config import SCOUT_DB_PATH

logger = logging.getLogger(__name__)


class ScoutReader:
    """Read-only interface to the lab-paper-scout database."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or SCOUT_DB_PATH
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def available(self) -> bool:
        """Check if the scout DB file exists."""
        return self.db_path.exists()

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create a read-only connection."""
        if self._conn is None:
            if not self.available:
                raise FileNotFoundError(f"Scout DB not found: {self.db_path}")
            # Read-only mode via URI
            uri = f"file:{self.db_path}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True, timeout=5)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def get_recent_papers(self, days: int = 7, limit: int = 50) -> list[dict]:
        """Get recently collected papers."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT id, title, authors, source, url, year,
                      relevance_score, status, collected_at, analyzed_at
               FROM papers
               WHERE collected_at >= ?
               ORDER BY relevance_score DESC, collected_at DESC
               LIMIT ?""",
            (cutoff, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_top_papers(self, min_score: int = 70, limit: int = 20) -> list[dict]:
        """Get highest relevance papers."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT id, title, authors, source, url, year,
                      relevance_score, status, analysis_json
               FROM papers
               WHERE relevance_score >= ? AND status = 'analyzed'
               ORDER BY relevance_score DESC
               LIMIT ?""",
            (min_score, limit),
        ).fetchall()

        results = []
        for r in rows:
            paper = dict(r)
            # Parse analysis summary if available
            if paper.get("analysis_json"):
                try:
                    analysis = json.loads(paper["analysis_json"])
                    paper["summary"] = analysis.get("one_line_summary", "")
                    paper["tags"] = analysis.get("tags", [])
                except (json.JSONDecodeError, TypeError):
                    paper["summary"] = ""
                    paper["tags"] = []
            else:
                paper["summary"] = ""
                paper["tags"] = []
            results.append(paper)
        return results

    def get_stats(self) -> dict:
        """Get basic stats from the scout DB."""
        conn = self._get_conn()
        stats = {}
        stats["total"] = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        stats["analyzed"] = conn.execute(
            "SELECT COUNT(*) FROM papers WHERE status='analyzed'"
        ).fetchone()[0]

        today = datetime.now().strftime("%Y-%m-%d")
        stats["today"] = conn.execute(
            "SELECT COUNT(*) FROM papers WHERE collected_at >= ?", (today,)
        ).fetchone()[0]

        stats["avg_score"] = conn.execute(
            "SELECT AVG(relevance_score) FROM papers WHERE status='analyzed'"
        ).fetchone()[0] or 0

        return stats

    def search_papers(self, query: str, limit: int = 20) -> list[dict]:
        """Simple text search across titles and abstracts."""
        conn = self._get_conn()
        like_query = f"%{query}%"
        rows = conn.execute(
            """SELECT id, title, authors, source, url, year,
                      relevance_score, status, analysis_json
               FROM papers
               WHERE title LIKE ? OR abstract LIKE ?
               ORDER BY relevance_score DESC
               LIMIT ?""",
            (like_query, like_query, limit),
        ).fetchall()

        results = []
        for r in rows:
            paper = dict(r)
            if paper.get("analysis_json"):
                try:
                    analysis = json.loads(paper["analysis_json"])
                    paper["summary"] = analysis.get("one_line_summary", "")
                except (json.JSONDecodeError, TypeError):
                    paper["summary"] = ""
            else:
                paper["summary"] = ""
            results.append(paper)
        return results

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
