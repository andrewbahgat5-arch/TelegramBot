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
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner
from bot.handlers.ads import show_placement_ad
from bot.keyboards.format_select import append_ad_buttons, build_format_keyboard
from bot.keyboards.quality_select import build_quality_keyboard
from core.i18n import Translator
from core.logging import get_correlation_id, get_logger
from domain.entities.media import MediaInfo
from domain.entities.user import UserSnapshot
from domain.enums import UNLIMITED_ROLES, AdPlacement, MediaFormat, Quality
from domain.exceptions import (
    ExtractionFailedError,
    InfrastructureError,
    URLNotSupportedError,
    UserFacingError,
)
from domain.protocols.downloader import ProviderRetryElsewhere
from services.ad_service import AdService
from services.caption_ad_mixer import CaptionAdMixer
from services.job_service import JobService, RequestKind
from services.notification_service import NotificationService
from services.rate_limit_service import RateLimitService
from services.url_analyzer import URLAnalyzerService
from services.user_preference_service import UserPreferenceService

router = Router(name="download")
_log = get_logger("bot.handlers.download")

AnalyzerFactory = Callable[[AsyncSession], URLAnalyzerService]
JobServiceFactory = Callable[[AsyncSession], JobService]
RateLimitServiceFactory = Callable[[AsyncSession], RateLimitService]
AdServiceFactory = Callable[[AsyncSession], AdService]
PreferenceServiceFactory = Callable[[AsyncSession], UserPreferenceService]

# "Small file" ceiling for the auto-download preference (item #10): a single-format
# link at or under this size is fetched without the picker; larger files still ask.
_AUTO_DOWNLOAD_MAX_BYTES = 20 * 1024 * 1024  # 20 MiB


def _is_free(user: UserSnapshot) -> bool:
    """A user is on the free plan unless an unexpired premium grant is active (16.5)."""
    expires = user.premium_expires_at
    active_premium = (
        user.is_premium and expires is not None and expires > datetime.datetime.now(datetime.UTC)
    )
    return not active_premium


def _subject_to_free_cap(user: UserSnapshot) -> bool:
    """Whether the free single-active-download cap applies (#16). Owner is exempt (#21)."""
    return _is_free(user) and user.role not in UNLIMITED_ROLES


@router.message(F.text.regexp(r"https?://"))
async def handle_url(
    message: Message,
    session: AsyncSession,
    user: UserSnapshot,
    analyzer_factory: AnalyzerFactory,
    ad_service_factory: AdServiceFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
    preference_service_factory: PreferenceServiceFactory | None = None,
    job_service_factory: JobServiceFactory | None = None,
    rate_limit_service_factory: RateLimitServiceFactory | None = None,
    notification_service: NotificationService | None = None,
) -> None:
    # Acknowledge instantly so the user never sees the bot as idle while yt-dlp runs.
    ack = await message.answer(translate("download.analyzing", locale))
    analyzer = analyzer_factory(session)
    try:
        analyzed = await analyzer.analyze(message.text or "")
    except URLNotSupportedError:
        await ack.edit_text(translate("errors.url_not_supported", locale))
        return
    except (ProviderRetryElsewhere, InfrastructureError) as exc:
        # A transient failure that survived the provider's own retries (rate-limit, anti-bot
        # throttle, a flaky fetch, the binary momentarily unavailable). Tell the user it's
        # temporary and to try again — never the misleading "private or removed" (#12).
        _log.warning("analyze_transient_failure", error=str(exc))
        await ack.edit_text(translate("download.temporary_error", locale))
        return
    except ExtractionFailedError:
        await ack.edit_text(translate("download.extraction_failed", locale))
        return

    if not analyzed.info.formats:
        await ack.edit_text(translate("download.no_formats", locale))
        return

    # Auto-download (item #10): if the user opted in and this is a single small format,
    # skip the picker and fetch it straight away (large/multi-format links still ask).
    if (
        job_service_factory is not None
        and rate_limit_service_factory is not None
        and notification_service is not None
    ):
        # Images have no format/quality to choose — always deliver straight away, no
        # picker, regardless of the auto-download-small preference. Other single small
        # formats still honour the user's opt-in.
        auto: tuple[MediaFormat, Quality] | None = None
        if _is_single_image(analyzed.info):
            auto = (MediaFormat.IMAGE, Quality.IMAGE)
        elif preference_service_factory is not None:
            prefs = await preference_service_factory(session).get(user.id)
            if prefs.auto_download_small:
                auto = _single_small_format(analyzed.info)
        if auto is not None:
            try:
                await rate_limit_service_factory(session).authorize_download(user.telegram_id)
            except UserFacingError as exc:
                await ack.edit_text(translate(exc.translation_key, locale))
                return
            await ack.delete()
            await _auto_download(
                session,
                user,
                analyzed,
                auto[0],
                auto[1],
                job_service_factory,
                ad_service_factory,
                notification_service,
                translate,
                locale,
            )
            return

    keyboard = build_format_keyboard(analyzed.media_id, analyzed.info, callback_signer, locale)
    caption = _media_caption(analyzed.info, translate, locale)
    # Caption-layer ad (two-layer ads): append the ad text under "Choose a format" + its CTA
    # button, using the same selector as delivered-media captions. Best-effort.
    mixer = CaptionAdMixer(ad_service_factory(session))
    decorated, ad_buttons = await mixer.decorate_for_user(user, caption, user.total_downloads)
    caption = decorated or caption
    keyboard = append_ad_buttons(keyboard, ad_buttons)
    thumbnail = analyzed.info.thumbnail_url
    if thumbnail:
        try:
            await message.answer_photo(thumbnail, caption=caption, reply_markup=keyboard)
            await ack.delete()
            await show_placement_ad(
                ad_service_factory(session), user, AdPlacement.ANALYSIS.value
            )
            return
        except Exception as exc:  # bad/blocked thumbnail URL → fall back to editing the ack
            _log.debug("thumbnail_send_failed", error=str(exc))
    await ack.edit_text(caption, reply_markup=keyboard)
    await show_placement_ad(ad_service_factory(session), user, AdPlacement.ANALYSIS.value)


def _single_small_format(info: MediaInfo) -> tuple[MediaFormat, Quality] | None:
    """The one small format to auto-fetch (item #10), or None when the picker should show:
    only a single available format whose size is known and at or under the ceiling."""
    if len(info.formats) != 1:
        return None
    option = info.formats[0]
    size = option.approx_size_bytes
    if size is None or size > _AUTO_DOWNLOAD_MAX_BYTES:
        return None
    return option.format, option.quality


def _is_single_image(info: MediaInfo) -> bool:
    """A source whose only option is a still image (Pinterest image pin, etc.).

    These skip the format picker entirely and download straight away (no tiers to
    choose), regardless of the auto-download-small preference."""
    return len(info.formats) == 1 and info.formats[0].format is MediaFormat.IMAGE


async def _auto_download(
    session: AsyncSession,
    user: UserSnapshot,
    analyzed: Any,
    format_: MediaFormat,
    quality: Quality,
    job_service_factory: JobServiceFactory,
    ad_service_factory: AdServiceFactory,
    notification_service: NotificationService,
    translate: Translator,
    locale: str,
) -> None:
    """Enqueue the auto-picked format directly — mirrors handle_quality_choice's core
    (progress message → JobService.request → dedup notices → placement ad) so an
    auto-download and a manual pick behave identically past the picker."""
    progress_message_id = await notification_service.send_initial(user.telegram_id, locale)
    correlation = get_correlation_id()
    outcome = await job_service_factory(session).request(
        user_id=user.id,
        telegram_id=user.telegram_id,
        media_id=analyzed.media_id,
        info=analyzed.info,
        format_=format_,
        quality=quality,
        progress_message_id=progress_message_id,
        correlation_id=uuid.UUID(correlation) if correlation else None,
        single_active=_subject_to_free_cap(user),
    )
    if outcome.kind is RequestKind.DUPLICATE:
        await notification_service.notify_text(
            user.telegram_id, progress_message_id, translate("download.duplicate", locale)
        )
    elif outcome.kind is RequestKind.BUSY:
        await notification_service.notify_text(
            user.telegram_id, progress_message_id, translate("download.busy", locale)
        )
    await show_placement_ad(ad_service_factory(session), user, AdPlacement.QUALITY_SELECT.value)


def _build_caption(info: MediaInfo, footer: str) -> str:
    """Title + duration + source + media details (description/views/likes) + footer.

    ``info.title``/``info.platform`` are user/platform-generated content and are
    interpolated verbatim, never translated (Sprint 11.5 requirement #3). Media
    details come from the raw yt-dlp metadata (``info.raw``) and are best-effort —
    most providers omit some or all of these fields.
    """
    lines = [f"🎬 <b>{escape(info.title)}</b>"]
    meta: list[str] = []
    if info.duration:
        meta.append(f"⏱ {_format_duration(info.duration)}")
    if info.platform and info.platform != "*":
        meta.append(f"📺 {info.platform.capitalize()}")
    if meta:
        lines.append("   ".join(meta))
    description = (info.raw.get("description") or "")[:100]
    if description:
        truncated = "…" if len(info.raw.get("description", "")) > 100 else ""
        lines.append(f"\n📝 {escape(description)}{truncated}")
    details: list[str] = []
    view_count = info.raw.get("view_count")
    like_count = info.raw.get("like_count")
    dislike_count = info.raw.get("dislike_count")
    if view_count is not None:
        details.append(f"👁 {_fmt_count(view_count)}")
    if like_count is not None:
        details.append(f"👍 {_fmt_count(like_count)}")
    if dislike_count is not None:
        details.append(f"👎 {_fmt_count(dislike_count)}")
    if details:
        lines.append("   ".join(details))
    lines.append(f"\n{footer}")
    return "\n".join(lines)


def _media_caption(info: MediaInfo, translate: Translator, locale: str) -> str:
    """Caption shown above the format keyboard (choose format)."""
    return _build_caption(info, translate("download.choose_format", locale))


def _quality_caption(info: MediaInfo, translate: Translator, locale: str) -> str:
    """Caption shown above the quality keyboard (choose quality)."""
    return _build_caption(info, translate("download.choose_quality", locale))


def _fmt_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


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
    user: UserSnapshot,
    analyzer_factory: AnalyzerFactory,
    ad_service_factory: AdServiceFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "f" or parsed.format is None:
        await callback.answer()  # forged/garbled → ignore silently (Section 14.2)
        return

    analyzed = await analyzer_factory(session).analyze_by_media_id(parsed.media_id)
    if analyzed is None:
        await callback.answer(translate("download.link_expired", locale), show_alert=True)
        return

    keyboard = build_quality_keyboard(
        parsed.media_id, parsed.format, analyzed.info, callback_signer, locale
    )
    caption = _quality_caption(analyzed.info, translate, locale)
    # Re-decorate with the caption-layer ad (two-layer ads) so it survives the
    # format → quality step instead of disappearing on the first tap.
    mixer = CaptionAdMixer(ad_service_factory(session))
    decorated, ad_buttons = await mixer.decorate_for_user(user, caption, user.total_downloads)
    caption = decorated or caption
    keyboard = append_ad_buttons(keyboard, ad_buttons)
    await _edit_chooser(callback.message, caption, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("b|"))
async def handle_back(
    callback: CallbackQuery,
    session: AsyncSession,
    user: UserSnapshot,
    analyzer_factory: AnalyzerFactory,
    ad_service_factory: AdServiceFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "b":
        await callback.answer()
        return

    analyzed = await analyzer_factory(session).analyze_by_media_id(parsed.media_id)
    if analyzed is None:
        await callback.answer(translate("download.link_expired", locale), show_alert=True)
        return

    keyboard = build_format_keyboard(parsed.media_id, analyzed.info, callback_signer, locale)
    caption = _media_caption(analyzed.info, translate, locale)
    # Re-decorate with the caption-layer ad (two-layer ads) so it survives the
    # back-navigation step instead of disappearing.
    mixer = CaptionAdMixer(ad_service_factory(session))
    decorated, ad_buttons = await mixer.decorate_for_user(user, caption, user.total_downloads)
    caption = decorated or caption
    keyboard = append_ad_buttons(keyboard, ad_buttons)
    await _edit_chooser(callback.message, caption, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("q|"))
async def handle_quality_choice(
    callback: CallbackQuery,
    session: AsyncSession,
    user: UserSnapshot,
    analyzer_factory: AnalyzerFactory,
    job_service_factory: JobServiceFactory,
    rate_limit_service_factory: RateLimitServiceFactory,
    ad_service_factory: AdServiceFactory,
    notification_service: NotificationService,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "q" or parsed.format is None or parsed.quality is None:
        await callback.answer()
        return

    analyzed = await analyzer_factory(session).analyze_by_media_id(parsed.media_id)
    if analyzed is None:
        await callback.answer(translate("download.link_expired", locale), show_alert=True)
        return

    # Enforce the per-user daily limit + cooldown against the authoritative DB row
    # (the cached snapshot's daily count can be stale) before doing any work (16.5).
    try:
        await rate_limit_service_factory(session).authorize_download(user.telegram_id)
    except UserFacingError as exc:
        await callback.answer(translate(exc.translation_key, locale), show_alert=True)
        return

    await callback.answer()
    progress_message_id = await notification_service.send_initial(user.telegram_id, locale)
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
        single_active=_subject_to_free_cap(user),
    )
    if outcome.kind is RequestKind.DUPLICATE:
        await notification_service.notify_text(
            user.telegram_id, progress_message_id, translate("download.duplicate", locale)
        )
    elif outcome.kind is RequestKind.BUSY:
        await notification_service.notify_text(
            user.telegram_id, progress_message_id, translate("download.busy", locale)
        )
    await show_placement_ad(
        ad_service_factory(session), user, AdPlacement.QUALITY_SELECT.value
    )


async def _edit_chooser(message: object, text: str, keyboard: object) -> None:
    """Edit the chooser in place — caption for a photo message, text otherwise."""
    if not isinstance(message, Message):
        return
    if message.photo:
        await message.edit_caption(caption=text, reply_markup=keyboard)  # type: ignore[arg-type]
    else:
        await message.edit_text(text, reply_markup=keyboard)  # type: ignore[arg-type]
