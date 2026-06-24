"""Download handlers (MASTER_PLAN Task 5.9 + 6.8, flow 16.1 steps 1-5).

URL message → format keyboard → quality keyboard → enqueue. The format message
shows the media thumbnail when one is known (Owner carry-in). The final quality
pick sends a progress message and hands off to ``JobService.request`` (Task 6.8),
which either delivers instantly from cache or queues a job whose worker edits the
progress message through its stages.

Per-request services come from factories bound to the update's session, injected as
aiogram workflow data (``analyzer_factory``, ``job_service_factory``,
``notification_service``, ``callback_signer``).
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Callable
from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner
from bot.keyboards.format_select import build_format_keyboard
from bot.keyboards.quality_select import build_quality_keyboard
from core.logging import get_correlation_id, get_logger
from domain.entities.media import MediaInfo
from domain.entities.user import UserSnapshot
from domain.exceptions import ExtractionFailedError, URLNotSupportedError, UserFacingError
from services.job_service import JobService, RequestKind
from services.notification_service import NotificationService
from services.rate_limit_service import RateLimitService
from services.url_analyzer import URLAnalyzerService

router = Router(name="download")
_log = get_logger("bot.handlers.download")

AnalyzerFactory = Callable[[AsyncSession], URLAnalyzerService]
JobServiceFactory = Callable[[AsyncSession], JobService]
RateLimitServiceFactory = Callable[[AsyncSession], RateLimitService]

_DUPLICATE_TEXT = "⏳ This is already being prepared — you'll get it shortly."
_BUSY_TEXT = "⏳ You already have a download in progress. Please wait for it to finish."


def _is_free(user: UserSnapshot) -> bool:
    """A user is on the free plan unless an unexpired premium grant is active (16.5)."""
    expires = user.premium_expires_at
    active_premium = (
        user.is_premium and expires is not None and expires > datetime.datetime.now(datetime.UTC)
    )
    return not active_premium


@router.message(F.text.regexp(r"https?://"))
async def handle_url(
    message: Message,
    session: AsyncSession,
    analyzer_factory: AnalyzerFactory,
    callback_signer: CallbackSigner,
) -> None:
    # Acknowledge instantly so the user never sees the bot as idle while yt-dlp runs.
    ack = await message.answer("🔍 Analyzing link…")
    analyzer = analyzer_factory(session)
    try:
        analyzed = await analyzer.analyze(message.text or "")
    except URLNotSupportedError:
        await ack.edit_text("That link isn't supported. Please try a different one.")
        return
    except ExtractionFailedError:
        await ack.edit_text("Sorry, I couldn't read that link. It may be private or removed.")
        return

    if not analyzed.info.formats:
        await ack.edit_text("No downloadable formats were found for that link.")
        return

    keyboard = build_format_keyboard(analyzed.media_id, analyzed.info, callback_signer)
    caption = _media_caption(analyzed.info)
    thumbnail = analyzed.info.thumbnail_url
    if thumbnail:
        try:
            await message.answer_photo(thumbnail, caption=caption, reply_markup=keyboard)
            await ack.delete()
            return
        except Exception as exc:  # bad/blocked thumbnail URL → fall back to editing the ack
            _log.debug("thumbnail_send_failed", error=str(exc))
    await ack.edit_text(caption, reply_markup=keyboard)


def _media_caption(info: MediaInfo) -> str:
    """Title + duration + source line shown above the format keyboard."""
    lines = [f"🎬 <b>{escape(info.title)}</b>"]
    meta: list[str] = []
    if info.duration:
        meta.append(f"⏱ {_format_duration(info.duration)}")
    if info.platform and info.platform != "*":
        meta.append(f"📺 {info.platform.capitalize()}")
    if meta:
        lines.append("   ".join(meta))
    lines.append("\nChoose a format:")
    return "\n".join(lines)


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


@router.callback_query(F.data.startswith("f|"))
async def handle_format_choice(
    callback: CallbackQuery,
    session: AsyncSession,
    analyzer_factory: AnalyzerFactory,
    callback_signer: CallbackSigner,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "f" or parsed.format is None:
        await callback.answer()  # forged/garbled → ignore silently (Section 14.2)
        return

    analyzed = await analyzer_factory(session).analyze_by_media_id(parsed.media_id)
    if analyzed is None:
        await callback.answer("This link expired — please send it again.", show_alert=True)
        return

    keyboard = build_quality_keyboard(
        parsed.media_id, parsed.format, analyzed.info, callback_signer
    )
    caption = f"🎬 <b>{escape(analyzed.info.title)}</b>\nChoose a quality:"
    await _edit_chooser(callback.message, caption, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("b|"))
async def handle_back(
    callback: CallbackQuery,
    session: AsyncSession,
    analyzer_factory: AnalyzerFactory,
    callback_signer: CallbackSigner,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "b":
        await callback.answer()
        return

    analyzed = await analyzer_factory(session).analyze_by_media_id(parsed.media_id)
    if analyzed is None:
        await callback.answer("This link expired — please send it again.", show_alert=True)
        return

    keyboard = build_format_keyboard(parsed.media_id, analyzed.info, callback_signer)
    await _edit_chooser(callback.message, _media_caption(analyzed.info), keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("q|"))
async def handle_quality_choice(
    callback: CallbackQuery,
    session: AsyncSession,
    user: UserSnapshot,
    analyzer_factory: AnalyzerFactory,
    job_service_factory: JobServiceFactory,
    rate_limit_service_factory: RateLimitServiceFactory,
    notification_service: NotificationService,
    callback_signer: CallbackSigner,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "q" or parsed.format is None or parsed.quality is None:
        await callback.answer()
        return

    analyzed = await analyzer_factory(session).analyze_by_media_id(parsed.media_id)
    if analyzed is None:
        await callback.answer("This link expired — please send it again.", show_alert=True)
        return

    # Enforce the per-user daily limit + cooldown against the authoritative DB row
    # (the cached snapshot's daily count can be stale) before doing any work (16.5).
    try:
        await rate_limit_service_factory(session).authorize_download(user.telegram_id)
    except UserFacingError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await callback.answer()
    progress_message_id = await notification_service.send_initial(user.telegram_id)
    correlation = get_correlation_id()
    outcome = await job_service_factory(session).request(
        user_id=user.id,
        telegram_id=user.telegram_id,
        media_id=parsed.media_id,
        info=analyzed.info,
        format_=parsed.format,
        quality=parsed.quality,
        progress_message_id=progress_message_id,
        correlation_id=uuid.UUID(correlation) if correlation else None,
        single_active=_is_free(user),
    )
    if outcome.kind is RequestKind.DUPLICATE:
        await notification_service.notify_text(
            user.telegram_id, progress_message_id, _DUPLICATE_TEXT
        )
    elif outcome.kind is RequestKind.BUSY:
        await notification_service.notify_text(user.telegram_id, progress_message_id, _BUSY_TEXT)


async def _edit_chooser(message: object, text: str, keyboard: object) -> None:
    """Edit the chooser in place — caption for a photo message, text otherwise."""
    if not isinstance(message, Message):
        return
    if message.photo:
        await message.edit_caption(caption=text, reply_markup=keyboard)  # type: ignore[arg-type]
    else:
        await message.edit_text(text, reply_markup=keyboard)  # type: ignore[arg-type]
