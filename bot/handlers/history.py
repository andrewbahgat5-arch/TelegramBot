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
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, LinkPreviewOptions, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner
from bot.callbacks.paging import decode_filter_page
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

# The list's clickable titles are links; without this Telegram renders a big link
# preview (thumbnail/player) for the first one under the message. Suppress it.
_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

HistoryServiceFactory = Callable[[AsyncSession], HistoryService]
AdServiceFactory = Callable[[AsyncSession], AdService]

_FILTER_LABELS = {0: None, 1: "audio", 2: "video"}
_FILTER_INDEX = {v: k for k, v in _FILTER_LABELS.items()}


def _badge(n: int) -> str:
    """Plain numeric label for a history row, e.g. ``1.`` (no keycap emoji)."""
    return f"{n}."


def _format_duration(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def _humanize_size(size_bytes: int) -> str:
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


@router.message(Command("history"))
async def handle_history(
    message: Message,
    session: AsyncSession,
    user: UserSnapshot,
    history_service_factory: HistoryServiceFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    svc = history_service_factory(session)
    page = await svc.list_history(user.id, page=0)
    text, keyboard = _render(page, callback_signer, translate, locale)
    await message.answer(text, reply_markup=keyboard, link_preview_options=_NO_PREVIEW)


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
        await callback.answer()
        return
    filter_index, page_num = decode_filter_page(parsed.arg)
    format_filter = _FILTER_LABELS.get(filter_index)
    svc = history_service_factory(session)
    page = await svc.list_history(user.id, page=page_num, format_filter=format_filter)
    text, keyboard = _render(page, callback_signer, translate, locale)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text, reply_markup=keyboard, link_preview_options=_NO_PREVIEW
        )
    await callback.answer()


@router.callback_query(F.data.startswith("hx|"))
async def handle_history_close(
    callback: CallbackQuery,
    callback_signer: CallbackSigner,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "hx":
        await callback.answer()
        return
    if isinstance(callback.message, Message):
        try:
            await callback.message.delete()
        except Exception:  # noqa: S110
            pass
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
    ad_service_factory: AdServiceFactory | None = None,
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
        user=user,
    )
    if outcome is ResendKind.RESENT:
        await notification_service.notify_completed(user.telegram_id, progress_message_id, locale)
        if ad_service_factory is not None:
            await show_placement_ad(ad_service_factory(session), user, AdPlacement.HISTORY.value)
    elif outcome is ResendKind.NEEDS_RELINK:
        await notification_service.notify_text(
            user.telegram_id, progress_message_id, translate("history.relink", locale)
        )
    elif outcome is ResendKind.NOT_FOUND:
        await notification_service.notify_text(
            user.telegram_id, progress_message_id, translate("history.not_found", locale)
        )


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
        format_filter=page.format_filter,
        audio_count=page.audio_count,
        video_count=page.video_count,
    )
    header = translate("history.header", locale, page=page.page + 1)
    subtitle = translate("history.subtitle", locale)
    lines = [header, subtitle, ""]
    for index, row in enumerate(page.rows, start=1):
        title_text = escape(row.title[:40]) if row.title else escape(row.format)
        # Clickable title → original source (item #8). Only http(s) to avoid unsafe
        # schemes; href is attribute-escaped. Old rows (no source_url) render as plain text.
        source_url = getattr(row, "source_url", None)
        title = (
            f'<a href="{escape(source_url, quote=True)}">{title_text}</a>'
            if source_url and source_url.startswith(("http://", "https://"))
            else title_text
        )
        lines.append(f"{_badge(index)} {title}")
        # Detail line is plain text — no time/format/source emoji (Owner request).
        detail_parts: list[str] = []
        duration = getattr(row, "duration_seconds", None)
        if duration is not None:
            detail_parts.append(_format_duration(duration))
        size = getattr(row, "size_bytes", None) or getattr(row, "file_size", None)
        if size is not None:
            detail_parts.append(_humanize_size(size))
        detail_parts.append(escape(row.format))
        detail_parts.append(escape(row.quality))
        detail_parts.append(escape(row.platform or "unknown").capitalize())
        lines.append(f"   {'  ·  '.join(detail_parts)}")
    lines.append("")
    lines.append(f"💡 {translate('history.tip', locale)}")
    return "\n".join(lines), keyboard
