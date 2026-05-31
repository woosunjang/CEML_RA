"""
Lab Orchestrator — Report Scheduler

asyncio 기반 스케줄러.
Slack Bot과 함께 구동되며, 리포트를 자동 생성·전송.

채널 구조:
  #lab-report  — 시스템 주간 리포트 (매주 월 09:00 KST)
  #lab-papers  — 논문 데일리 리포트 (매일 09:00 KST)
                  논문 주간 리포트 (매주 월 09:00 KST)
  #lab-project — 프로젝트 주간 리포트 (매주 월 09:00 KST)
  #lab-alerts  — 시스템 알림 (이벤트 발생 시 즉시)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("report_scheduler")

KST = timezone(timedelta(hours=9))


async def _send_report(report_type: str, channel: str):
    """Generate and send a report to Slack."""
    from integrations.slack_notifier import slack_notify

    try:
        if report_type == "system_weekly":
            from integrations.report_generator import generate_weekly_report
            content = await generate_weekly_report()
        elif report_type == "papers_daily":
            from integrations.report_generator import generate_papers_daily
            content = await generate_papers_daily()
        elif report_type == "papers_weekly":
            from integrations.report_generator import generate_papers_weekly
            content = await generate_papers_weekly()
        elif report_type == "project_weekly":
            from integrations.report_generator import generate_project_weekly
            content = await generate_project_weekly()
        else:
            logger.error(f"Unknown report type: {report_type}")
            return

        ok = await slack_notify(channel, content)
        logger.info(f"{report_type} report sent to {channel}: {ok}")
    except Exception as e:
        logger.error(f"Failed to send {report_type} report: {e}")
        # Alert on report generation failure
        try:
            from integrations.slack_notifier import notify_error
            await notify_error(
                "report_scheduler",
                f"{report_type} 리포트 생성/전송 실패",
                str(e),
            )
        except Exception:
            pass  # Never let alert failure propagate


def _next_daily_time() -> datetime:
    """Calculate next 09:00 KST."""
    now = datetime.now(KST)
    target = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return target


def _next_weekly_time() -> datetime:
    """Calculate next Monday 09:00 KST."""
    now = datetime.now(KST)
    days_ahead = (7 - now.weekday()) % 7
    if days_ahead == 0 and now.hour >= 9:
        days_ahead = 7
    target = now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
    return target


async def _papers_daily_loop(channel: str):
    """Run papers daily report on schedule."""
    while True:
        next_run = _next_daily_time()
        wait_sec = (next_run - datetime.now(KST)).total_seconds()
        logger.info(f"Papers daily next run: {next_run.isoformat()} (in {wait_sec:.0f}s)")
        await asyncio.sleep(max(wait_sec, 0))
        await _send_report("papers_daily", channel)


async def _papers_weekly_loop(channel: str):
    """Run papers weekly report on schedule."""
    while True:
        next_run = _next_weekly_time()
        wait_sec = (next_run - datetime.now(KST)).total_seconds()
        logger.info(f"Papers weekly next run: {next_run.isoformat()} (in {wait_sec:.0f}s)")
        await asyncio.sleep(max(wait_sec, 0))
        await _send_report("papers_weekly", channel)


async def _system_weekly_loop(channel: str):
    """Run system weekly report on schedule."""
    while True:
        next_run = _next_weekly_time()
        wait_sec = (next_run - datetime.now(KST)).total_seconds()
        logger.info(f"System weekly next run: {next_run.isoformat()} (in {wait_sec:.0f}s)")
        await asyncio.sleep(max(wait_sec, 0))
        await _send_report("system_weekly", channel)


async def _project_weekly_loop(channel: str):
    """Run project weekly report on schedule."""
    while True:
        next_run = _next_weekly_time()
        wait_sec = (next_run - datetime.now(KST)).total_seconds()
        logger.info(f"Project weekly next run: {next_run.isoformat()} (in {wait_sec:.0f}s)")
        await asyncio.sleep(max(wait_sec, 0))
        await _send_report("project_weekly", channel)


async def _deadline_check_loop(channel: str):
    """Daily deadline check — D-3 이내 마감 리마인더.

    매일 09:05 KST 실행. project_store에서 마감일을 조회하여
    D-3 이하 항목을 #lab-project에 긴급 알림.
    """
    while True:
        now = datetime.now(KST)
        target = now.replace(hour=9, minute=5, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_sec = (target - now).total_seconds()
        logger.info(f"Deadline check next run: {target.isoformat()} (in {wait_sec:.0f}s)")
        await asyncio.sleep(max(wait_sec, 0))

        try:
            from agents.project.project_store import get_all_deadlines
            from integrations.slack_notifier import slack_notify

            deadlines = get_all_deadlines()
            urgent = [
                d for d in deadlines
                if 0 <= d["d_day"] <= 3 and d["status"] != "completed"
            ]
            if urgent:
                lines = ["⏰ *긴급 마감 리마인더*\n"]
                for dl in urgent:
                    if dl["d_day"] == 0:
                        icon = "🔴 *오늘 마감*"
                    elif dl["d_day"] == 1:
                        icon = "🔴 *내일 마감*"
                    else:
                        icon = f"🟠 D-{dl['d_day']}"
                    lines.append(f"  {icon} | {dl['name']} ({dl['project']})")
                await slack_notify(channel, "\n".join(lines))
                logger.info(f"Deadline reminder: {len(urgent)} urgent items")
        except Exception as e:
            logger.error(f"Deadline check failed: {e}")


async def start_scheduler():
    """Start all report scheduler tasks.

    Env vars:
        SLACK_REPORT_CHANNEL   → #lab-report  (시스템 주간)
        SLACK_PAPERS_CHANNEL   → #lab-papers  (논문 데일리 + 주간)
        SLACK_PROJECT_CHANNEL  → #lab-project (프로젝트 주간 + 마감 리마인더)
    """
    import os

    report_ch = os.getenv("SLACK_REPORT_CHANNEL", "")
    papers_ch = os.getenv("SLACK_PAPERS_CHANNEL", "")
    project_ch = os.getenv("SLACK_PROJECT_CHANNEL", "")

    if not report_ch and not papers_ch and not project_ch:
        logger.warning("No report channels set, report scheduler disabled")
        return

    started = []
    if report_ch:
        asyncio.create_task(_system_weekly_loop(report_ch))
        started.append(f"system_weekly→{report_ch}")
    if papers_ch:
        asyncio.create_task(_papers_daily_loop(papers_ch))
        asyncio.create_task(_papers_weekly_loop(papers_ch))
        started.append(f"papers_daily+weekly→{papers_ch}")
    if project_ch:
        asyncio.create_task(_project_weekly_loop(project_ch))
        asyncio.create_task(_deadline_check_loop(project_ch))
        started.append(f"project_weekly+deadline→{project_ch}")

    # Health check — runs on alerts channel
    alerts_ch = os.getenv("SLACK_CHANNEL_ALERTS", "")
    if alerts_ch:
        asyncio.create_task(_health_check_loop(alerts_ch))
        started.append(f"health_check→{alerts_ch}")

    logger.info(f"Report scheduler started: {', '.join(started)}")


# ---------------------------------------------------------------------------
# Health Check — 10분마다 핵심 서비스 상태 확인
# ---------------------------------------------------------------------------

async def _health_check_loop(alerts_channel: str):
    """Periodic health check every 10 minutes.

    Checks:
      1. Qdrant connection
      2. Scout DB accessibility
      3. LLM API availability (cheap model ping)

    Only sends alert when a check FAILS.
    """
    check_interval = 600  # 10 minutes
    # Track previous state to avoid duplicate alerts
    _prev_status: dict[str, bool] = {}

    # Wait 30s after startup before first check
    await asyncio.sleep(30)

    while True:
        checks: dict[str, bool] = {}
        errors: list[str] = []

        # 1. Qdrant
        try:
            from orchestrator.config import QDRANT_URL
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{QDRANT_URL}/healthz")
                checks["qdrant"] = resp.status_code == 200
        except Exception as e:
            checks["qdrant"] = False
            errors.append(f"Qdrant: {e}")

        # 2. Scout DB
        try:
            from orchestrator.config import SCOUT_DB_PATH
            checks["scout_db"] = SCOUT_DB_PATH.exists()
            if not checks["scout_db"]:
                errors.append(f"Scout DB not found: {SCOUT_DB_PATH}")
        except Exception as e:
            checks["scout_db"] = False
            errors.append(f"Scout DB: {e}")

        # 3. LLM API (ping with nano model)
        try:
            from llm.pool import generate_answer
            result = await generate_answer(
                system_prompt="Reply with OK",
                user_prompt="ping",
                model="gpt-4.1-nano",
                temperature=0,
            )
            checks["llm_api"] = len(result) > 0
        except Exception as e:
            checks["llm_api"] = False
            errors.append(f"LLM API: {e}")

        # Send alerts only for newly failed checks
        newly_failed = []
        for name, ok in checks.items():
            was_ok = _prev_status.get(name, True)
            if not ok and was_ok:
                newly_failed.append(name)

        if newly_failed:
            from integrations.slack_notifier import slack_notify
            lines = ["🔴 *서비스 Health Check 실패*\n"]
            for name in newly_failed:
                err = next((e for e in errors if name.replace("_", " ") in e.lower() or name in e.lower()), "")
                lines.append(f"  ❌ `{name}` — {err or '응답 없음'}")
            await slack_notify(alerts_channel, "\n".join(lines))
            logger.warning(f"Health check failed: {newly_failed}")

        # Log recovery
        recovered = [
            name for name, ok in checks.items()
            if ok and not _prev_status.get(name, True)
        ]
        if recovered:
            from integrations.slack_notifier import slack_notify
            await slack_notify(
                alerts_channel,
                f"🟢 *서비스 복구 확인*: {', '.join(f'`{r}`' for r in recovered)}"
            )
            logger.info(f"Health check recovered: {recovered}")

        _prev_status = checks
        await asyncio.sleep(check_interval)


# ---------------------------------------------------------------------------
# One-shot test: 모든 채널에 즉시 테스트 메시지 전송
# ---------------------------------------------------------------------------

async def test_all_channels():
    """모든 리포트 채널에 일회성 테스트 메시지를 즉시 전송.

    - #lab-report  → 시스템 주간 리포트 (실제 생성)
    - #lab-papers  → 논문 데일리 리포트 (실제 생성)
    - #lab-project → 프로젝트 주간 리포트 (실제 생성)
    - #lab-alerts  → 테스트 알림 메시지
    """
    import os
    from integrations.slack_notifier import slack_notify

    report_ch = os.getenv("SLACK_REPORT_CHANNEL", "")
    papers_ch = os.getenv("SLACK_PAPERS_CHANNEL", "")
    project_ch = os.getenv("SLACK_PROJECT_CHANNEL", "")
    alerts_ch = os.getenv("SLACK_CHANNEL_ALERTS", "")

    results = {}
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    # 1. #lab-report — 시스템 주간 리포트
    if report_ch:
        try:
            from integrations.report_generator import generate_weekly_report
            content = await generate_weekly_report()
            ok = await slack_notify(report_ch, content)
            results["system_weekly"] = {"channel": report_ch, "ok": ok}
            logger.info(f"Test: system_weekly → {report_ch}: {ok}")
        except Exception as e:
            results["system_weekly"] = {"channel": report_ch, "error": str(e)}
            logger.error(f"Test: system_weekly failed: {e}")

    # 2. #lab-papers — 논문 데일리 리포트
    if papers_ch:
        try:
            from integrations.report_generator import generate_papers_daily
            content = await generate_papers_daily()
            ok = await slack_notify(papers_ch, content)
            results["papers_daily"] = {"channel": papers_ch, "ok": ok}
            logger.info(f"Test: papers_daily → {papers_ch}: {ok}")
        except Exception as e:
            results["papers_daily"] = {"channel": papers_ch, "error": str(e)}
            logger.error(f"Test: papers_daily failed: {e}")

    # 3. #lab-project — 프로젝트 주간 리포트
    if project_ch:
        try:
            from integrations.report_generator import generate_project_weekly
            content = await generate_project_weekly()
            ok = await slack_notify(project_ch, content)
            results["project_weekly"] = {"channel": project_ch, "ok": ok}
            logger.info(f"Test: project_weekly → {project_ch}: {ok}")
        except Exception as e:
            results["project_weekly"] = {"channel": project_ch, "error": str(e)}
            logger.error(f"Test: project_weekly failed: {e}")

    # 4. #lab-alerts — 테스트 알림 메시지
    if alerts_ch:
        try:
            alert_text = (
                "🔔 *시스템 알림 테스트*\n\n"
                f"이 메시지는 `#lab-alerts` 채널의 연동 테스트입니다.\n"
                f"정상적으로 수신되면 알림 시스템이 올바르게 작동하고 있습니다.\n\n"
                f"*알림 대상 이벤트:*\n"
                f"  • 🚨 에이전트 호출 실패 / timeout\n"
                f"  • 🔴 서비스 장애 (오케스트레이터 / Slack Bot / Qdrant)\n"
                f"  • ⚠️ 파이프라인 실패\n"
                f"  • 📡 Scout 수집 오류 (API 한도 / 소스 접근 불가)\n"
                f"  • 💾 리소스 경고 (DB 용량 / 디스크 부족)\n"
                f"  • 🔑 모델 API 오류 (키 만료 / rate limit)\n"
                f"  • ⏰ 스케줄 리포트 생성 실패\n\n"
                f"_테스트 시각: {now_str}_"
            )
            ok = await slack_notify(alerts_ch, alert_text)
            results["alerts_test"] = {"channel": alerts_ch, "ok": ok}
            logger.info(f"Test: alerts → {alerts_ch}: {ok}")
        except Exception as e:
            results["alerts_test"] = {"channel": alerts_ch, "error": str(e)}
            logger.error(f"Test: alerts failed: {e}")

    return results


# ---------------------------------------------------------------------------
# CLI entry point for testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    asyncio.run(test_all_channels())
