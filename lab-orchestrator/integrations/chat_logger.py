"""
Lab Orchestrator — Chat Logger

대화 내용을 마크다운 파일로 저장.
사용자 메시지 + 에이전트 응답을 일별 파일에 시간순으로 기록.

저장 경로: lab-orchestrator/logs/chat/YYYY-MM-DD.md
"""

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("chat_logger")

from orchestrator.config import CHAT_LOG_DIR
_LOG_DIR = CHAT_LOG_DIR


def _ensure_dir():
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_turn(
    user_message: str,
    assistant_message: str,
    agent_name: str = "orchestrator",
    conversation_id: str = "",
    mode: str = "normal",
    source: str = "web",
):
    """Append a conversation turn to today's log file.

    Args:
        user_message: 사용자 입력
        assistant_message: 에이전트 응답
        agent_name: 응답한 에이전트
        conversation_id: 대화 세션 ID
        mode: normal | debate | pipeline
        source: web | slack | file
    """
    _ensure_dir()

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    log_path = _LOG_DIR / f"{date_str}.md"

    # Truncate very long messages for log readability
    user_short = user_message[:2000]
    asst_short = assistant_message[:5000]

    mode_icon = {"debate": "🏛️", "pipeline": "🔗"}.get(mode, "")
    source_icon = {"slack": "💬", "file": "📁", "web": "🌐"}.get(source, "")

    entry = (
        f"\n---\n\n"
        f"### {time_str} {source_icon} {mode_icon}\n"
        f"> **conv**: `{conversation_id[:12]}` | "
        f"**agent**: `{agent_name}` | **mode**: `{mode}`\n\n"
        f"**👤 User**\n\n{user_short}\n\n"
        f"**🤖 {agent_name}**\n\n{asst_short}\n"
    )

    try:
        # Append header if new file
        if not log_path.exists():
            header = f"# 대화 로그 — {date_str}\n\n"
            log_path.write_text(header, encoding="utf-8")

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)

    except Exception as e:
        logger.warning(f"Chat log write failed: {e}")
