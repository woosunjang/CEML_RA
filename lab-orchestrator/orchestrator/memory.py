"""
Lab Orchestrator — 3-Tier Memory System

Implements Letta-inspired tiered memory:
  - Core Memory: always injected (~200 tokens), user prefs & workspace
  - Recall Memory: recent 5 turns verbatim + auto-summarization every 20 turns
  - Archival Memory: key decisions stored in Qdrant, searched on demand

Usage:
    memory = memory_store.get_or_create(conv_id)
    context = memory.build_llm_context(workspace_context="...")
    # → returns Core + Recall ready for system prompt injection
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Core Memory — always present in context
# ---------------------------------------------------------------------------

_DEFAULT_CORE = {
    "user_prefs": {
        "language": "한국어 (기술 용어 영어 병기)",
        "level": "학부 3학년 기본, 필요 시 조정",
        "style": "존대말, 간결하고 직접적",
    },
    "active_project": None,
    "key_facts": [],  # ["NASICON 논문 5편 분석 완료", ...]
}


class CoreMemory:
    """Persistent user/project facts. Always in context."""

    def __init__(self, data: Optional[dict] = None):
        self._data = data or dict(_DEFAULT_CORE)

    def update_fact(self, fact: str):
        """Add or update a key fact."""
        facts = self._data.setdefault("key_facts", [])
        if fact not in facts:
            facts.append(fact)
            # Keep max 10 facts (FIFO)
            if len(facts) > 10:
                facts.pop(0)

    def set_project(self, project_name: str):
        self._data["active_project"] = project_name

    def to_prompt(self, workspace_context: str = "") -> str:
        """Render as prompt text (~200 tokens)."""
        lines = ["## 사용자 프로필"]
        prefs = self._data.get("user_prefs", {})
        for k, v in prefs.items():
            lines.append(f"- {k}: {v}")

        proj = self._data.get("active_project")
        if proj:
            lines.append(f"\n## 활성 프로젝트: {proj}")

        if workspace_context:
            lines.append(f"\n## 프로젝트 배경\n{workspace_context}")

        facts = self._data.get("key_facts", [])
        if facts:
            lines.append("\n## 핵심 사실")
            for f in facts:
                lines.append(f"- {f}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return self._data

    @classmethod
    def from_dict(cls, data: dict) -> "CoreMemory":
        return cls(data)


# ---------------------------------------------------------------------------
# Shared Memory (Session)
# ---------------------------------------------------------------------------

class SharedMemory:
    """3-tier memory for a single conversation session."""

    SUMMARIZE_THRESHOLD = 20  # Summarize after this many messages

    def __init__(self, conversation_id: Optional[str] = None):
        self.conversation_id = conversation_id or str(uuid.uuid4())
        self.messages: list[dict] = []
        self.summaries: list[dict] = []  # Compressed past conversation
        self.core = CoreMemory()
        self.task_context: dict = {}
        self.active_documents: list[str] = []
        self.agent_results: list[dict] = []
        self.created_at = datetime.now().isoformat()
        self._turn_count = 0

    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.messages.append({
            "role": "user",
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        self._turn_count += 1

    def add_assistant_message(self, content: str, agent_name: str = "orchestrator"):
        """Add an assistant message to history."""
        self.messages.append({
            "role": "assistant",
            "content": content,
            "agent_name": agent_name,
            "timestamp": datetime.now().isoformat(),
        })
        self._turn_count += 1

    def needs_summarization(self) -> bool:
        """Check if conversation should be summarized."""
        return len(self.messages) >= self.SUMMARIZE_THRESHOLD

    def compress(self, summary_text: str):
        """Compress old messages into a summary, keeping recent 6 messages."""
        # Keep recent messages
        keep_count = 6
        old_messages = self.messages[:-keep_count] if len(self.messages) > keep_count else []
        recent = self.messages[-keep_count:] if len(self.messages) > keep_count else self.messages

        if old_messages:
            self.summaries.append({
                "summary": summary_text,
                "message_count": len(old_messages),
                "timestamp": datetime.now().isoformat(),
            })
            self.messages = recent
            logger.info(
                f"Compressed {len(old_messages)} messages into summary "
                f"(session {self.conversation_id[:8]})"
            )

    def get_recent_context(self, n_turns: int = 3) -> list[dict]:
        """Get recent conversation turns for LLM context."""
        recent = self.messages[-(n_turns * 2):]
        return [{"role": m["role"], "content": m["content"]} for m in recent]

    async def build_llm_context(
        self, workspace_context: str = "", query: str = ""
    ) -> str:
        """Build full context for LLM injection.

        Returns a string containing:
          1. Core Memory (always)
          2. Previous summaries (if any)
          3. Archival Memory (query-relevant long-term facts)
        """
        parts = []

        # 1. Core Memory
        parts.append(self.core.to_prompt(workspace_context))

        # 2. Summaries
        if self.summaries:
            # Only include the most recent 2 summaries
            recent_summaries = self.summaries[-2:]
            summary_text = "\n".join(s["summary"] for s in recent_summaries)
            parts.append(f"\n## 이전 대화 요약\n{summary_text}")

        # 3. Archival Memory — search for relevant long-term facts
        if query:
            try:
                from orchestrator.archival import archival_memory
                facts = await archival_memory.search(query, limit=3)
                if facts:
                    fact_lines = []
                    for f in facts:
                        ts = f.get("created_at")
                        ts_str = f" ({ts})" if ts else ""
                        fact_lines.append(f"- {f['fact']}{ts_str}")
                    fact_text = "\n".join(fact_lines)
                    parts.append(f"\n## 관련 장기 기억\n{fact_text}")
            except Exception as e:
                logger.warning(f"Archival search skipped: {e}")

        return "\n\n".join(parts)

    def store_agent_result(self, result: dict):
        """Store an agent result for subsequent agents to reference."""
        self.agent_results.append(result)

    def get_agent_results(self) -> list[dict]:
        return self.agent_results

    def clear_task_context(self):
        """Clear task-specific context (keep conversation history)."""
        self.task_context = {}
        self.agent_results = []
        self.active_documents = []

    def to_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "messages": self.messages,
            "summaries": self.summaries,
            "core_memory": self.core.to_dict(),
            "task_context": self.task_context,
            "active_documents": self.active_documents,
            "agent_results": self.agent_results,
            "created_at": self.created_at,
            "turn_count": self._turn_count,
        }


# ---------------------------------------------------------------------------
# Memory Store — persistent across sessions
# ---------------------------------------------------------------------------

class MemoryStore:
    """In-memory store with JSON file persistence."""

    from orchestrator.config import SESSIONS_DIR
    STORE_DIR = SESSIONS_DIR

    def __init__(self):
        self._sessions: dict[str, SharedMemory] = {}
        self.STORE_DIR.mkdir(parents=True, exist_ok=True)

    def get_or_create(self, conversation_id: Optional[str] = None) -> SharedMemory:
        """Get existing session or create/load one."""
        if conversation_id and conversation_id in self._sessions:
            return self._sessions[conversation_id]

        # Try loading from disk
        if conversation_id:
            loaded = self._load_from_disk(conversation_id)
            if loaded:
                self._sessions[conversation_id] = loaded
                return loaded

        memory = SharedMemory(conversation_id)
        self._sessions[memory.conversation_id] = memory
        logger.info(f"Created new session: {memory.conversation_id}")
        return memory

    def get(self, conversation_id: str) -> Optional[SharedMemory]:
        if conversation_id in self._sessions:
            return self._sessions[conversation_id]
        return self._load_from_disk(conversation_id)

    def list_sessions(self) -> list[str]:
        disk_sessions = set()
        if self.STORE_DIR.exists():
            disk_sessions = {f.stem for f in self.STORE_DIR.glob("*.json")}
        return list(set(self._sessions.keys()) | disk_sessions)

    def list_sessions_detail(self) -> list[dict]:
        """List all sessions with metadata for UI display."""
        result = []
        all_ids = self.list_sessions()
        for sid in all_ids:
            try:
                meta = self._get_session_meta(sid)
                if meta:
                    result.append(meta)
            except Exception:
                continue
        # Sort by last_message_at descending (most recent first)
        result.sort(key=lambda x: x.get("last_message_at", ""), reverse=True)
        return result

    def _get_session_meta(self, conversation_id: str) -> Optional[dict]:
        """Extract metadata from a session without loading full messages."""
        # Try in-memory first
        memory = self._sessions.get(conversation_id)
        if memory:
            return self._meta_from_memory(memory)

        # Try disk
        path = self.STORE_DIR / f"{conversation_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            messages = data.get("messages", [])
            title = ""
            last_at = data.get("created_at", "")
            for m in messages:
                if m.get("role") == "user":
                    title = m.get("content", "")[:60]
                    break
            if messages:
                last_at = messages[-1].get("timestamp", last_at)
            return {
                "conversation_id": conversation_id,
                "title": title or "(새 대화)",
                "created_at": data.get("created_at", ""),
                "last_message_at": last_at,
                "message_count": len(messages),
            }
        except Exception:
            return None

    @staticmethod
    def _meta_from_memory(memory: "SharedMemory") -> dict:
        """Extract metadata from an in-memory SharedMemory."""
        title = ""
        last_at = memory.created_at
        for m in memory.messages:
            if m.get("role") == "user":
                title = m.get("content", "")[:60]
                break
        if memory.messages:
            last_at = memory.messages[-1].get("timestamp", last_at)
        return {
            "conversation_id": memory.conversation_id,
            "title": title or "(새 대화)",
            "created_at": memory.created_at,
            "last_message_at": last_at,
            "message_count": len(memory.messages),
        }

    def get_session_messages(self, conversation_id: str) -> Optional[list[dict]]:
        """Get all messages for a specific session."""
        memory = self.get_or_create(conversation_id)
        if not memory:
            return None
        return memory.messages

    def delete(self, conversation_id: str):
        self._sessions.pop(conversation_id, None)
        path = self.STORE_DIR / f"{conversation_id}.json"
        if path.exists():
            path.unlink()

    def save(self, conversation_id: str):
        """Persist a session to disk."""
        memory = self._sessions.get(conversation_id)
        if not memory:
            return
        try:
            path = self.STORE_DIR / f"{conversation_id}.json"
            path.write_text(
                json.dumps(memory.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Failed to persist session {conversation_id}: {e}")

    def _load_from_disk(self, conversation_id: str) -> Optional[SharedMemory]:
        path = self.STORE_DIR / f"{conversation_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            memory = SharedMemory(conversation_id)
            memory.messages = data.get("messages", [])
            memory.summaries = data.get("summaries", [])
            memory.task_context = data.get("task_context", {})
            memory.active_documents = data.get("active_documents", [])
            memory.agent_results = data.get("agent_results", [])
            memory.created_at = data.get("created_at", memory.created_at)
            memory._turn_count = data.get("turn_count", len(memory.messages))

            # Restore core memory
            core_data = data.get("core_memory")
            if core_data:
                memory.core = CoreMemory.from_dict(core_data)

            logger.info(f"Loaded session from disk: {conversation_id}")
            return memory
        except Exception as e:
            logger.warning(f"Failed to load session {conversation_id}: {e}")
            return None


# Module-level singleton
memory_store = MemoryStore()
