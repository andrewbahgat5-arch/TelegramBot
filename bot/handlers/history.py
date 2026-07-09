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
from bot.handlers.ads import show_placement_ad
from bot.keyboards.history import build_history_keyboard
from core.i18n import Translator
from core.logging import get_logger
from domain.entities.user import UserSnapshot
from domain.enums import AdPlacement
from services.ad_service import AdService
from services.history_service import HistoryPage, HistoryService, ResendKind
from services.notification_service import NotificationService

router = Router(name="history")
_log = get_logger("bot.handlers.history")

HistoryServiceFactory = Callable[[AsyncSession], HistoryService]
AdServiceFactory = Callable[[AsyncSession], AdService]

_PLATFORM_EMOJI: dict[str, str] = {
    "youtube": "▶️",
    "tiktok": "🎵",
    "instagram": "📸",
    "facebook": "📘",
    "twitter": "🐦",
    "x": "🐦",
    "soundcloud": "🎧",
    "pinterest": "📌",
    "snapchat": "👻",
    "reddit": "🔗",
}


def _platform_emoji(platform: str | None) -> str:
    return _PLATFORM_EMOJI.get((platform or "").lower(), "🔗")


@router.message(Command("history"))
async def handle_history(
    message: Message,
    session: AsyncSession,
    user: UserSnapshot,
    history_service_factory: HistoryServiceFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
    ad_service_factory: AdServiceFactory | None = None,
) -> None:
    page = await history_service_factory(session).list_history(user.id, page=0)
    text, keyboard = _render(page, callback_signer, translate, locale)
    await message.answer(text, reply_markup=keyboard)
    if ad_service_factory is not None:  # best-effort history placement (Sprint 9.5)
        await show_placement_ad(ad_service_factory(session), user, AdPlacement.HISTORY.value)


@router.callback_query(F.data.startswith("h|"))
async def handle_history_page(
    callback: CallbackQuery,
    session: AsyncSession,
    user: UserSnapshot,
    history_service_factory: HistoryServiceFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "h" or parsed.arg is None:
        await callback.answer()  # forged/garbled → ignore silently (Section 14.2)
        return
    page = await history_service_factory(session).list_history(user.id, page=parsed.arg)
    text, keyboard = _render(page, callback_signer, translate, locale)
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
    translate: Translator,
    locale: str,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "r" or parsed.arg is None:
        await callback.answer()
        return

    await callback.answer()
    progress_message_id = await notification_service.send_initial(user.telegram_id, locale)
    outcome = await history_service_factory(session).resend(
        download_id=parsed.arg,
        user_id=user.id,
        telegram_id=user.telegram_id,
        progress_message_id=progress_message_id,
        user=user,  # lets the caption-ad layer target this viewer (two-layer ads)
    )
    if outcome is ResendKind.RESENT:
        await notification_service.notify_completed(user.telegram_id, progress_message_id, locale)
    elif outcome is ResendKind.NEEDS_RELINK:
        await notification_service.notify_text(
            user.telegram_id, progress_message_id, translate("history.relink", locale)
        )
    elif outcome is ResendKind.NOT_FOUND:
        await notification_service.notify_text(
            user.telegram_id, progress_message_id, translate("history.not_found", locale)
        )
    # REQUEUED: the worker now owns the progress message (request stashed its id),
    # editing it through the download stages to ✅/❌ — nothing more to do here.


def _render(
    page: HistoryPage, signer: CallbackSigner, translate: Translator, locale: str
) -> tuple[str, InlineKeyboardMarkup | None]:
    if not page.rows:
        return translate("history.empty", locale), None
    keyboard = build_history_keyboard(
        page.rows,
        page=page.page,
        has_prev=page.has_prev,
        has_next=page.has_next,
        signer=signer,
        locale=locale,
    )
    header = translate("history.header", locale, page=page.page + 1)
    lines = [header, ""]
    for index, row in enumerate(page.rows, start=1):
        platform_emoji = _platform_emoji(row.platform)
        title = escape(row.title[:40]) if row.title else escape(row.format)
        lines.append(f"{index}. {platform_emoji} {title} · {escape(row.quality)}")
    return "\n".join(lines), keyboard
