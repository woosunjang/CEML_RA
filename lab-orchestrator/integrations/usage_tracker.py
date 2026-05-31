"""
Lab Orchestrator — Usage Tracker

SQLite 기반 에이전트 호출·대화·파이프라인 실행 기록.
리포트 생성의 데이터 소스.

Usage:
    from integrations.usage_tracker import tracker
    await tracker.log_agent_call("literature", "completed", 12.5)
    stats = await tracker.get_daily_stats()
"""

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("usage_tracker")

from orchestrator.config import USAGE_DB
_DB_PATH = USAGE_DB


class UsageTracker:
    """SQLite-based usage statistics tracker."""

    def __init__(self, db_path: Path = _DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS agent_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                agent_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'completed',
                elapsed_sec REAL DEFAULT 0,
                instruction TEXT DEFAULT '',
                error TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                conversation_id TEXT NOT NULL,
                message TEXT DEFAULT '',
                agent_name TEXT DEFAULT '',
                mode TEXT DEFAULT 'normal'
            );

            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                pipeline_id TEXT NOT NULL,
                run_id TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'completed',
                steps INTEGER DEFAULT 0,
                elapsed_sec REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_calls_ts ON agent_calls(timestamp);
            CREATE INDEX IF NOT EXISTS idx_conv_ts ON conversations(timestamp);
            CREATE INDEX IF NOT EXISTS idx_pipe_ts ON pipeline_runs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_llm_ts ON llm_usage(timestamp);
        """)
        conn.close()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Logging ──

    async def log_agent_call(
        self,
        agent_name: str,
        status: str = "completed",
        elapsed_sec: float = 0,
        instruction: str = "",
        error: str = "",
    ):
        """Record an agent invocation."""
        def _insert():
            conn = self._conn()
            conn.execute(
                "INSERT INTO agent_calls (agent_name, status, elapsed_sec, instruction, error) "
                "VALUES (?, ?, ?, ?, ?)",
                (agent_name, status, elapsed_sec, instruction[:500], error[:500]),
            )
            conn.commit()
            conn.close()

        await asyncio.get_event_loop().run_in_executor(None, _insert)

    async def log_conversation(
        self,
        conversation_id: str,
        message: str,
        agent_name: str = "",
        mode: str = "normal",
    ):
        """Record a conversation turn."""
        def _insert():
            conn = self._conn()
            conn.execute(
                "INSERT INTO conversations (conversation_id, message, agent_name, mode) "
                "VALUES (?, ?, ?, ?)",
                (conversation_id, message[:500], agent_name, mode),
            )
            conn.commit()
            conn.close()

        await asyncio.get_event_loop().run_in_executor(None, _insert)

    async def log_pipeline_run(
        self,
        pipeline_id: str,
        run_id: str = "",
        status: str = "completed",
        steps: int = 0,
        elapsed_sec: float = 0,
    ):
        """Record a pipeline execution."""
        def _insert():
            conn = self._conn()
            conn.execute(
                "INSERT INTO pipeline_runs (pipeline_id, run_id, status, steps, elapsed_sec) "
                "VALUES (?, ?, ?, ?, ?)",
                (pipeline_id, run_id, status, steps, elapsed_sec),
            )
            conn.commit()
            conn.close()

        await asyncio.get_event_loop().run_in_executor(None, _insert)

    async def log_llm_usage(
        self,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0,
    ):
        """Record LLM token usage and cost."""
        total = prompt_tokens + completion_tokens

        def _insert():
            conn = self._conn()
            conn.execute(
                "INSERT INTO llm_usage (provider, model, prompt_tokens, completion_tokens, total_tokens, cost_usd) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (provider, model, prompt_tokens, completion_tokens, total, cost_usd),
            )
            conn.commit()
            conn.close()

        await asyncio.get_event_loop().run_in_executor(None, _insert)

    async def get_weekly_llm_cost(self, end_date: Optional[str] = None) -> dict:
        """Get LLM usage summary for the past 7 days."""
        if not end_date:
            end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d")

        def _query():
            conn = self._conn()
            # Per-model summary
            rows = conn.execute(
                "SELECT provider, model, "
                "SUM(prompt_tokens) as total_prompt, "
                "SUM(completion_tokens) as total_completion, "
                "SUM(total_tokens) as total_tokens, "
                "SUM(cost_usd) as total_cost, "
                "COUNT(*) as call_count "
                "FROM llm_usage "
                "WHERE DATE(timestamp) BETWEEN ? AND ? "
                "GROUP BY provider, model ORDER BY total_cost DESC",
                (start_date, end_date),
            ).fetchall()

            # Daily trend
            daily = conn.execute(
                "SELECT DATE(timestamp) as day, "
                "SUM(total_tokens) as tokens, "
                "SUM(cost_usd) as cost "
                "FROM llm_usage "
                "WHERE DATE(timestamp) BETWEEN ? AND ? "
                "GROUP BY DATE(timestamp) ORDER BY day",
                (start_date, end_date),
            ).fetchall()

            conn.close()
            return {
                "period": f"{start_date} ~ {end_date}",
                "models": [dict(r) for r in rows],
                "daily_trend": [dict(d) for d in daily],
                "total_cost": sum(r["total_cost"] for r in rows),
                "total_tokens": sum(r["total_tokens"] for r in rows),
            }

        return await asyncio.get_event_loop().run_in_executor(None, _query)

    # ── Queries ──

    async def get_daily_stats(self, date: Optional[str] = None) -> dict:
        """Get stats for a specific date (default: yesterday)."""
        if not date:
            date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        def _query():
            conn = self._conn()

            # Agent calls
            rows = conn.execute(
                "SELECT agent_name, status, COUNT(*) as cnt, "
                "AVG(elapsed_sec) as avg_sec "
                "FROM agent_calls WHERE DATE(timestamp) = ? "
                "GROUP BY agent_name, status",
                (date,),
            ).fetchall()
            agent_stats = {}
            for r in rows:
                name = r["agent_name"]
                if name not in agent_stats:
                    agent_stats[name] = {"total": 0, "completed": 0, "failed": 0, "avg_sec": 0}
                agent_stats[name]["total"] += r["cnt"]
                agent_stats[name][r["status"]] = r["cnt"]
                if r["status"] == "completed":
                    agent_stats[name]["avg_sec"] = round(r["avg_sec"], 1)

            # Conversations
            conv_count = conn.execute(
                "SELECT COUNT(DISTINCT conversation_id) as cnt "
                "FROM conversations WHERE DATE(timestamp) = ?",
                (date,),
            ).fetchone()["cnt"]

            # Recent questions
            questions = conn.execute(
                "SELECT message, agent_name, mode FROM conversations "
                "WHERE DATE(timestamp) = ? ORDER BY timestamp DESC LIMIT 5",
                (date,),
            ).fetchall()

            # Pipelines
            pipes = conn.execute(
                "SELECT pipeline_id, status, COUNT(*) as cnt "
                "FROM pipeline_runs WHERE DATE(timestamp) = ? "
                "GROUP BY pipeline_id, status",
                (date,),
            ).fetchall()

            conn.close()
            return {
                "date": date,
                "agent_stats": agent_stats,
                "conversation_count": conv_count,
                "recent_questions": [dict(q) for q in questions],
                "pipeline_stats": [dict(p) for p in pipes],
            }

        return await asyncio.get_event_loop().run_in_executor(None, _query)

    async def get_weekly_stats(self, end_date: Optional[str] = None) -> dict:
        """Get stats for the past 7 days."""
        if not end_date:
            end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d")

        def _query():
            conn = self._conn()

            # Daily trend
            daily_trend = conn.execute(
                "SELECT DATE(timestamp) as day, COUNT(*) as calls, "
                "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as success "
                "FROM agent_calls "
                "WHERE DATE(timestamp) BETWEEN ? AND ? "
                "GROUP BY DATE(timestamp) ORDER BY day",
                (start_date, end_date),
            ).fetchall()

            # Agent usage ranking
            agent_rank = conn.execute(
                "SELECT agent_name, COUNT(*) as cnt, "
                "AVG(elapsed_sec) as avg_sec "
                "FROM agent_calls "
                "WHERE DATE(timestamp) BETWEEN ? AND ? "
                "GROUP BY agent_name ORDER BY cnt DESC",
                (start_date, end_date),
            ).fetchall()

            # Topic keywords (from conversations)
            topics = conn.execute(
                "SELECT message FROM conversations "
                "WHERE DATE(timestamp) BETWEEN ? AND ? "
                "ORDER BY timestamp DESC LIMIT 50",
                (start_date, end_date),
            ).fetchall()

            # Pipeline summary
            pipe_summary = conn.execute(
                "SELECT pipeline_id, COUNT(*) as runs, "
                "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as success, "
                "AVG(elapsed_sec) as avg_sec "
                "FROM pipeline_runs "
                "WHERE DATE(timestamp) BETWEEN ? AND ? "
                "GROUP BY pipeline_id",
                (start_date, end_date),
            ).fetchall()

            # Total conversations
            total_conv = conn.execute(
                "SELECT COUNT(DISTINCT conversation_id) as cnt "
                "FROM conversations "
                "WHERE DATE(timestamp) BETWEEN ? AND ?",
                (start_date, end_date),
            ).fetchone()["cnt"]

            # Mode distribution
            mode_dist = conn.execute(
                "SELECT mode, COUNT(*) as cnt FROM conversations "
                "WHERE DATE(timestamp) BETWEEN ? AND ? "
                "GROUP BY mode",
                (start_date, end_date),
            ).fetchall()

            conn.close()
            return {
                "period": f"{start_date} ~ {end_date}",
                "daily_trend": [dict(d) for d in daily_trend],
                "agent_ranking": [dict(a) for a in agent_rank],
                "topic_messages": [r["message"] for r in topics],
                "pipeline_summary": [dict(p) for p in pipe_summary],
                "total_conversations": total_conv,
                "mode_distribution": [dict(m) for m in mode_dist],
            }

        return await asyncio.get_event_loop().run_in_executor(None, _query)


# Module-level singleton
tracker = UsageTracker()
