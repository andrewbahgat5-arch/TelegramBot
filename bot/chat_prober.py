"""AiogramChatProber — Telegram-side status probe for the health checker (Sprint 13.5).

Implements ``services.user_health.ChatProber`` over ``Bot.get_chat``. Lives in the bot
layer (not ``infrastructure``) because it maps aiogram exceptions to the framework-free
:class:`ProbeOutcome`; keeping it here preserves the "services never import aiogram"
and "infrastructure is a leaf" import-linter contracts.

Mapping (best-effort — Telegram's signals are not exhaustive):

* ``TelegramForbiddenError`` (bot was blocked / kicked) → ``BLOCKED``
* ``TelegramBadRequest`` mentioning "not found" / "deactivated" → ``DELETED``
* any other API error (rate limit, transient) → ``ERROR`` (left unmarked, retried next sweep)
* success → ``ACTIVE``
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from services.user_health import ProbeOutcome

_DELETED_MARKERS = ("not found", "deactivated", "user is deactivated")


class AiogramChatProber:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def probe(self, telegram_id: int) -> ProbeOutcome:
        try:
            await self._bot.get_chat(telegram_id)
        except TelegramForbiddenError:
            return ProbeOutcome.BLOCKED
        except TelegramBadRequest as exc:
            message = str(exc).lower()
            if any(marker in message for marker in _DELETED_MARKERS):
                return ProbeOutcome.DELETED
            return ProbeOutcome.ERROR
        except Exception:  # any other API/transport error is retried on the next sweep
            return ProbeOutcome.ERROR
        return ProbeOutcome.ACTIVE
