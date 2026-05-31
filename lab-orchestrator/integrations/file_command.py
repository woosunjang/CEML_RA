"""
Lab Orchestrator — File Command Interface

Slack 불가 시 폴백: 공유 폴더의 마크다운 파일로 명령을 보내고 결과를 받는다.

디렉토리 구조:
    lab-orchestrator/commands/
    ├── inbox/      ← 사용자가 명령 파일을 여기에 놓음
    ├── outbox/     ← 결과 파일이 여기에 생성됨
    └── archive/    ← 처리 완료된 명령 파일 보관

명령 파일 포맷:
    ---
    command: ask
    agent: literature      (optional)
    mode: normal           (optional: normal | debate)
    ---

    NASICON 고체전해질의 Al 도핑 효과를 정리해줘

지원 커맨드: ask, debate, search, pipeline, report, status
"""

import asyncio
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("file_command")

from orchestrator.config import COMMANDS_DIR as _CMD_DIR
COMMANDS_DIR = _CMD_DIR
INBOX = COMMANDS_DIR / "inbox"
OUTBOX = COMMANDS_DIR / "outbox"
ARCHIVE = COMMANDS_DIR / "archive"

POLL_INTERVAL = 30  # seconds


def _ensure_dirs():
    for d in (INBOX, OUTBOX, ARCHIVE):
        d.mkdir(parents=True, exist_ok=True)


def _parse_command_file(path: Path) -> dict:
    """Parse a markdown command file.

    Supports two formats:
    1. YAML frontmatter: ---\ncommand: ask\n---\n본문
    2. 자연어: frontmatter 없이 본문만 작성 → 자동으로 ask 명령 처리
    """
    content = path.read_text(encoding="utf-8").strip()

    # Try to extract frontmatter
    meta = {}
    body = content
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if match:
        frontmatter = match.group(1)
        body = match.group(2).strip()
        for line in frontmatter.split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip().lower()] = val.strip()

    # No frontmatter → treat entire content as natural language ask
    # (body is already set to full content in this case)

    return {
        "command": meta.get("command", "ask"),
        "agent": meta.get("agent", ""),
        "mode": meta.get("mode", "normal"),
        "body": body,
        "filename": path.name,
    }


async def _execute_command(cmd: dict) -> str:
    """Execute a parsed command and return result text."""
    command = cmd["command"]
    body = cmd["body"]
    agent = cmd.get("agent", "")
    mode = cmd.get("mode", "normal")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
    header = f"# 실행 결과\n> 명령: `{command}` | 시각: {timestamp}\n\n---\n\n"

    try:
        if command in ("ask", "question"):
            return header + await _cmd_ask(body, agent, mode)
        elif command == "debate":
            return header + await _cmd_ask(body, agent, "debate")
        elif command == "search":
            return header + await _cmd_search(body)
        elif command == "report":
            return header + await _cmd_report(body)
        elif command == "status":
            return header + await _cmd_status()
        elif command == "pipeline":
            return header + await _cmd_pipeline(body)
        else:
            return header + f"❌ 알 수 없는 명령: `{command}`\n\n지원 명령: ask, debate, search, report, status, pipeline"
    except Exception as e:
        logger.error(f"Command execution error: {e}")
        return header + f"❌ 실행 오류: {e}"


async def _cmd_ask(message: str, agent: str = "", mode: str = "normal") -> str:
    """Execute ask/debate command via API."""
    import httpx
    api_base = os.getenv("ORCHESTRATOR_API_URL", "http://localhost:8000")
    payload = {"message": message, "mode": mode}
    if agent:
        payload["agent_override"] = agent

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(f"{api_base}/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

    content = data.get("content", "응답 없음")
    agent_name = data.get("agent_name", "unknown")
    return f"**[{agent_name}]**\n\n{content}"


async def _cmd_search(query: str) -> str:
    """Execute memory search."""
    import httpx
    api_base = os.getenv("ORCHESTRATOR_API_URL", "http://localhost:8000")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{api_base}/memory/search", params={"q": query, "limit": 5})
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    if not results:
        return "검색 결과 없음"

    lines = [f"## 🔍 검색: {query}\n"]
    for i, r in enumerate(results):
        lines.append(f"**[{i+1}]** {r.get('fact', '')[:300]}")
        if r.get("created_at"):
            lines.append(f"  _{r['created_at']}_\n")
    return "\n".join(lines)


async def _cmd_report(report_type: str) -> str:
    """Generate a report."""
    report_type = report_type.strip().lower()
    if report_type not in ("daily", "weekly"):
        report_type = "daily"

    from integrations.report_generator import generate_daily_report, generate_weekly_report
    if report_type == "daily":
        return await generate_daily_report()
    else:
        return await generate_weekly_report()


async def _cmd_status() -> str:
    """Get system status."""
    import httpx
    api_base = os.getenv("ORCHESTRATOR_API_URL", "http://localhost:8000")

    async with httpx.AsyncClient(timeout=10) as client:
        health = (await client.get(f"{api_base}/health")).json()
        profile = (await client.get(f"{api_base}/model-profile")).json()
        agents = (await client.get(f"{api_base}/agents")).json()

    online = sum(1 for a in agents.get("agents", []) if a.get("online"))
    total = len(agents.get("agents", []))
    active = profile.get("active_profile", "unknown")

    return (
        f"## 🧠 시스템 상태\n\n"
        f"- 서버: {'🟢 Online' if health.get('status') == 'ok' else '🔴 Offline'}\n"
        f"- 에이전트: {online}/{total} 활성\n"
        f"- 모델 프로필: {'🚀' if active == 'performance' else '💰'} {active}\n"
    )


async def _cmd_pipeline(body: str) -> str:
    """Trigger a pipeline."""
    import httpx
    api_base = os.getenv("ORCHESTRATOR_API_URL", "http://localhost:8000")

    # Parse: first line = pipeline_id, rest = message
    lines = body.strip().split("\n", 1)
    pipeline_id = lines[0].strip()
    message = lines[1].strip() if len(lines) > 1 else ""

    payload = {
        "message": message or f"Run pipeline {pipeline_id}",
        "mode": "pipeline",
        "pipeline_id": pipeline_id,
    }

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(f"{api_base}/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

    return f"**파이프라인 `{pipeline_id}` 실행 완료**\n\n{data.get('content', '')}"


async def _watch_inbox():
    """Watch inbox for new command files."""
    _ensure_dirs()
    processed = set()

    while True:
        try:
            for f in sorted(INBOX.glob("*.md")):
                if f.name in processed:
                    continue

                logger.info(f"Processing command file: {f.name}")
                processed.add(f.name)

                cmd = _parse_command_file(f)
                result = await _execute_command(cmd)

                # Write result to outbox
                out_path = OUTBOX / f.name
                out_path.write_text(result, encoding="utf-8")
                logger.info(f"Result written: {out_path.name}")

                # Move original to archive
                archive_path = ARCHIVE / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{f.name}"
                f.rename(archive_path)

                # Notify via Slack if possible
                try:
                    from integrations.slack_notifier import slack_notify_webhook
                    await slack_notify_webhook(
                        f"📁 파일 명령 처리 완료: `{f.name}` → `outbox/{f.name}`"
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"File watcher error: {e}")

        await asyncio.sleep(POLL_INTERVAL)


async def start_file_watcher():
    """Start the file command watcher as a background task."""
    _ensure_dirs()
    asyncio.create_task(_watch_inbox())
    logger.info(f"File command watcher started: {INBOX}")
