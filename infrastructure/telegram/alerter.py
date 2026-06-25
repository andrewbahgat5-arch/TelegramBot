"""Telegram alerter (MASTER_PLAN Task 10.3, Section 15.6).

Sends operational alerts to the Owner-monitored ``TELEGRAM_ALERTS_CHAT_ID``. The
composition root wires this behind the pure ``TelegramAlertProcessor`` sink in
``core.alerting``; throttling/deduplication live there. A send failure must never
propagate into the logging pipeline (logging an alert failure would recurse), so it
is caught and dropped here.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot

from core.alerting import AlertSink
from core.logging import get_logger

_log = get_logger("infrastructure.telegram.alerter")

# Strong references to in-flight alert sends so the event loop does not garbage-collect
# a pending task before it completes (the alert sink is fire-and-forget).
_background_tasks: set[asyncio.Task[None]] = set()


class TelegramAlerter:
    """Send a text alert to the alerts chat via the bot."""

    def __init__(self, bot: Bot, chat_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        try:
            await self._bot.send_message(self._chat_id, text)
        except Exception as exc:  # alerting must never raise back into the logger
            # Use a non-critical level so a failed alert cannot trigger another alert.
            _log.warning("alert_send_failed", error=str(exc))


def make_alert_sink(alerter: TelegramAlerter) -> AlertSink:
    """Build a sync sink that fires the async alert send on the running loop.

    Called from the (synchronous) structlog processor; if no loop is running (e.g.
    a log emitted at startup/shutdown) the alert is dropped rather than raising.
    """

    def sink(text: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(alerter.send(text))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return sink
