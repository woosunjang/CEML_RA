"""
Lab Orchestrator — Slack Notifier

범용 알림 시스템.
파이프라인 완료, 에이전트 오류, Scout 수집 등의 이벤트를 Slack 채널/DM으로 전달.

Usage:
    from integrations.slack_notifier import slack_notify, notify_error, notify_pipeline_done
    await slack_notify("#research-papers", "새 논문 수집 완료")
    await notify_error("literature", "API rate limit exceeded")
    await notify_pipeline_done(user_id, "literature_to_writing", result)
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = logging.getLogger("slack_notifier")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_WEBHOOK_API = os.getenv("SLACK_WEBHOOK_API", "")

# Default channels
CHANNEL_ALERTS = os.getenv("SLACK_CHANNEL_ALERTS", "#system-alerts")
CHANNEL_PAPERS = os.getenv("SLACK_CHANNEL_PAPERS", "#research-papers")


async def slack_notify(
    channel: str,
    text: str,
    blocks: Optional[list[dict]] = None,
    thread_ts: Optional[str] = None,
) -> bool:
    """Send a notification to a Slack channel or user.

    Args:
        channel: Channel name (#channel) or user ID (U...) for DM.
        text: Fallback text for notifications.
        blocks: Optional Block Kit blocks.
        thread_ts: Thread to reply to.

    Returns:
        True on success, False on failure.
    """
    if not SLACK_BOT_TOKEN:
        logger.warning("SLACK_BOT_TOKEN not set, skipping notification")
        return False

    try:
        from slack_sdk.web.async_client import AsyncWebClient
        client = AsyncWebClient(token=SLACK_BOT_TOKEN)

        kwargs = {
            "channel": channel,
            "text": text,
        }
        if blocks:
            kwargs["blocks"] = blocks
        if thread_ts:
            kwargs["thread_ts"] = thread_ts

        result = await client.chat_postMessage(**kwargs)
        logger.info(f"Notification sent to {channel}: {text[:50]}...")
        return result.get("ok", False)

    except Exception as e:
        # Notification failure must never block the main workflow
        logger.warning(f"Slack notification failed ({channel}): {e}")
        return False


async def slack_notify_webhook(text: str) -> bool:
    """Send notification via incoming webhook (for simple alerts)."""
    if not SLACK_WEBHOOK_API:
        return False

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(SLACK_WEBHOOK_API, json={"text": text})
            return resp.status_code == 200
    except Exception as e:
        logger.warning(f"Webhook notification failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Typed notification helpers
# ---------------------------------------------------------------------------

async def notify_error(agent_name: str, error: str, details: str = ""):
    """Send agent error alert to #system-alerts."""
    text = f"🚨 *에이전트 오류*\n• Agent: `{agent_name}`\n• Error: {error}"
    if details:
        text += f"\n• Details: {details[:500]}"

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "🚨 에이전트 오류"}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Agent:*\n`{agent_name}`"},
                {"type": "mrkdwn", "text": f"*Error:*\n{error[:200]}"},
            ],
        },
    ]
    if details:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{details[:800]}```"},
        })

    await slack_notify(CHANNEL_ALERTS, text, blocks=blocks)


async def notify_pipeline_done(
    user_id: str,
    pipeline_id: str,
    status: str = "completed",
    summary: str = "",
):
    """Notify user that a pipeline has completed (via DM)."""
    icon = "✅" if status == "completed" else "❌"
    text = f"{icon} *파이프라인 완료*\n• Pipeline: `{pipeline_id}`\n• Status: {status}"
    if summary:
        text += f"\n\n{summary[:1000]}"

    await slack_notify(user_id, text)


async def notify_scout_papers(
    papers: list[dict],
    total_new: int = 0,
):
    """Notify about new papers collected by Scout."""
    if not papers:
        return

    text = f"📚 *Scout: 신규 논문 {total_new}편 수집*"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"📚 신규 논문 {total_new}편"}},
    ]
    for p in papers[:5]:
        title = p.get("title", "Untitled")
        score = p.get("relevance_score", 0)
        source = p.get("source", "")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{title}*\n_{source}_ · 관련도: {score:.0%}",
            },
        })

    if total_new > 5:
        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"외 {total_new - 5}편 더..."},
            ],
        })

    await slack_notify(CHANNEL_PAPERS, text, blocks=blocks)


async def notify_weekly_digest():
    """Send weekly research digest. (Stub — to be implemented with Scout)."""
    # TODO: Connect with Scout pipeline when available
    logger.info("Weekly digest stub called — implement after Scout upgrade")
    pass
