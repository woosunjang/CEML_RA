"""
Lab Orchestrator — Slack Bot Integration

Slack Bolt (Socket Mode) 서버.
멘션, DM, 슬래시 커맨드로 오케스트레이터 기능에 접근.

Usage:
    python -m integrations.slack_bot
"""

import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

logger = logging.getLogger("slack_bot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

# ── Config ──
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN", "")
API_BASE = os.getenv("ORCHESTRATOR_API_URL", "http://localhost:8000")

# Max Slack message length
MAX_MSG_LEN = 3000
# If total response exceeds this, upload as file instead of multi-message
FILE_UPLOAD_THRESHOLD = 6000

# Session tracking: channel_id → conversation_id
# Keeps the same conversation active per DM channel until user resets
_channel_sessions: dict[str, str] = {}

_NEW_CHAT_KEYWORDS = re.compile(
    r"^(새\s*대화|new\s*chat|리셋|reset|초기화|처음부터)$",
    re.IGNORECASE,
)

app = AsyncApp(token=SLACK_BOT_TOKEN)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _call_api(method: str, path: str, data: dict = None) -> dict:
    """Call orchestrator API."""
    import httpx
    url = f"{API_BASE}{path}"
    async with httpx.AsyncClient(timeout=300) as client:
        if method == "GET":
            resp = await client.get(url, params=data)
        else:
            resp = await client.post(url, json=data or {})
        resp.raise_for_status()
        return resp.json()


def _md_to_slack(text: str) -> str:
    """Convert markdown to Slack mrkdwn format."""
    # Bold: **text** → *text*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    # Headers: ### text → *text*
    text = re.sub(r"^#{1,4}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)
    # Code blocks: ```lang → ```
    text = re.sub(r"```\w+\n", "```\n", text)
    # Links: [text](url) → <url|text>
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)
    return text


def _split_message(text: str, max_len: int = MAX_MSG_LEN) -> list[str]:
    """Split long messages for Slack's limit."""
    if len(text) <= max_len:
        return [text]
    parts = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        # Find last newline within limit
        split_at = text.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            split_at = max_len
        parts.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return parts


async def _send_response(
    channel: str, loading_ts: Optional[str],
    formatted: str, say, client=None,
):
    """Send response: file upload for long content, messages for short."""
    # Detect if a file was already saved locally (Markdown or PPTX)
    has_saved_file = "**마크다운 저장 완료**" in formatted or "**PowerPoint 생성 완료**" in formatted
    
    if has_saved_file:
        # File is already saved to local directory, only send the header summary to Slack
        summary = formatted
        for delimiter in ["### 슬라이드 미리보기", "---"]:
            if delimiter in formatted:
                summary = formatted.split(delimiter)[0].strip()
                break
        
        if len(summary) > 1000:
            summary = summary[:1000] + "\n\n...(이하 상세 내용 생략)"
            
        if loading_ts:
            await _update_message(channel, loading_ts, summary)
        else:
            await say(summary)
        return

    # If the response is very long, upload it as a markdown file instead of spamming chat
    if len(formatted) > FILE_UPLOAD_THRESHOLD and client:
        try:
            # Show a brief preview of 400 chars and upload the rest as a file
            summary = formatted[:400]
            if len(formatted) > 400:
                summary += "\n\n📄 *전체 내용은 아래 업로드된 파일을 확인하세요.*"
                
            if loading_ts:
                await _update_message(channel, loading_ts, summary)
            else:
                await say(summary)

            await client.files_upload_v2(
                channel=channel,
                content=formatted,
                filename="response.md",
                title="전체 응답",
                initial_comment="📎 전체 응답 내용입니다.",
            )
            return
        except Exception as e:
            logger.warning(f"File upload failed, falling back to messages: {e}")

    # Standard fallback: split and send in chunks
    parts = _split_message(formatted)
    if loading_ts and parts:
        await _update_message(channel, loading_ts, parts[0])
        for part in parts[1:]:
            await say(part)
    else:
        for part in parts:
            await say(part)


def _agent_blocks(agents: list[dict]) -> list[dict]:
    """Build Block Kit blocks for agent list."""
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "🤖 에이전트 상태"}},
    ]
    for a in agents:
        status = "🟢" if a.get("online") else "🔴"
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{status} *{a.get('icon', '')} {a.get('display_name', a['name'])}*\n"
                    f"{a.get('description', '')}\n"
                    f"_{', '.join(a.get('capabilities', [])[:3])}_"
                ),
            },
        })
    return blocks


def _search_blocks(results: list[dict], query: str) -> list[dict]:
    """Build Block Kit blocks for memory search results."""
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"🔍 검색: {query}"}},
    ]
    if not results:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "검색 결과가 없습니다."},
        })
        return blocks

    for i, r in enumerate(results[:5]):
        fact = r.get("fact", "")[:300]
        created = r.get("created_at", "")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*[{i+1}]* {fact}\n_{created}_",
            },
        })
    return blocks


# ---------------------------------------------------------------------------
# Event: App Mention / DM
# ---------------------------------------------------------------------------

# Agents that show a label prefix in messages
_LABELED_AGENTS = {"literature", "teaching", "writing", "presentation", "project", "debate", "pipeline"}


def _format_response(agent: str, content: str) -> str:
    """Format response with optional agent label.
    
    Orchestrator (general chat) responses have no prefix.
    Specialized agent responses show *[agent]* prefix.
    """
    if agent in _LABELED_AGENTS:
        return f"*[{agent}]*\n\n{content}"
    return content


async def _update_message(channel: str, ts: str, text: str):
    """Update an existing Slack message via chat.update (best-effort)."""
    try:
        from slack_sdk.web.async_client import AsyncWebClient
        client = AsyncWebClient(token=SLACK_BOT_TOKEN)
        await client.chat_update(channel=channel, ts=ts, text=text)
    except Exception as e:
        logger.debug(f"Failed to update message: {e}")


@app.event("app_mention")
async def handle_mention(event, say, client):
    """Handle @bot mentions in channels — replies directly in channel (no thread)."""
    text = re.sub(r"<@\w+>\s*", "", event.get("text", "")).strip()
    if not text:
        await say("질문을 입력해주세요. 예: `@bot NASICON 도핑 조건 알려줘`")
        return

    channel = event.get("channel", "")

    # Send temporary "processing" message
    loading_msg = await say(f"🔄 처리 중... `{text[:50]}`")
    try:
        loading_ts = loading_msg["ts"]
    except (KeyError, TypeError):
        loading_ts = None

    try:
        conv_id = _channel_sessions.get(channel)
        result = await _call_api("POST", "/chat", {
            "message": text,
            "conversation_id": conv_id,
            "mode": "normal",
        })
        # Store returned conversation_id for session continuity
        if result.get("conversation_id"):
            _channel_sessions[channel] = result["conversation_id"]
        content = _md_to_slack(result.get("content", "응답 없음"))
        agent = result.get("agent_name", "orchestrator")
        formatted = _format_response(agent, content)

        await _send_response(channel, loading_ts, formatted, say, client)

    except Exception as e:
        logger.error(f"Mention handler error: {e}")
        if loading_ts:
            await _update_message(channel, loading_ts, f"❌ 오류: {e}")
        else:
            await say(f"❌ 오류: {e}")


@app.event("message")
async def handle_dm(event, say, client):
    """Handle direct messages."""
    # Only handle DMs (channel type 'im')
    if event.get("channel_type") != "im":
        return
    # Ignore bot's own messages
    if event.get("bot_id"):
        return

    text = event.get("text", "").strip()
    if not text:
        return

    channel = event.get("channel", "")

    # Handle clear command with args (e.g., 삭제 10, clear 30m, 비우기 1h)
    match = re.match(r"^(clear|cleanup|삭제|비우기)(?:\s+(.+))?$", text, re.IGNORECASE)
    if match:
        cmd = match.group(1)
        arg = match.group(2).strip() if match.group(2) else None
        
        limit_count = None
        cutoff_time = None
        
        if arg:
            # 1. 시간 파싱 시도 (예: 30m, 1h, 2d, 30분, 1시간, 2일)
            time_match = re.match(r"^(\d+)\s*(m|h|d|분|시간|일)$", arg, re.IGNORECASE)
            if time_match:
                amount = int(time_match.group(1))
                unit = time_match.group(2).lower()
                
                import time
                now = time.time()
                
                if unit in ("m", "분"):
                    delta = amount * 60
                elif unit in ("h", "시간"):
                    delta = amount * 3600
                elif unit in ("d", "일"):
                    delta = amount * 86400
                else:
                    delta = 0
                
                if delta > 0:
                    cutoff_time = now - delta
            else:
                # 2. 숫자(개수) 파싱 시도
                try:
                    limit_count = int(arg)
                except ValueError:
                    await say(
                        "❌ 올바른 형식의 인자가 아닙니다.\n"
                        "사용법:\n"
                        "- `삭제 10` (최근 봇 메시지 10개 삭제)\n"
                        "- `삭제 30m` 또는 `삭제 1h` (최근 30분 또는 1시간 이내 봇 메시지 삭제)\n"
                        "- `삭제` (기본 최근 100개 히스토리 중 봇 메시지 삭제)"
                    )
                    return

        loading_msg = await say("🧹 이전 메시지 삭제 작업을 시작합니다...")
        try:
            loading_ts = loading_msg["ts"]
        except (KeyError, TypeError):
            loading_ts = None

        try:
            auth_info = await app.client.auth_test()
            bot_user_id = auth_info.get("user_id")
        except Exception as e:
            logger.error(f"auth_test failed: {e}")
            bot_user_id = None

        try:
            # 기본적으로 최근 100개 히스토리를 가져옴
            history_limit = max(100, limit_count) if limit_count else 100
            
            response = await app.client.conversations_history(channel=channel, limit=history_limit)
            messages = response.get("messages", [])
            
            deleted_count = 0
            fail_count = 0
            for msg in messages:
                ts = msg.get("ts")
                # Skip the current loading message
                if loading_ts and ts == loading_ts:
                    continue
                    
                # Check if it is a bot message
                is_bot = False
                if msg.get("bot_id") or (bot_user_id and msg.get("user") == bot_user_id):
                    is_bot = True
                
                if not is_bot:
                    continue

                # 시간 조건 검사
                if cutoff_time:
                    try:
                        msg_ts = float(ts)
                        if msg_ts < cutoff_time:
                            break
                    except ValueError:
                        pass
                
                # 개수 조건 검사
                if limit_count is not None and deleted_count >= limit_count:
                    break
                
                try:
                    await app.client.chat_delete(channel=channel, ts=ts)
                    deleted_count += 1
                    await asyncio.sleep(0.05) # rate limit buffer
                except Exception as e:
                    logger.debug(f"Failed to delete message {ts}: {e}")
                    fail_count += 1
            
            # 결과 텍스트 포맷팅
            cond_str = ""
            if limit_count:
                cond_str = f"최근 {limit_count}개 기준, "
            elif cutoff_time:
                cond_str = f"최근 {arg} 이내 작성된 메시지 기준, "
            
            result_text = f"✅ 삭제 완료: {cond_str}봇이 작성한 메시지 {deleted_count}개를 삭제했습니다. (실패: {fail_count}개)\n*(참고: 슬랙 정책상 봇은 사용자가 작성한 메시지를 삭제할 수 없습니다.)*"
            if loading_ts:
                await _update_message(channel, loading_ts, result_text)
            else:
                await say(result_text)
        except Exception as e:
            logger.error(f"Failed to fetch history or delete: {e}")
            error_msg = f"❌ 메시지 삭제 중 오류가 발생했습니다: {e}\n슬랙 앱 설정에 `im:history` 권한이 추가되어 있는지 확인이 필요할 수 있습니다."
            if loading_ts:
                await _update_message(channel, loading_ts, error_msg)
            else:
                await say(error_msg)
        return

    # Send temporary "processing" message
    loading_msg = await say("🔄 처리 중...")
    try:
        loading_ts = loading_msg["ts"]
    except (KeyError, TypeError):
        loading_ts = None


    # Handle new conversation request
    if _NEW_CHAT_KEYWORDS.match(text):
        old = _channel_sessions.pop(channel, None)
        status = "이전 대화를 종료" if old else "새로운 대화를 시작"
        if loading_ts:
            await _update_message(channel, loading_ts, f"✨ {status}합니다. 새 대화를 시작하세요!")
        else:
            await say(f"✨ {status}합니다. 새 대화를 시작하세요!")
        return

    try:
        conv_id = _channel_sessions.get(channel)
        result = await _call_api("POST", "/chat", {
            "message": text,
            "conversation_id": conv_id,
            "mode": "normal",
        })
        # Store returned conversation_id for session continuity
        if result.get("conversation_id"):
            _channel_sessions[channel] = result["conversation_id"]
        content = _md_to_slack(result.get("content", "응답 없음"))
        agent = result.get("agent_name", "orchestrator")
        formatted = _format_response(agent, content)

        await _send_response(channel, loading_ts, formatted, say, client)

    except Exception as e:
        logger.error(f"DM handler error: {e}")
        if loading_ts:
            await _update_message(channel, loading_ts, f"❌ 오류: {e}")
        else:
            await say(f"❌ 오류: {e}")



# ---------------------------------------------------------------------------
# Slash Commands
# ---------------------------------------------------------------------------
@app.command("/ask")
async def handle_ask(ack, say, command):
    """/ask — 일반 질문"""
    await ack()
    text = command.get("text", "").strip()
    if not text:
        await say("사용법: `/ask 질문 내용`")
        return

    msg = await say(f"🔄 처리 중... `{text[:50]}`")

    try:
        result = await _call_api("POST", "/chat", {
            "message": text,
            "mode": "normal",
        })
        content = _md_to_slack(result.get("content", "응답 없음"))
        agent = result.get("agent_name", "orchestrator")
        thread_ts = msg.get("ts") if isinstance(msg, dict) else None

        parts = _split_message(f"*[{agent}]*\n\n{content}")
        for part in parts:
            await say(part, thread_ts=thread_ts)

    except Exception as e:
        await say(f"❌ 오류: {e}")


@app.command("/debate")
async def handle_debate(ack, say, command):
    """/debate — Multi-LLM Debate 모드"""
    await ack()
    text = command.get("text", "").strip()
    if not text:
        await say("사용법: `/debate 토론 주제`")
        return

    msg = await say(f"🏛️ Debate 시작: `{text[:50]}`\n🟢 패널리스트 소집 중...")

    try:
        # Use streaming for progress
        import httpx
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "GET",
                f"{API_BASE}/debate/stream",
                params={"q": text, "rounds": 3},
            ) as resp:
                thread_ts = msg.get("ts") if isinstance(msg, dict) else None
                event_type = ""
                async for line in resp.aiter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: ") and event_type:
                        try:
                            data = json.loads(line[6:])
                            if event_type == "round_start":
                                round_num = data.get("round", 1)
                                await say(f"📢 라운드 {round_num} 시작", thread_ts=thread_ts)
                            elif event_type == "panelist_done":
                                name = data.get("panelist", "")
                                icon = {"analyst": "🟢", "critic": "🟣", "synthesizer": "🔵"}.get(name, "⚪")
                                await say(f"{icon} {name} 응답 완료", thread_ts=thread_ts)
                            elif event_type == "judge_start":
                                await say("⚖️ Judge 종합 중...", thread_ts=thread_ts)
                            elif event_type == "debate_done":
                                answer = data.get("final_answer", "")
                                content = _md_to_slack(answer)
                                parts = _split_message(f"*[debate]*\n\n{content}")
                                for part in parts:
                                    await say(part, thread_ts=thread_ts)
                        except json.JSONDecodeError:
                            pass
                        event_type = ""

    except Exception as e:
        logger.error(f"Debate error: {e}")
        await say(f"❌ Debate 오류: {e}")


@app.command("/memsearch")
async def handle_search(ack, say, command):
    """/memsearch — 장기 기억 검색"""
    await ack()
    query = command.get("text", "").strip()
    if not query:
        await say("사용법: `/memsearch 검색어`")
        return

    try:
        result = await _call_api("GET", "/memory/search", {"q": query, "limit": 5})
        blocks = _search_blocks(result.get("results", []), query)
        await say(blocks=blocks)
    except Exception as e:
        await say(f"❌ 검색 오류: {e}")


@app.command("/agents")
async def handle_agents(ack, say, command):
    """/agents — 에이전트 상태 조회"""
    await ack()
    try:
        result = await _call_api("GET", "/agents")
        blocks = _agent_blocks(result.get("agents", []))
        await say(blocks=blocks)
    except Exception as e:
        await say(f"❌ 에이전트 조회 오류: {e}")


@app.command("/profile")
async def handle_profile(ack, say, command):
    """/profile — 모델 프로필 전환"""
    await ack()
    profile = command.get("text", "").strip().lower()
    if profile not in ("cost", "performance"):
        await say("사용법: `/profile cost` 또는 `/profile performance`")
        return

    try:
        result = await _call_api("POST", "/model-profile", {"profile": profile})
        success = result.get("success", False)
        msg = result.get("message", "")
        icon = "✅" if success else "❌"
        await say(f"{icon} {msg}")
    except Exception as e:
        await say(f"❌ 프로필 전환 오류: {e}")


@app.command("/brief")
async def handle_brief(ack, say, command, client):
    """/brief — Scout/Knowledge proactive brief.

    Usage:
      /brief today
      /brief week
      /brief topic materials ontology
    """
    await ack()
    text = command.get("text", "").strip()
    channel = command.get("channel_id", "")

    from datetime import datetime, timedelta, timezone
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%Y-%m-%d")

    if not text or text.lower() == "today":
        payload = {"date": today, "days": 1, "promote": True}
        label = f"오늘({today})"
    elif text.lower() == "week":
        payload = {"date": today, "days": 7, "promote": True}
        label = "최근 7일"
    elif text.lower().startswith("topic "):
        query = text[6:].strip()
        if not query:
            await say("사용법: `/brief topic 검색어`")
            return
        payload = {"date": today, "days": 7, "query": query, "promote": True}
        label = f"토픽 `{query}`"
    else:
        await say("사용법: `/brief today`, `/brief week`, `/brief topic 검색어`")
        return

    loading = await say(f"🧭 Proactive Brief 생성 중... {label}")
    loading_ts = loading.get("ts") if isinstance(loading, dict) else None

    try:
        result = await _call_api("POST", "/knowledge/briefs/generate", payload)
        markdown = result.get("markdown", "Brief 생성 결과가 비어 있습니다.")
        formatted = _md_to_slack(markdown)
        await _send_response(channel, loading_ts, formatted, say, client)
    except Exception as e:
        logger.error(f"Brief command error: {e}")
        if loading_ts:
            await _update_message(channel, loading_ts, f"❌ Brief 오류: {e}")
        else:
            await say(f"❌ Brief 오류: {e}")


@app.command("/labstatus")
async def handle_status(ack, say, command):
    """/labstatus — 시스템 상태 조회"""
    await ack()
    try:
        health = await _call_api("GET", "/health")
        profile = await _call_api("GET", "/model-profile")
        agents_data = await _call_api("GET", "/agents")
        online = sum(1 for a in agents_data.get("agents", []) if a.get("online"))
        total = len(agents_data.get("agents", []))

        active = profile.get("active_profile", "unknown")
        profile_icon = "🚀" if active == "performance" else "💰"

        text = (
            f"*🧠 CEML Lab Orchestrator Status*\n"
            f"• 서버: {'🟢 Online' if health.get('status') == 'ok' else '🔴 Offline'}\n"
            f"• 에이전트: {online}/{total} 활성\n"
            f"• 모델 프로필: {profile_icon} {active}\n"
        )
        await say(text)
    except Exception as e:
        await say(f"❌ 상태 조회 오류: {e}")


@app.command("/report")
async def handle_report(ack, say, command):
    """/report — 수동 리포트 생성

    Usage:
      /report daily         — 논문 데일리 리포트 (여기에 출력)
      /report weekly        — 논문 주간 리포트 (여기에 출력)
      /report system        — 시스템 주간 리포트 (여기에 출력)
      /report project       — 프로젝트 주간 리포트 (여기에 출력)
      /report test          — 모든 채널에 테스트 전송 (실제 채널에 발송)
    """
    await ack()
    report_type = command.get("text", "").strip().lower()
    valid_types = ("daily", "weekly", "system", "project", "test")
    if report_type not in valid_types:
        await say(
            "사용법:\n"
            "• `/report daily` — 논문 데일리 리포트\n"
            "• `/report weekly` — 논문 주간 리포트\n"
            "• `/report system` — 시스템 주간 리포트\n"
            "• `/report project` — 프로젝트 주간 리포트\n"
            "• `/report test` — 모든 채널에 테스트 전송"
        )
        return

    # test: 모든 채널에 즉시 전송
    if report_type == "test":
        await say("🧪 모든 리포트 채널에 테스트 전송을 시작합니다...")
        try:
            from integrations.report_scheduler import test_all_channels
            results = await test_all_channels()
            lines = ["*🧪 채널 테스트 결과*\n"]
            for key, info in results.items():
                ch = info.get("channel", "")
                if info.get("ok"):
                    lines.append(f"  ✅ `{key}` → {ch}")
                elif info.get("error"):
                    lines.append(f"  ❌ `{key}` → {ch}: {info['error']}")
                else:
                    lines.append(f"  ⚠️ `{key}` → {ch}: ok={info.get('ok')}")
            await say("\n".join(lines))
        except Exception as e:
            await say(f"❌ 테스트 오류: {e}")
        return

    label = {
        "daily": "논문 데일리",
        "weekly": "논문 주간",
        "system": "시스템 주간",
        "project": "프로젝트 주간",
    }[report_type]
    await say(f"📊 {label} 리포트 생성 중...")
    try:
        from integrations.report_generator import (
            generate_papers_daily, generate_papers_weekly,
            generate_weekly_report, generate_project_weekly,
        )
        if report_type == "daily":
            content = await generate_papers_daily()
        elif report_type == "weekly":
            content = await generate_papers_weekly()
        elif report_type == "project":
            content = await generate_project_weekly()
        else:  # system
            content = await generate_weekly_report()

        parts = _split_message(_md_to_slack(content))
        for part in parts:
            await say(part)
    except Exception as e:
        await say(f"❌ 리포트 생성 오류: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
        logger.error("SLACK_BOT_TOKEN and SLACK_APP_TOKEN are required in .env")
        sys.exit(1)

    # Start report scheduler (non-blocking)
    try:
        from integrations.report_scheduler import start_scheduler
        await start_scheduler()
    except Exception as e:
        logger.warning(f"Report scheduler init failed (continuing): {e}")

    # Start file command watcher (non-blocking)
    try:
        from integrations.file_command import start_file_watcher
        await start_file_watcher()
    except Exception as e:
        logger.warning(f"File command watcher init failed (continuing): {e}")

    handler = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)
    logger.info("Slack bot starting (Socket Mode)...")
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(main())
