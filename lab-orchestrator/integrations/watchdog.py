#!/usr/bin/env python3
"""
Lab Orchestrator — Service Watchdog

독립 프로세스로 실행되어 오케스트레이터 서비스를 모니터링.
서비스가 다운되면 #lab-alerts에 즉시 알림을 보내고,
복구되면 원인 분석 + 정상화 보고를 전송.

launchd로 별도 서비스로 등록하여 사용:
    launchctl load ~/Library/LaunchAgents/kr.ceml.lab-watchdog.plist
"""

import asyncio
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watchdog] %(levelname)s %(message)s",
)
logger = logging.getLogger("watchdog")

# ── Config ──
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
ALERTS_CHANNEL = os.getenv("SLACK_CHANNEL_ALERTS", "#lab-alerts")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_API_URL", "http://localhost:8000")
UI_URL = os.getenv("UI_URL", "http://localhost:3000")

CHECK_INTERVAL = 30          # seconds between checks
STARTUP_DELAY = 15           # wait after own startup before first check
MAX_CONSECUTIVE_FAILS = 2    # alert after N consecutive failures

# Log paths for crash analysis
ORCH_ERROR_LOG = _PROJECT_ROOT / "logs" / "orchestrator.error.log"
SLACK_ERROR_LOG = _PROJECT_ROOT / "logs" / "slack-bot.error.log"
STATE_FILE = _PROJECT_ROOT / "logs" / "watchdog_state.json"

# launchd plist paths
ORCH_PLIST = Path.home() / "Library" / "LaunchAgents" / "kr.ceml.lab-orchestrator.plist"
SLACK_PLIST = Path.home() / "Library" / "LaunchAgents" / "kr.ceml.lab-slack-bot.plist"

# ── State ──
_orch_status: dict[str, bool | float | str] = {
    "healthy": True,
    "down_since": 0.0,
    "consecutive_fails": 0,
    "alerted": False,
    "last_error": "",
}

_slack_bot_status: dict[str, bool | float] = {
    "healthy": True,
    "down_since": 0.0,
    "consecutive_fails": 0,
    "alerted": False,
}


def _save_state():
    """Persist watchdog state to disk."""
    import json
    try:
        state = {
            "orch": {
                "healthy": _orch_status["healthy"],
                "down_since": _orch_status["down_since"],
                "alerted": _orch_status["alerted"],
                "last_error": str(_orch_status.get("last_error", "")),
            },
            "slack_bot": {
                "healthy": _slack_bot_status["healthy"],
                "down_since": _slack_bot_status["down_since"],
                "alerted": _slack_bot_status["alerted"],
            },
            "updated_at": time.time(),
        }
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to save state: {e}")


def _load_state():
    """Load previous watchdog state from disk."""
    import json
    if not STATE_FILE.exists():
        return
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        orch = state.get("orch", {})
        if not orch.get("healthy", True):
            _orch_status["healthy"] = False
            _orch_status["down_since"] = orch.get("down_since", 0.0)
            _orch_status["alerted"] = orch.get("alerted", False)
            _orch_status["last_error"] = orch.get("last_error", "")
            logger.info(f"Restored state: orchestrator was DOWN since {_orch_status['down_since']}")
        bot = state.get("slack_bot", {})
        if not bot.get("healthy", True):
            _slack_bot_status["healthy"] = False
            _slack_bot_status["down_since"] = bot.get("down_since", 0.0)
            _slack_bot_status["alerted"] = bot.get("alerted", False)
            logger.info("Restored state: slack bot was DOWN")
    except Exception as e:
        logger.warning(f"Failed to load state: {e}")


# ── Slack Notification (direct, no dependency on orchestrator) ──
async def _send_alert(text: str) -> bool:
    """Send alert directly via Slack SDK. Does NOT depend on orchestrator."""
    if not SLACK_BOT_TOKEN:
        logger.error("SLACK_BOT_TOKEN not set, cannot send alert")
        return False
    try:
        from slack_sdk.web.async_client import AsyncWebClient
        client = AsyncWebClient(token=SLACK_BOT_TOKEN)
        result = await client.chat_postMessage(
            channel=ALERTS_CHANNEL,
            text=text,
        )
        return result.get("ok", False)
    except Exception as e:
        logger.error(f"Failed to send Slack alert: {e}")
        return False


# ── Health Checks ──
async def _check_orchestrator() -> tuple[bool, str]:
    """Check if orchestrator API is responding."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{ORCHESTRATOR_URL}/health")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ok":
                    return True, ""
            return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


async def _check_slack_bot() -> tuple[bool, str]:
    """Check if Slack bot process is running."""
    try:
        import subprocess
        result = subprocess.run(
            ["/usr/bin/pgrep", "-f", "integrations.slack_bot"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True, ""
        return False, "Process not found"
    except Exception as e:
        return False, str(e)


# ── Crash Analysis ──
def _analyze_crash(log_path: Path, lines_to_read: int = 30) -> str:
    """Read recent log lines to determine crash cause."""
    if not log_path.exists():
        return "로그 파일 없음"
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        recent = text.strip().split("\n")[-lines_to_read:]

        # Known patterns
        patterns = [
            (r"error while attempting to bind.*address already in use",
             "포트 충돌 (Address already in use)"),
            (r"ModuleNotFoundError|ImportError",
             "모듈 임포트 오류"),
            (r"SyntaxError",
             "구문 오류 (SyntaxError)"),
            (r"MemoryError|Cannot allocate memory",
             "메모리 부족"),
            (r"SIGKILL|signal 9|Killed",
             "프로세스 강제 종료 (SIGKILL)"),
            (r"Permission.*denied",
             "권한 오류"),
            (r"ConnectionRefused|Connection refused",
             "의존 서비스 연결 실패"),
            (r"KeyError|AttributeError|TypeError|ValueError",
             "런타임 오류"),
        ]

        recent_text = "\n".join(recent)
        for pattern, desc in patterns:
            if re.search(pattern, recent_text, re.IGNORECASE):
                # Find the matching line for context
                for line in reversed(recent):
                    if re.search(pattern, line, re.IGNORECASE):
                        return f"{desc}\n```{line.strip()[:200]}```"
                return desc

        # If no pattern matched, return last error line
        error_lines = [l for l in recent if "ERROR" in l or "Error" in l]
        if error_lines:
            return f"마지막 에러:\n```{error_lines[-1].strip()[:200]}```"

        return "명확한 에러 패턴 없음 (로그 확인 필요)"
    except Exception as e:
        return f"로그 분석 실패: {e}"


def _format_downtime(seconds: float) -> str:
    """Format downtime duration in Korean."""
    if seconds < 60:
        return f"{int(seconds)}초"
    elif seconds < 3600:
        return f"{int(seconds / 60)}분 {int(seconds % 60)}초"
    else:
        h = int(seconds / 3600)
        m = int((seconds % 3600) / 60)
        return f"{h}시간 {m}분"


# ── Main Loop ──
async def watchdog_loop():
    """Main monitoring loop."""
    KST = timezone(timedelta(hours=9))

    logger.info(f"Watchdog starting (interval={CHECK_INTERVAL}s, startup_delay={STARTUP_DELAY}s)")
    _load_state()
    await asyncio.sleep(STARTUP_DELAY)
    logger.info("Watchdog active — monitoring orchestrator and slack bot")

    while True:
        now = time.time()
        now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

        # ── Check Orchestrator ──
        orch_ok, orch_err = await _check_orchestrator()

        if not orch_ok:
            _orch_status["consecutive_fails"] += 1
            _orch_status["last_error"] = orch_err

            if _orch_status["healthy"]:
                _orch_status["healthy"] = False
                _orch_status["down_since"] = now
                logger.warning(f"Orchestrator DOWN: {orch_err}")

            # Alert after N consecutive failures (avoid false positives from transient issues)
            if (
                _orch_status["consecutive_fails"] >= MAX_CONSECUTIVE_FAILS
                and not _orch_status["alerted"]
            ):
                cause = _analyze_crash(ORCH_ERROR_LOG)
                alert_text = (
                    f"🔴 *오케스트레이터 서비스 다운*\n"
                    f"• 시각: {now_kst}\n"
                    f"• 오류: {orch_err}\n"
                    f"• 원인 분석:\n{cause}\n\n"
                    f"서비스 자동 재시작을 시도합니다."
                )
                await _send_alert(alert_text)
                _orch_status["alerted"] = True
                logger.error(f"Alert sent: Orchestrator down — {orch_err}")

                # Attempt auto-recovery: kill port + restart via launchctl
                await _attempt_recovery()

        else:
            if not _orch_status["healthy"]:
                # ── Recovery detected ──
                downtime = now - _orch_status["down_since"]
                cause = _analyze_crash(ORCH_ERROR_LOG)
                recovery_text = (
                    f"🟢 *오케스트레이터 서비스 복구 완료*\n"
                    f"• 복구 시각: {now_kst}\n"
                    f"• 다운타임: {_format_downtime(downtime)}\n"
                    f"• 원인:\n{cause}\n"
                )
                await _send_alert(recovery_text)
                logger.info(f"Recovery confirmed after {_format_downtime(downtime)}")

            _orch_status["healthy"] = True
            _orch_status["consecutive_fails"] = 0
            _orch_status["alerted"] = False
            _orch_status["last_error"] = ""

        _save_state()

        # ── Check Slack Bot ──
        bot_ok, bot_err = await _check_slack_bot()

        if not bot_ok:
            _slack_bot_status["consecutive_fails"] += 1

            if _slack_bot_status["healthy"]:
                _slack_bot_status["healthy"] = False
                _slack_bot_status["down_since"] = now

            if (
                _slack_bot_status["consecutive_fails"] >= MAX_CONSECUTIVE_FAILS
                and not _slack_bot_status["alerted"]
            ):
                alert_text = (
                    f"🔴 *Slack Bot 프로세스 다운*\n"
                    f"• 시각: {now_kst}\n"
                    f"• 상태: {bot_err}\n"
                    f"• `launchctl kickstart` 로 재시작을 시도합니다."
                )
                await _send_alert(alert_text)
                _slack_bot_status["alerted"] = True
        else:
            if not _slack_bot_status["healthy"]:
                downtime = now - _slack_bot_status["down_since"]
                await _send_alert(
                    f"🟢 *Slack Bot 복구 완료* (다운타임: {_format_downtime(downtime)})"
                )

            _slack_bot_status["healthy"] = True
            _slack_bot_status["consecutive_fails"] = 0
            _slack_bot_status["alerted"] = False

        _save_state()
        await asyncio.sleep(CHECK_INTERVAL)


async def _attempt_recovery():
    """Attempt to recover the orchestrator by killing port conflict and restarting."""
    import subprocess

    logger.info("Attempting auto-recovery...")

    try:
        # 1. Kill any process holding port 8000
        result = subprocess.run(
            ["/usr/sbin/lsof", "-ti:8000"],
            capture_output=True, text=True, timeout=5,
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                try:
                    subprocess.run(["/bin/kill", "-9", pid.strip()], timeout=5)
                    logger.info(f"Killed PID {pid.strip()} on port 8000")
                except Exception:
                    pass
            await asyncio.sleep(2)

        # 2. Restart via launchctl
        uid_result = subprocess.run(
            ["/usr/bin/id", "-u"], capture_output=True, text=True, timeout=5,
        )
        uid = uid_result.stdout.strip()

        subprocess.run(
            ["/bin/launchctl", "kickstart", "-k", f"gui/{uid}/kr.ceml.lab-orchestrator"],
            timeout=10,
            capture_output=True,
        )
        logger.info("Orchestrator restart triggered via launchctl kickstart")

        # Verify it's actually running after a short wait
        await asyncio.sleep(5)
        orch_ok, _ = await _check_orchestrator()
        if not orch_ok:
            # kickstart failed (maybe service was bootout'd) — try bootstrap
            logger.warning("kickstart failed, trying bootstrap...")
            if ORCH_PLIST.exists():
                subprocess.run(
                    ["/bin/launchctl", "bootstrap", f"gui/{uid}", str(ORCH_PLIST)],
                    timeout=10,
                    capture_output=True,
                )
                logger.info("Orchestrator bootstrap attempted")

        # 3. Also restart slack bot
        subprocess.run(
            ["/bin/launchctl", "kickstart", "-k", f"gui/{uid}/kr.ceml.lab-slack-bot"],
            timeout=10,
            capture_output=True,
        )
        logger.info("Slack bot restart triggered via launchctl")

    except Exception as e:
        logger.error(f"Auto-recovery failed: {e}")
        await _send_alert(f"⚠️ 자동 복구 시도 실패: {e}")


if __name__ == "__main__":
    asyncio.run(watchdog_loop())
