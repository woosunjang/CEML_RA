"""
lab-paper-scout: Slack notifier
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Sends notifications to Slack via Incoming Webhook."""

    def __init__(self, webhook_url: Optional[str]):
        self.webhook_url = webhook_url
        self.enabled = bool(webhook_url)

    def send(self, text: str) -> bool:
        if not self.enabled:
            logger.debug("Slack not configured, skipping notification.")
            return False

        try:
            resp = requests.post(
                self.webhook_url,
                json={"text": text},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("Slack notification sent successfully.")
                return True
            else:
                logger.error(f"Slack error: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            return False
