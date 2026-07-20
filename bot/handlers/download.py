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
import hashlib
import uuid
from collections.abc import Callable
from html import escape
from typing import Any
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InputMediaPhoto, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner
from bot.handlers.ads import show_placement_ad
from bot.keyboards.format_select import append_ad_buttons, build_format_keyboard
from bot.keyboards.gallery import (
    browse_caption,
    build_browse_keyboard,
    build_item_keyboard,
    item_back_callback,
    item_caption,
)
from bot.keyboards.quality_select import build_quality_keyboard
from core.alerting import BurstDetector
from core.error_report import ErrorReport, RequestContext, Severity, UserContext
from core.i18n import Translator
from core.logging import get_correlation_id, get_logger
from core.urls import detect_platform
from domain.entities.media import AUDIO_TARGET_BY_QUALITY, MediaFormatOption, MediaInfo
from domain.entities.user import UserSnapshot
from domain.enums import UNLIMITED_ROLES, AdPlacement, MediaFormat, Quality
from domain.exceptions import (
    AuthRequiredError,
    ExtractionFailedError,
    InfrastructureError,
    NoDownloadableMediaError,
    URLNotSupportedError,
    UserFacingError,
)
from domain.protocols.downloader import ProviderRetryElsewhere
from services.ad_service import AdService
from services.caption_ad_mixer import CaptionAdMixer
from services.error_log_service import ErrorLogService
from services.error_report_service import ErrorReportService
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
ErrorLogServiceFactory = Callable[[AsyncSession], ErrorLogService]


async def _record_report(
    reporter: ErrorReportService | None,
    error_log_factory: ErrorLogServiceFactory | None,
    session: AsyncSession,
    *,
    severity: Severity,
    kind: str,
    message_text: str,
    user: UserSnapshot,
    tg_message: Message,
    url: str,
    exc: BaseException,
) -> None:
    """Classify once, then let the routing policy decide the destination.

    The report is built here and handed to BOTH sinks: the reporter (which pushes only
    CRITICAL) and error_logs (which stores every field the dashboard filters on). One
    classification, two destinations — no per-call decision about where things go.
    """
    if reporter is None:
        return
    report = ErrorReport(
        severity=severity,
        kind=kind,
        exc_type=type(exc).__name__,
        message=message_text,
        correlation_id=get_correlation_id(),
        user=_report_user(user, tg_message, "send_url"),
        request=RequestContext(url=url, platform=detect_platform(url), stage="analyze"),
    )
    persist = None
    if error_log_factory is not None:
        service = error_log_factory(session)
        fields = _url_log_fields(url)
        ctx = f"analyze {fields['platform']} {fields['url_host']} {fields['url_hash']}"

        async def persist(e: BaseException, _kind: str) -> None:
            await service.record_failure(
                e,
                context=ctx,
                user_id=user.id,
                correlation_id=get_correlation_id(),
                report=report,
            )

    await reporter.deliver(report, persist=persist, exc=exc)


def _report_user(user: UserSnapshot, message: Message, action: str) -> UserContext:
    """Owner-report identity for the user who triggered a failure."""
    tg = message.from_user
    return UserContext(
        telegram_id=user.telegram_id,
        username=tg.username if tg else None,
        first_name=tg.first_name if tg else None,
        last_name=tg.last_name if tg else None,
        chat_id=message.chat.id if message.chat else None,
        chat_type=message.chat.type if message.chat else None,
        language=tg.language_code if tg else None,
        is_premium=user.is_premium,
        plan='premium' if user.is_premium else 'free',
        action=action,
    )

# One CRITICAL "analysis failures are bursting" alert (→ the Telegram alerts chat via
# TelegramAlertProcessor) when this many analyses fail within the window. Isolated
# failures stay log-only; a burst means the pipeline (proxy, yt-dlp, a platform) broke.
_BURST_THRESHOLD = 5
_BURST_WINDOW_SECONDS = 600.0
_analyze_failure_burst = BurstDetector(_BURST_THRESHOLD, _BURST_WINDOW_SECONDS)
# Outcomes attributable to the LINK, not to us: a login wall, a post with nothing in it,
# an unsupported site. They are recorded in error_logs but never count toward the burst
# alert, which is a signal that the pipeline itself is broken.
_EXPECTED_USER_ERRORS = (
    AuthRequiredError,
    NoDownloadableMediaError,
    URLNotSupportedError,
)

# "Small file" ceiling for the auto-download preference (item #10): a single-format
# link at or under this size is fetched without the picker; larger files still ask.
_AUTO_DOWNLOAD_MAX_BYTES = 20 * 1024 * 1024  # 20 MiB


def _url_log_fields(url: str) -> dict[str, str]:
    """Diagnostic fields for analysis-failure logs: platform + host + a short stable
    hash of the URL (never the URL itself — hosts are diagnostic, full URLs are
    user content and stay out of the logs). The hash lets repeated failures for the
    same link be correlated across users and time."""
    host = urlparse(url.strip()).netloc.lower()
    digest = hashlib.sha256(url.strip().encode()).hexdigest()[:12]
    return {"platform": detect_platform(url), "url_host": host, "url_hash": digest}


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
    error_log_service_factory: ErrorLogServiceFactory | None = None,
    error_report_service: ErrorReportService | None = None,
) -> None:
    # Acknowledge instantly so the user never sees the bot as idle while yt-dlp runs.
    url = message.text or ""
    ack = await message.answer(translate("download.analyzing", locale))
    _log.info("download_requested", user_id=user.telegram_id, **_url_log_fields(url))
    analyzer = analyzer_factory(session)

    async def record_failure(exc: BaseException, *, with_traceback: bool = False) -> None:
        # Persist into error_logs (queryable long after docker logs rotate) + fire ONE
        # CRITICAL burst alert when analyses are failing in bulk (pipeline-level outage).
        fields = _url_log_fields(url)
        if error_log_service_factory is not None:
            context = f"analyze {fields['platform']} {fields['url_host']} {fields['url_hash']}"
            await error_log_service_factory(session).record_failure(
                exc,
                context=context,
                user_id=user.id,
                correlation_id=get_correlation_id(),
                with_traceback=with_traceback,
            )
        # The burst alert exists to catch a pipeline-level OUTAGE, so it must only count
        # failures that implicate us. A login-walled or empty post is the link doing
        # exactly what it should — and now that auth walls are classified (rather than
        # buried in generic extraction failures), a handful of users pasting private
        # Instagram links in one window would otherwise page the Owner with a CRITICAL
        # for a perfectly healthy bot. Still persisted to error_logs either way.
        if isinstance(exc, _EXPECTED_USER_ERRORS):
            return
        if _analyze_failure_burst.record():
            _log.critical(
                "analyze_failure_burst",
                failures=_BURST_THRESHOLD,
                window_seconds=int(_BURST_WINDOW_SECONDS),
                error=str(exc),
                **fields,
            )

    try:
        analyzed = await analyzer.analyze(url)
    except URLNotSupportedError as exc:
        _log.info("analyze_unsupported_url", **_url_log_fields(url))
        # INFO: the bot behaved correctly, so this is a Logs row, not a Telegram push
        # (DESIGN_MONITORING.md). It is recorded with the FULL url because an
        # unsupported site today is a candidate for support tomorrow, and that call
        # cannot be made from a hash.
        await _record_report(
            error_report_service,
            error_log_service_factory,
            session,
            severity=Severity.INFO,
            kind="unsupported_url",
            message_text=str(exc) or "This link is not supported.",
            user=user,
            tg_message=message,
            url=url,
            exc=exc,
        )
        await ack.edit_text(translate("errors.url_not_supported", locale))
        return
    except UserFacingError as exc:
        # The site refuses this specific item (e.g. YouTube's per-video bot-check wall) —
        # an honest, actionable message beats "busy, try again" for something a retry
        # cannot fix. The catalog key comes from the domain error type.
        _log.warning("analyze_rejected", error=str(exc), **_url_log_fields(url))
        await record_failure(exc)
        await ack.edit_text(translate(exc.translation_key, locale))
        return
    except (ProviderRetryElsewhere, InfrastructureError) as exc:
        # A transient failure that survived the provider's own retries (rate-limit, anti-bot
        # throttle, a flaky fetch, the binary momentarily unavailable). Tell the user it's
        # temporary and to try again — never the misleading "private or removed" (#12).
        _log.warning("analyze_transient_failure", error=str(exc), **_url_log_fields(url))
        await record_failure(exc)
        await ack.edit_text(translate("download.temporary_error", locale))
        return
    except ExtractionFailedError as exc:
        _log.warning("analyze_extraction_failed", error=str(exc), **_url_log_fields(url))
        await record_failure(exc)
        await _record_report(
            error_report_service,
            error_log_service_factory,
            session,
            severity=Severity.ERROR,
            kind="extraction_failed",
            message_text=str(exc),
            user=user,
            tg_message=message,
            url=url,
            exc=exc,
        )
        await ack.edit_text(translate("download.extraction_failed", locale))
        return
    except Exception as exc:
        # Last-resort guard: an unexpected bug must never strand the user on a frozen
        # "Analyzing…" message. Log the traceback, tell the user it's on our side.
        _log.exception("analyze_unexpected_error", **_url_log_fields(url))
        await record_failure(exc, with_traceback=True)
        try:
            await ack.edit_text(translate("errors.unexpected", locale))
        except Exception:  # noqa: S110 - the ack may have been deleted; nothing to do
            pass
        return

    # A multi-item post (Instagram carousel) resolves to an item list rather than
    # formats — the media lives in the slides. Offer the slides first; picking one
    # re-analyzes it and continues into the normal format/quality flow. This branch
    # must come BEFORE the no-formats check: a carousel legitimately has none of its
    # own, and falling through told users a post full of video had "no formats".
    if analyzed.info.carousel_items:
        await _open_gallery(
            message, ack, analyzed.media_id, analyzed.info, 1, callback_signer, locale
        )
        await show_placement_ad(ad_service_factory(session), user, AdPlacement.ANALYSIS.value)
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


def _link(inner_html: str, url: object) -> str:
    """Wrap already-escaped ``inner_html`` in an <a> when ``url`` is a usable http(s) link.

    Used for the chooser's inline links (title → source page, channel name → channel
    page), mirroring the reference bot. ``url`` comes from provider metadata and is only
    trusted when it's an http(s) string; anything else falls back to plain text so a
    stray value can never inject markup or a non-web scheme.
    """
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return f'<a href="{escape(url, quote=True)}">{inner_html}</a>'
    return inner_html


def _build_caption(
    info: MediaInfo,
    footer: str,
    translate: Translator,
    locale: str,
    *,
    formats_for: MediaFormat | None = None,
) -> str:
    """Rich header (title · duration · source · stats · channel) + optional formats list.

    ``info.title``/``info.platform`` are user/platform-generated content and are
    interpolated verbatim, never translated (Sprint 11.5 requirement #3). Stats come
    from the raw yt-dlp metadata (``info.raw``) and are best-effort — most providers
    omit some or all of these fields. When ``formats_for`` is given, the available
    options for that format are listed with their sizes, so the size is shown in the
    description rather than on the buttons.
    """
    title_html = _link(f"<b>{escape(info.title)}</b>", info.source_url)
    lines = [f"🎬 {title_html}"]
    meta: list[str] = []
    if info.duration:
        meta.append(f"⏱ {_format_duration(info.duration)}")
    if info.platform and info.platform != "*":
        meta.append(f"📺 {info.platform.capitalize()}")
    if meta:
        lines.append("   ".join(meta))

    stats: list[str] = []
    view_count = info.raw.get("view_count")
    like_count = info.raw.get("like_count")
    comment_count = info.raw.get("comment_count")
    if view_count is not None:
        stats.append(f"👁 {_fmt_count(view_count)}")
    if like_count is not None:
        stats.append(f"👍 {_fmt_count(like_count)}")
    if comment_count is not None:
        stats.append(f"💬 {_fmt_count(comment_count)}")
    uploaded = _format_upload_date(info.raw.get("upload_date"))
    if uploaded:
        stats.append(f"📅 {uploaded}")
    if stats:
        lines.append("   ".join(stats))

    channel = info.raw.get("channel") or info.raw.get("uploader")
    if channel:
        channel_url = info.raw.get("channel_url") or info.raw.get("uploader_url")
        chan = f"👤 {_link(escape(str(channel)), channel_url)}"
        subscribers = info.raw.get("channel_follower_count")
        if subscribers is not None:
            chan += f" · {_fmt_count(subscribers)} {translate('download.subscribers', locale)}"
        lines.append(chan)

    if formats_for is not None:
        lines.extend(_formats_block(info, formats_for, translate, locale))

    lines.append(f"\n{footer}")
    return "\n".join(lines)


def _formats_block(
    info: MediaInfo, format_: MediaFormat, translate: Translator, locale: str
) -> list[str]:
    """One line per available option for ``format_``: ``• <label> — <container> · <size>``."""
    options = [o for o in info.formats if o.format is format_]
    if not options:
        return []
    header_key = (
        "download.format.video" if format_ is MediaFormat.VIDEO else "download.format.audio"
    )
    lines = ["", translate(header_key, locale)]
    lines.extend(_format_line(o, format_) for o in options)
    return lines


def _format_line(option: MediaFormatOption, format_: MediaFormat) -> str:
    label = _option_label(option)
    detail: list[str] = []
    if format_ is MediaFormat.VIDEO:
        detail.append("mp4")  # video tiers are muxed to mp4 on delivery
    size = _human_size(option.approx_size_bytes)
    if size:
        detail.append(size)
    return f"• {label} — {' · '.join(detail)}" if detail else f"• {label}"


def _option_label(option: MediaFormatOption) -> str:
    """Quality/codec label for an option — mirrors the keyboard button label."""
    target = AUDIO_TARGET_BY_QUALITY.get(option.quality)
    return target.label if target is not None else option.quality.value


def _human_size(size_bytes: int | None) -> str | None:
    if not size_bytes:
        return None
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    mb = size_bytes / (1024 * 1024)
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{mb:.1f} MB"


def _format_upload_date(raw_date: Any) -> str | None:
    """yt-dlp ``upload_date`` is ``YYYYMMDD`` → ``Sep 24, 2021`` (best-effort)."""
    if not isinstance(raw_date, str) or len(raw_date) != 8 or not raw_date.isdigit():
        return None
    try:
        parsed = datetime.datetime.strptime(raw_date, "%Y%m%d")
    except ValueError:
        return None
    return parsed.strftime("%b %d, %Y")


def _media_caption(info: MediaInfo, translate: Translator, locale: str) -> str:
    """Caption shown above the format keyboard (choose format)."""
    return _build_caption(info, translate("download.choose_format", locale), translate, locale)


def _quality_caption(
    info: MediaInfo, format_: MediaFormat, translate: Translator, locale: str
) -> str:
    """Caption above the quality keyboard — lists each quality's size in the description."""
    return _build_caption(
        info,
        translate("download.choose_quality", locale),
        translate,
        locale,
        formats_for=format_,
    )


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
    caption = _quality_caption(analyzed.info, parsed.format, translate, locale)
    # Re-decorate with the caption-layer ad (two-layer ads) so it survives the
    # format → quality step instead of disappearing on the first tap.
    mixer = CaptionAdMixer(ad_service_factory(session))
    decorated, ad_buttons = await mixer.decorate_for_user(user, caption, user.total_downloads)
    caption = decorated or caption
    keyboard = append_ad_buttons(keyboard, ad_buttons)
    await _edit_chooser(callback.message, caption, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("g|"))
async def handle_gallery(
    callback: CallbackQuery,
    session: AsyncSession,
    user: UserSnapshot,
    analyzer_factory: AnalyzerFactory,
    ad_service_factory: AdServiceFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
    job_service_factory: JobServiceFactory | None = None,
    rate_limit_service_factory: RateLimitServiceFactory | None = None,
    notification_service: NotificationService | None = None,
) -> None:
    """Every gallery step: navigate, or act on the current item.

    Navigation is served entirely from the cached item list — no extraction — so paging
    is instant. Extraction happens only when the user commits to an item, which is also
    when that item earns its own metadata row.
    """
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "g" or parsed.arg is None:
        await callback.answer()
        return
    op = parsed.language or "n"
    index = parsed.arg

    analyzer = analyzer_factory(session)
    post = await analyzer.analyze_by_media_id(parsed.media_id)
    if post is None or not post.info.carousel_items:
        await callback.answer(translate("gallery.expired", locale), show_alert=True)
        return
    items = post.info.carousel_items
    if not 1 <= index <= len(items):
        await callback.answer(translate("gallery.item_gone", locale), show_alert=True)
        return

    if op in ("n", "s"):
        # Browsing and selecting are both served from the cached item list — no
        # extraction — so moving between items and screens is instant. yt-dlp only
        # runs once the user commits to a media type below.
        await _render_gallery(
            callback.message,
            parsed.media_id,
            post.info,
            index,
            callback_signer,
            locale,
            selected=(op == "s"),
        )
        await callback.answer()
        return

    # Any other op needs the item's real formats, so extract it now.
    try:
        analyzed = await analyzer.analyze(post.info.source_url, item_index=index)
    except UserFacingError as exc:
        await callback.answer(translate(exc.translation_key, locale), show_alert=True)
        return
    except Exception:
        _log.exception("gallery_item_failed", item=index, media_id=parsed.media_id)
        await callback.answer(translate("errors.unexpected", locale), show_alert=True)
        return

    if not analyzed.info.formats:
        await callback.answer(translate("gallery.item_gone", locale), show_alert=True)
        return

    if op == "i":
        # An image has nothing to choose, so tapping it downloads. Any intermediate
        # screen here would be a screen with exactly one button on it.
        if not (
            job_service_factory
            and rate_limit_service_factory
            and notification_service
        ):
            await callback.answer(translate("errors.unexpected", locale), show_alert=True)
            return
        try:
            await rate_limit_service_factory(session).authorize_download(user.telegram_id)
        except UserFacingError as exc:
            await callback.answer(translate(exc.translation_key, locale), show_alert=True)
            return
        await callback.answer()
        await _auto_download(
            session, user, analyzed, MediaFormat.IMAGE, Quality.IMAGE,
            job_service_factory, ad_service_factory, notification_service,
            translate, locale,
        )
        return

    fmt = MediaFormat.VIDEO if op == "v" else MediaFormat.AUDIO
    if not any(o.format is fmt for o in analyzed.info.formats):
        await callback.answer(translate("download.no_formats", locale), show_alert=True)
        return
    await _start_quality_step(
        callback, session, user, analyzed, fmt,
        ad_service_factory, callback_signer, translate, locale,
        post_media_id=parsed.media_id, index=index,
    )


async def _start_quality_step(
    callback: CallbackQuery,
    session: AsyncSession,
    user: UserSnapshot,
    analyzed: Any,
    fmt: MediaFormat,
    ad_service_factory: AdServiceFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
    post_media_id: int,
    index: int,
) -> None:
    """Hand a chosen gallery item into the existing quality-selection flow.

    ``post_media_id``/``index`` are carried purely so Back can rebuild the gallery.
    """
    # THE back fix: this quality screen was opened from the gallery, so Back must
    # return to the gallery at the very item it was opened from. Previously it used
    # the default pack_back(item media_id), which walked to that ITEM's own format
    # screen — the browser (position, preview, Previous/Next) disappeared entirely
    # and the user had no way back except resending the link.
    keyboard = build_quality_keyboard(
        analyzed.media_id,
        fmt,
        analyzed.info,
        callback_signer,
        locale,
        # One step back up the chain: quality → the selected-item screen (not the
        # browser), so trying the other media type does not mean re-selecting the item.
        back_callback=item_back_callback(post_media_id, index, callback_signer),
    )
    caption = _quality_caption(analyzed.info, fmt, translate, locale)
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


async def _open_gallery(
    message: Message,
    ack: Message,
    media_id: int,
    info: MediaInfo,
    index: int,
    signer: CallbackSigner,
    locale: str,
) -> None:
    """First render of the gallery: replace the "Analyzing…" ack with a photo message.

    It MUST be sent as a photo, not edited into one: Telegram cannot convert a text
    message into a media message, so a gallery that started as text could never show a
    preview for any item. When no item has a usable preview at all we fall back to a
    text gallery — navigation still works, it simply stays text for that session.
    """
    items = info.carousel_items
    item = items[index - 1]
    caption = browse_caption(
        item, len(items), locale, info.title, source_total=info.raw.get("playlist_total")
    )
    keyboard = build_browse_keyboard(media_id, items, index, signer, locale)
    if item.thumbnail_url:
        try:
            await message.answer_photo(
                item.thumbnail_url, caption=caption, reply_markup=keyboard
            )
            await ack.delete()
            return
        except Exception as exc:  # unreachable/blocked preview → text gallery
            _log.debug("gallery_photo_failed", error=str(exc), index=index)
    await ack.edit_text(caption, reply_markup=keyboard)


async def _render_gallery(
    message: object,
    media_id: int,
    info: MediaInfo,
    index: int,
    signer: CallbackSigner,
    locale: str,
    selected: bool = False,
) -> None:
    """Re-render the gallery IN PLACE for ``index`` — never a new message.

    ``selected`` picks the screen: the browser (navigation + Select) or the chosen
    item's actions. Both keep the same preview, so stepping between them is a caption
    and keyboard swap the user reads as one continuous screen.

    Swapping the picture needs editMessageMedia; editing the caption alone would leave
    the previous item's image above the new item's buttons. A text-only gallery (no
    preview was available at open time) can only ever have its text edited.
    """
    if not isinstance(message, Message):
        return
    items = info.carousel_items
    item = items[index - 1]
    if selected:
        caption = item_caption(item, len(items), locale, info.title)
        keyboard = build_item_keyboard(media_id, item, signer, locale)
    else:
        caption = browse_caption(
            item, len(items), locale, info.title,
            source_total=info.raw.get("playlist_total"),
        )
        keyboard = build_browse_keyboard(media_id, items, index, signer, locale)
    if message.photo and item.thumbnail_url:
        try:
            await message.edit_media(
                InputMediaPhoto(media=item.thumbnail_url, caption=caption),
                reply_markup=keyboard,
            )
            return
        except TelegramBadRequest as exc:
            # "message is not modified" = the same item was re-selected (the counter
            # button); anything else means the preview URL was rejected, and the
            # caption still has to move on to the new item.
            if "not modified" in str(exc).lower():
                return
            _log.debug("gallery_edit_media_failed", error=str(exc), index=index)
    await _edit_chooser(message, caption, keyboard)


async def _edit_chooser(message: object, text: str, keyboard: object) -> None:
    """Edit the chooser in place — caption for a photo message, text otherwise."""
    if not isinstance(message, Message):
        return
    if message.photo:
        await message.edit_caption(caption=text, reply_markup=keyboard)  # type: ignore[arg-type]
    else:
        await message.edit_text(text, reply_markup=keyboard)  # type: ignore[arg-type]
