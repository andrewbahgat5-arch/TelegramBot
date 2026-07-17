"""Membership handler — real-time detection of a user blocking/unblocking the bot.

Telegram sends a ``my_chat_member`` update whenever the bot's status in a chat
changes. In a **private** chat that means the user blocked the bot (status → ``kicked``)
or unblocked/restarted it (``kicked`` → ``member``). We record the ``bot_blocked`` flag
and let ``UserService`` fan out the admin notification. Group membership changes are
ignored — this is only about a user's relationship with the bot.

Only ``session`` (from ``DbSessionMiddleware``, applied to every update) and the
``user_service_factory`` are needed; the auth/locale middlewares don't run for
``my_chat_member`` and aren't required here.
"""

from __future__ import annotations

from collections.abc import Callable

from aiogram import Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import ChatMemberUpdated
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from services.user_service import UserService

router = Router(name="membership")
_log = get_logger("bot.handlers.membership")

UserServiceFactory = Callable[[AsyncSession], UserService]

# Statuses that mean "the bot is no longer an active member of this private chat".
_BLOCKED_STATUSES = frozenset({ChatMemberStatus.KICKED, ChatMemberStatus.LEFT})


@router.my_chat_member()
async def handle_my_chat_member(
    event: ChatMemberUpdated,
    session: AsyncSession | None = None,
    user_service_factory: UserServiceFactory | None = None,
) -> None:
    if session is None or user_service_factory is None:
        return
    if event.chat.type != ChatType.PRIVATE:
        return  # only a user's own block/unblock, never group add/remove

    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status
    telegram_id = event.from_user.id
    service = user_service_factory(session)

    if new_status in _BLOCKED_STATUSES and old_status not in _BLOCKED_STATUSES:
        _log.info("my_chat_member_blocked", telegram_id=telegram_id, status=str(new_status))
        await service.record_bot_blocked(telegram_id)
    elif new_status == ChatMemberStatus.MEMBER and old_status in _BLOCKED_STATUSES:
        _log.info("my_chat_member_unblocked", telegram_id=telegram_id)
        await service.record_bot_unblocked(telegram_id)
