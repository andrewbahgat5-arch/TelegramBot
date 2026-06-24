"""History handlers (MASTER_PLAN Task 7.4, flow 16.3).

``/history`` lists a user's past downloads, newest first, paginated. Each row has a
resend button; tapping it re-sends the file instantly from cache, or — when the cache
is gone — falls back to a fresh download. A prev/next row paginates in place.

No business logic lives here: the handler parses the signed callback, delegates to
``HistoryService``, and formats the outcome (Section 9.1 rule). Per-request services
arrive as aiogram workflow data (``history_service_factory``, ``notification_service``,
``callback_signer``).
"""

from __future__ import annotations

from collections.abc import Callable
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner
from bot.keyboards.history import build_history_keyboard
from core.logging import get_logger
from domain.entities.user import UserSnapshot
from services.history_service import HistoryPage, HistoryService, ResendKind
from services.notification_service import NotificationService

router = Router(name="history")
_log = get_logger("bot.handlers.history")

HistoryServiceFactory = Callable[[AsyncSession], HistoryService]

_EMPTY_TEXT = "🗂 You have no downloads yet. Send me a link to get started!"
_RELINK_TEXT = "This file is no longer available — please send the link again."
_NOT_FOUND_TEXT = "That item is no longer in your history."


@router.message(Command("history"))
async def handle_history(
    message: Message,
    session: AsyncSession,
    user: UserSnapshot,
    history_service_factory: HistoryServiceFactory,
    callback_signer: CallbackSigner,
) -> None:
    page = await history_service_factory(session).list_history(user.id, page=0)
    text, keyboard = _render(page, callback_signer)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("h|"))
async def handle_history_page(
    callback: CallbackQuery,
    session: AsyncSession,
    user: UserSnapshot,
    history_service_factory: HistoryServiceFactory,
    callback_signer: CallbackSigner,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "h" or parsed.arg is None:
        await callback.answer()  # forged/garbled → ignore silently (Section 14.2)
        return
    page = await history_service_factory(session).list_history(user.id, page=parsed.arg)
    text, keyboard = _render(page, callback_signer)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("r|"))
async def handle_resend(
    callback: CallbackQuery,
    session: AsyncSession,
    user: UserSnapshot,
    history_service_factory: HistoryServiceFactory,
    notification_service: NotificationService,
    callback_signer: CallbackSigner,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "r" or parsed.arg is None:
        await callback.answer()
        return

    await callback.answer()
    progress_message_id = await notification_service.send_initial(user.telegram_id)
    outcome = await history_service_factory(session).resend(
        download_id=parsed.arg,
        user_id=user.id,
        telegram_id=user.telegram_id,
        progress_message_id=progress_message_id,
    )
    if outcome is ResendKind.RESENT:
        await notification_service.notify_completed(user.telegram_id, progress_message_id)
    elif outcome is ResendKind.NEEDS_RELINK:
        await notification_service.notify_text(user.telegram_id, progress_message_id, _RELINK_TEXT)
    elif outcome is ResendKind.NOT_FOUND:
        await notification_service.notify_text(
            user.telegram_id, progress_message_id, _NOT_FOUND_TEXT
        )
    # REQUEUED: the worker now owns the progress message (request stashed its id),
    # editing it through the download stages to ✅/❌ — nothing more to do here.


def _render(page: HistoryPage, signer: CallbackSigner) -> tuple[str, InlineKeyboardMarkup | None]:
    if not page.rows:
        return _EMPTY_TEXT, None
    keyboard = build_history_keyboard(
        page.rows,
        page=page.page,
        has_prev=page.has_prev,
        has_next=page.has_next,
        signer=signer,
    )
    header = f"🗂 <b>Your downloads</b> (page {page.page + 1})\nTap an entry to resend it."
    lines = [header, ""]
    for index, row in enumerate(page.rows, start=1):
        platform = escape((row.platform or "link").capitalize())
        lines.append(f"{index}. {platform} · {escape(row.quality)} · {escape(row.format)}")
    return "\n".join(lines), keyboard
