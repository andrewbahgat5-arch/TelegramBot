"""DownloadService (MASTER_PLAN Component 9.2, Task 6.5, flow 16.1 W0-W12).

Executes one queued job end-to-end: resolve media → download (via the registry,
never a provider) → transcode audio to the chosen codec if needed (D-041) →
upload once to mint a reusable ``file_id`` → UPSERT ``cached_files`` → for every
waiter insert ``downloads`` + bump counters + deliver the file → mark the job
complete → release the lock → clear temp files.

``process`` performs the happy path and raises on failure (after wiping temp
files). The worker (Task 6.6) owns the retry / permanent-failure decision and calls
:meth:`mark_retry` or :meth:`mark_permanent_failure`, which this service implements
so the cleanup (lock, active marker, waiters, context, progress message) lives in
one place.

Fan-out (Task 7.2): ``_deliver`` reads every waiter and delivers the file once to
each. The first not-yet-delivered waiter's *upload* is their delivery (it mints the
reusable ``file_id``); each additional waiter receives that ``file_id``. Delivery is
idempotent across worker retries — the minted ``file_id`` and the set of already-
delivered waiters are persisted in the Redis job context (outside the per-job DB
transaction), so a retry after partial delivery never sends a waiter their file
twice. One waiter's delivery failure is logged and skipped, never blocking the rest.

Ads (Task 9.3): after a waiter is freshly delivered their file, the optional
``AdShowProtocol`` hook (``AdService``) is invoked with that waiter's post-increment
download total (flow 16.7, D-010). It is best-effort — an ad failure never fails the
already-completed download, and a retry never re-shows an ad (only *newly* delivered
waiters are offered one).
"""

from __future__ import annotations

import datetime
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from core import metrics
from core.config import Settings
from core.i18n import resolve_locale, translate
from core.logging import get_logger
from domain.entities.media import AUDIO_TARGET_BY_QUALITY, MediaInfo
from domain.enums import JobStatus, MediaFormat, Quality
from domain.exceptions import (
    CachedFileExpiredError,
    DownloadTimeoutError,
    ExtractionFailedError,
    FileTooLargeError,
    InfrastructureError,
    TelegramUploadError,
)
from domain.protocols.advertising import AdButtonSpec, AdShowProtocol
from domain.protocols.downloader import (
    DownloaderProtocol,
    DownloadProgress,
    ProviderRetryElsewhere,
)
from domain.protocols.file_sender import FileSenderProtocol, UploadedFile
from domain.protocols.repositories import (
    ActiveDownloadRepositoryProtocol,
    CachedFileRepositoryProtocol,
    DownloadRepositoryProtocol,
    JobRepositoryProtocol,
    JobWaiterRepositoryProtocol,
    UserRepositoryProtocol,
)
from domain.protocols.transcoder import TranscoderProtocol
from services.cache_service import CacheService
from services.caption_ad_mixer import CaptionAdMixer
from services.notification_service import NotificationService, ProgressStage
from services.settings_service import SettingNotFoundError, SettingsService
from services.url_analyzer import URLAnalyzerService
from services.user_preference_service import UserPreferenceStore

_log = get_logger("services.download_service")

# Transient failures the worker may retry (re-enqueue). Everything else is permanent.
RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    ProviderRetryElsewhere,
    DownloadTimeoutError,
    InfrastructureError,
    TelegramUploadError,
)

_MAX_FILE_SIZE_FALLBACK = 2_147_483_648  # 2 GiB (settings `max_file_size` default)


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


# Characters illegal in Windows/macOS/Linux filenames, plus control chars.
_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_MAX_FILENAME_STEM = 120


def _delivery_caption_base(info: MediaInfo, format_: MediaFormat) -> str | None:
    """Caption base for the delivered file.

    Images append the source page link under the title (feature request), so the
    recipient can open the original. Video/audio keep the title only.
    """
    title = info.title if info.title and info.title != "Untitled" else None
    if format_ is MediaFormat.IMAGE and info.source_url:
        return f"{title}\n{info.source_url}" if title else info.source_url
    return title


_BAR_WIDTH = 10
# Min seconds between progress edits — Telegram rate-limits rapid editMessageText.
_PROGRESS_MIN_INTERVAL = 3.0


def _human_size(num_bytes: int) -> str:
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.0f} KB"
    if num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


def _render_progress(downloaded: int, total: int | None) -> str:
    """A live download bar, e.g. ``⬇️ ▰▰▰▰▱▱▱▱▱▱  44%`` + ``12.3 MB / 28.0 MB``."""
    if total and total > 0:
        frac = min(1.0, downloaded / total)
        filled = round(frac * _BAR_WIDTH)
        bar = "▰" * filled + "▱" * (_BAR_WIDTH - filled)
        return f"⬇️ {bar}  {int(frac * 100)}%\n{_human_size(downloaded)} / {_human_size(total)}"
    return f"⬇️ {_human_size(downloaded)}"


def _render_uploading(size_bytes: int, locale: str) -> str:
    """The post-download status: a full bar + the *real* final file size, then upload.

    Replaces the live download bar the moment the file is ready, so the user never
    sees a stale/partial ``100%`` frame (which showed one stream's size, not the merged
    file) while the — sometimes long — upload to Telegram runs.
    """
    bar = "▰" * _BAR_WIDTH
    return f"⬆️ {bar}  100%\n{_human_size(size_bytes)}\n{translate('notification.uploading', locale)}"


def _render_processing(locale: str) -> str:
    """Shown while FFmpeg transcodes audio (between download and upload)."""
    return translate("notification.processing", locale)


def _safe_filename(title: str, suffix: str) -> str:
    """Build a delivered filename from the media title (#11): ``<sanitized title><ext>``.

    Strips characters illegal across filesystems, collapses whitespace, trims length,
    and preserves the produced file's extension. Falls back to ``media`` if the title
    sanitizes to nothing.
    """
    stem = _INVALID_FILENAME_CHARS.sub("", title)
    stem = " ".join(stem.split()).strip().strip(".")
    stem = stem[:_MAX_FILENAME_STEM].strip() or "media"
    return f"{stem}{suffix}"


class DownloadService:
    def __init__(
        self,
        *,
        job_repo: JobRepositoryProtocol[Any],
        cached_file_repo: CachedFileRepositoryProtocol[Any],
        download_repo: DownloadRepositoryProtocol[Any],
        job_waiter_repo: JobWaiterRepositoryProtocol[Any],
        active_download_repo: ActiveDownloadRepositoryProtocol[Any],
        user_repo: UserRepositoryProtocol[Any],
        analyzer: URLAnalyzerService,
        downloader: DownloaderProtocol,
        transcoder: TranscoderProtocol,
        file_sender: FileSenderProtocol,
        notification_service: NotificationService,
        cache_service: CacheService,
        settings_service: SettingsService,
        settings: Settings,
        ad_service: AdShowProtocol | None = None,
        caption_mixer: CaptionAdMixer | None = None,
        preference_repo: UserPreferenceStore | None = None,
    ) -> None:
        self._jobs = job_repo
        self._cached = cached_file_repo
        self._downloads = download_repo
        self._waiters = job_waiter_repo
        self._active = active_download_repo
        self._users = user_repo
        self._analyzer = analyzer
        self._downloader = downloader
        self._transcoder = transcoder
        self._file_sender = file_sender
        self._notifier = notification_service
        self._cache = cache_service
        self._settings_service = settings_service
        self._settings = settings
        self._ad_service = ad_service
        self._caption_mixer = caption_mixer
        self._prefs = preference_repo

    async def _caption(
        self, user: Any, total_downloads: int, base: str | None
    ) -> tuple[str | None, tuple[AdButtonSpec, ...]]:
        """Base caption + any due caption-layer ad (text + buttons) for ``user`` (two-layer).

        Respects the per-user "Don't send title" preference (item #10): the delivered
        caption base is the media title, so drop it when the recipient has opted out.
        """
        if base and self._prefs is not None and getattr(user, "id", None) is not None:
            pref = await self._prefs.get_by_user_id(user.id)
            if pref is not None and getattr(pref, "hide_title", False):
                base = None
        if self._caption_mixer is None:
            return base, ()
        return await self._caption_mixer.decorate_for_user(user, base, total_downloads)

    async def process(self, job_id_str: str) -> None:
        """Run a job to completion (flow 16.1 W1-W12). Raises on failure."""
        job_id = uuid.UUID(job_id_str)
        job = await self._jobs.get_by_uuid(job_id)
        if job is None:
            _log.warning("job_missing_on_process", job_id=job_id_str)
            return
        media_id: int = job.media_id
        format_ = MediaFormat(job.format)
        quality = Quality(job.quality)
        ctx = await self._cache.get_job_context(job_id_str) or {}
        chat_id = ctx.get("telegram_id")
        message_id = ctx.get("message_id")
        locale = await self._locale_for(chat_id)
        dest = Path(self._settings.download_temp_dir) / job_id_str
        started = time.monotonic()

        try:
            await self._jobs.set_status(job_id, JobStatus.PROCESSING.value, started_at=now_utc())
            await self._stage(chat_id, message_id, ProgressStage.DOWNLOADING, locale)

            analyzed = await self._analyzer.analyze_by_media_id(media_id)
            if analyzed is None:
                raise ExtractionFailedError("The media is no longer available.")
            info = analyzed.info

            produced, file_size = await self._produce_file(
                info, format_, quality, dest, chat_id, message_id, locale
            )
            await self._enforce_size_limit(file_size)

            # Replace the live download bar with a "ready → uploading" line showing the
            # *real* file size, so the user isn't left staring at a stale/partial 100%
            # frame while a large file uploads to Telegram (which can take a while).
            await self._stage(chat_id, message_id, ProgressStage.UPLOADING, locale)
            await self._show_status(chat_id, message_id, _render_uploading(file_size, locale))
            upload_started = time.monotonic()
            uploaded = await self._deliver(
                job_id, ctx, produced, info, format_, quality, file_size, media_id
            )
            upload_elapsed = time.monotonic() - upload_started
            metrics.observe_upload(upload_elapsed)
            _log.info(
                "upload_seconds",
                job_id=job_id_str,
                upload_seconds=round(upload_elapsed, 3),
                file_size=file_size,
            )

            await self._cache.set_file_id(media_id, format_.value, quality.value, uploaded.file_id)
            await self._waiters.delete_for_job(job_id)
            await self._active.delete_by_job(job_id)
            await self._jobs.set_status(job_id, JobStatus.COMPLETED.value, finished_at=now_utc())
            await self._notify_waiters(ctx, completed=True)
            await self._release_lock(ctx)
            await self._cache.delete_job_context(job_id_str)
            _log.info(
                "job_completed",
                job_id=job_id_str,
                job_processing_seconds=round(time.monotonic() - started, 3),
            )
        finally:
            shutil.rmtree(dest, ignore_errors=True)

    def _download_progress_cb(self, chat_id: int, message_id: int) -> DownloadProgress:
        """A throttled callback that edits the progress message with a live bar.

        Edits are rate-limit-safe: skipped unless the rendered text changed AND at least
        ``_PROGRESS_MIN_INTERVAL`` has passed (the final 100% frame is always sent). Edit
        failures are swallowed — progress is cosmetic, never a reason to fail a download.
        """
        last_at = 0.0
        last_text = ""
        max_total = 0

        async def cb(downloaded: int, total: int | None) -> None:
            nonlocal last_at, last_text, max_total
            if total:
                max_total = max(max_total, total)
            # A merged video downloads video then audio as *separate* 0→100 passes. The
            # trailing audio stream is tiny, so its ``100%`` frame would overwrite the
            # bar with a misleading small size. Skip any stream far smaller than the
            # largest seen — the real, final size is shown at the upload step instead.
            if total and max_total and total < max_total // 2:
                return
            text = _render_progress(downloaded, total)
            now = time.monotonic()
            done = total is not None and downloaded >= total
            if text == last_text or (now - last_at < _PROGRESS_MIN_INTERVAL and not done):
                return
            last_at, last_text = now, text
            try:
                await self._notifier.notify_text(chat_id, message_id, text)
            except Exception:  # noqa: S110 - progress edits are best-effort
                pass

        return cb

    async def _show_status(self, chat_id: int | None, message_id: int | None, text: str) -> None:
        """Best-effort edit of the progress message to an arbitrary status line."""
        if chat_id is None or message_id is None:
            return
        try:
            await self._notifier.notify_text(chat_id, message_id, text)
        except Exception:  # noqa: S110 - status edits are best-effort, never fatal
            pass

    async def _produce_file(
        self,
        info: MediaInfo,
        format_: MediaFormat,
        quality: Quality,
        dest: Path,
        chat_id: int | None,
        message_id: int | None,
        locale: str,
    ) -> tuple[Path, int]:
        progress_cb = (
            self._download_progress_cb(chat_id, message_id)
            if chat_id is not None and message_id is not None
            else None
        )
        download_started = time.monotonic()
        downloaded = await self._downloader.download(
            info, format_, quality, dest, progress_cb=progress_cb
        )
        download_elapsed = time.monotonic() - download_started
        metrics.observe_download(download_elapsed)
        _log.info(
            "download_seconds",
            download_seconds=round(download_elapsed, 3),
            platform=info.platform,
            format=format_.value,
            quality=quality.value,
        )
        produced = downloaded.path
        target = AUDIO_TARGET_BY_QUALITY.get(quality)
        if format_ is MediaFormat.AUDIO and target is not None:
            await self._stage(chat_id, message_id, ProgressStage.PROCESSING, locale)
            await self._show_status(chat_id, message_id, _render_processing(locale))
            produced = await self._transcoder.transcode_audio(produced, target)
        return produced, produced.stat().st_size

    async def _enforce_size_limit(self, file_size: int) -> None:
        try:
            max_size = int(await self._settings_service.get("max_file_size"))
        except SettingNotFoundError:
            max_size = _MAX_FILE_SIZE_FALLBACK
        if file_size > max_size:
            raise FileTooLargeError(f"The file is {file_size // (1024 * 1024)} MB, over the limit.")

    async def _deliver(
        self,
        job_id: uuid.UUID,
        ctx: dict[str, Any],
        produced: Path,
        info: MediaInfo,
        format_: MediaFormat,
        quality: Quality,
        file_size: int,
        media_id: int,
    ) -> UploadedFile:
        """Deliver exactly one file to each waiter (16.1 W4-W7), idempotently.

        The first not-yet-delivered waiter's **upload is their delivery** — we never
        send them the file a second time. That upload mints the reusable ``file_id``,
        which is cached and re-sent to every other waiter (fan-out). One file per user.

        Idempotency across retries: the minted ``file_id`` and the set of already-
        delivered waiters live in the Redis job context (``ctx``), which is *not* part
        of the per-job DB transaction. If a previous attempt delivered to some waiters
        and then failed (rolling back the DB writes), this attempt reuses the stored
        ``file_id`` (no re-upload, so the upload-target is not re-delivered) and skips
        the Telegram send for anyone already delivered. The DB rows (``downloads`` +
        counters) are re-created for every waiter — correct, since they rolled back.
        """
        job_id_str = str(job_id)
        delivered: set[int] = set(ctx.get("delivered", []))
        # Waiters who receive the file *this* attempt (vs. on a prior, rolled-back try):
        # only they get a post-delivery ad, so a retry never re-shows an ad (16.7, 9.3).
        newly_delivered: set[int] = set()
        post_totals: dict[int, int] = {}
        # The delivered file's message id per waiter, so the post-download ad can be
        # attached as a reply directly under the media (#30).
        delivered_message_ids: dict[int, int] = {}
        file_id: str | None = ctx.get("file_id")
        unique_file_id: str | None = ctx.get("unique_file_id")

        waiters = list(await self._waiters.list_for_job(job_id))
        users = [await self._users.get_by_id(w.user_id) for w in waiters]
        pairs = [(w, u) for w, u in zip(waiters, users, strict=True) if u is not None]
        if not pairs:  # pragma: no cover - the originator is always a waiter
            raise ExtractionFailedError("No recipient for the completed job.")

        if file_id is None:
            # Mint the file_id by uploading to the first waiter who has not already
            # received it on a prior attempt — that upload is their delivery.
            target = next((p for p in pairs if p[0].user_id not in delivered), pairs[0])
            target_caption, target_buttons = await self._caption(
                target[1], target[1].total_downloads + 1, _delivery_caption_base(info, format_)
            )
            uploaded = await self._file_sender.upload(
                produced,
                format_=format_,
                quality=quality,
                chat_id=target[1].telegram_id,
                filename=_safe_filename(info.title, produced.suffix),
                caption=target_caption,
                buttons=target_buttons,
            )
            file_id, unique_file_id = uploaded.file_id, uploaded.unique_file_id
            delivered.add(target[0].user_id)
            newly_delivered.add(target[0].user_id)
            if uploaded.message_id is not None:
                delivered_message_ids[target[0].user_id] = uploaded.message_id
            await self._cache.record_uploaded_file(job_id_str, file_id, unique_file_id)
            await self._cache.record_delivered(job_id_str, target[0].user_id)

        cached = await self._cached.upsert(
            media_id=media_id,
            format_=format_.value,
            quality=quality.value,
            telegram_file_id=file_id,
            telegram_unique_file_id=unique_file_id or "",
            file_size=file_size,
        )
        for waiter, user in pairs:
            # Capture the post-increment lifetime total *before* the bump (the ad
            # frequency modulo is locked post-increment, D-010 / 16.7 step 4).
            post_totals[waiter.user_id] = user.total_downloads + 1
            await self._downloads.create_completed(
                user_id=waiter.user_id,
                cached_file_id=cached.id,
                platform=info.platform,
                format_=format_.value,
                quality=quality.value,
                file_size=file_size,
                title=info.title,
                source_url=info.source_url,
                duration_seconds=info.duration,
                size_bytes=file_size,
            )
            metrics.record_download(
                platform=info.platform,
                format_=format_.value,
                quality=quality.value,
                result="completed",
            )
            await self._users.increment_download_counters(waiter.user_id)
            # Invalidate the user snapshot so the next rate-limit read sees the new count.
            await self._cache.delete_user(user.telegram_id)
            if waiter.user_id in delivered:
                continue  # already received it (via the upload, or a prior attempt)
            waiter_caption, waiter_buttons = await self._caption(
                user, post_totals[waiter.user_id], _delivery_caption_base(info, format_)
            )
            try:
                sent_message_id = await self._file_sender.send_cached(
                    user.telegram_id,
                    file_id,
                    format_=format_,
                    quality=quality,
                    caption=waiter_caption,
                    buttons=waiter_buttons,
                )
            except CachedFileExpiredError as exc:
                # The just-minted file_id was rejected — treat as an upload failure so
                # the whole job retries rather than silently dropping every waiter.
                raise TelegramUploadError("Minted file_id was rejected.") from exc
            except Exception as exc:  # one waiter's failure must not block the others
                _log.warning(
                    "waiter_delivery_failed",
                    job_id=job_id_str,
                    user_id=waiter.user_id,
                    error=str(exc),
                )
                continue
            delivered.add(waiter.user_id)
            newly_delivered.add(waiter.user_id)
            if sent_message_id is not None:
                delivered_message_ids[waiter.user_id] = sent_message_id
            await self._cache.record_delivered(job_id_str, waiter.user_id)

        await self._show_ads(pairs, newly_delivered, post_totals, delivered_message_ids)
        return UploadedFile(
            file_id=file_id, unique_file_id=unique_file_id or "", size_bytes=file_size
        )

    async def _show_ads(
        self,
        pairs: list[tuple[Any, Any]],
        newly_delivered: set[int],
        post_totals: dict[int, int],
        delivered_message_ids: dict[int, int],
    ) -> None:
        """Run the post-delivery ad hook for each freshly-delivered waiter (Task 9.3).

        The ad is attached as a reply to the delivered media so it sits directly under
        it (#30). Entirely best-effort: the file is already delivered, so a failure here
        must never fail the job (which would trigger a retry and re-deliver the file). The
        hook itself swallows send errors; this guard additionally contains any unexpected
        error per waiter.
        """
        if self._ad_service is None:
            return
        for waiter, user in pairs:
            if waiter.user_id not in newly_delivered:
                continue
            try:
                await self._ad_service.maybe_show(
                    chat_id=user.telegram_id,
                    role=str(user.role),
                    is_premium=user.is_premium,
                    premium_expires_at=user.premium_expires_at,
                    total_downloads=post_totals[waiter.user_id],
                    language=user.language,
                    telegram_id=user.telegram_id,
                    user_row_id=user.id,
                    reply_to_message_id=delivered_message_ids.get(waiter.user_id),
                )
            except Exception as exc:  # an ad must never break a completed download
                _log.warning("ad_hook_failed", user_id=waiter.user_id, error=str(exc))

    async def handle_failure(
        self, job_id_str: str, *, reason: str, retryable: bool, max_retries: int
    ) -> bool:
        """Decide retry vs. permanent failure (Section 12.3, validation checklist).

        Returns True if the job was re-queued (the caller must enqueue it at LOW
        priority), False if it was permanently failed. The retry budget is the job's
        ``retry_count`` against ``max_retries``.
        """
        job = await self._jobs.get_by_uuid(uuid.UUID(job_id_str))
        retry_count: int = job.retry_count if job is not None else max_retries
        if retryable and retry_count < max_retries:
            await self.mark_retry(job_id_str)
            return True
        await self.mark_permanent_failure(job_id_str, reason)
        return False

    async def mark_retry(self, job_id_str: str) -> None:
        """Transient failure with retries left: RETRY_QUEUED → re-enqueue (LOW) (12.3)."""
        job_id = uuid.UUID(job_id_str)
        await self._jobs.set_status(job_id, JobStatus.RETRY_QUEUED.value, increment_retry=True)
        ctx = await self._cache.get_job_context(job_id_str) or {}
        telegram_id = ctx.get("telegram_id")
        locale = await self._locale_for(telegram_id)
        await self._stage(telegram_id, ctx.get("message_id"), ProgressStage.QUEUED, locale)
        await self._jobs.set_status(job_id, JobStatus.QUEUED.value)
        # Re-enqueue handled by the caller's QueueService (worker owns the queue).
        _log.info("job_retry_queued", job_id=job_id_str)

    async def mark_permanent_failure(self, job_id_str: str, reason: str) -> None:
        """Give up: PERMANENTLY_FAILED, notify the user, release all held resources."""
        job_id = uuid.UUID(job_id_str)
        await self._jobs.set_status(
            job_id, JobStatus.PERMANENTLY_FAILED.value, finished_at=now_utc(), error_message=reason
        )
        ctx = await self._cache.get_job_context(job_id_str) or {}
        await self._notify_waiters(ctx, completed=False)
        await self._waiters.delete_for_job(job_id)
        await self._active.delete_by_job(job_id)
        await self._release_lock(ctx)
        await self._cache.delete_job_context(job_id_str)
        _log.warning("job_permanently_failed", job_id=job_id_str, reason=reason)

    async def _notify_waiters(self, ctx: dict[str, Any], *, completed: bool) -> None:
        """Edit every waiter's progress message to ✅/❌ (16.1 W7, per-waiter).

        Uses the ``progress`` map populated by ``JobService`` (originator + fan-out
        duplicates). Falls back to the top-level originator fields for legacy contexts.
        Each edit is best-effort — one failed edit never blocks the others. Each
        waiter's *own* language is resolved fresh here (Sprint 11.5) — fan-out can
        deliver to users with different languages, and this path must be
        self-sufficient (``mark_permanent_failure`` can call it on a retry attempt
        with no ``_deliver`` in-memory state to reuse).
        """
        targets = list((ctx.get("progress") or {}).values())
        if not targets:
            tid, mid = ctx.get("telegram_id"), ctx.get("message_id")
            if tid is not None and mid is not None:
                targets = [{"telegram_id": tid, "message_id": mid}]
        for target in targets:
            chat_id, message_id = target.get("telegram_id"), target.get("message_id")
            if chat_id is None or message_id is None:
                continue
            locale = await self._locale_for(chat_id)
            if completed:
                await self._notifier.notify_completed(chat_id, message_id, locale)
            else:
                await self._notifier.notify_failed(chat_id, message_id, locale)

    async def _stage(
        self, chat_id: int | None, message_id: int | None, stage: ProgressStage, locale: str
    ) -> None:
        if chat_id is not None and message_id is not None:
            await self._notifier.notify_stage(chat_id, message_id, stage, locale)

    async def _locale_for(self, telegram_id: int | None) -> str:
        """Resolve a recipient's locale by ``telegram_id`` (read-only, Sprint 11.5).

        Mirrors ``LocaleMiddleware``'s resolution exactly, so behavior is identical
        whether a message originates in the bot process or here in the worker.
        """
        if telegram_id is None:
            return resolve_locale(None)
        user = await self._users.get_by_telegram_id(telegram_id)
        return resolve_locale(user.language if user is not None else None)

    async def _release_lock(self, ctx: dict[str, object]) -> None:
        token = ctx.get("lock_token")
        media_id, fmt, qual = ctx.get("media_id"), ctx.get("format"), ctx.get("quality")
        if isinstance(token, str) and isinstance(media_id, int):
            await self._cache.release_download_lock(media_id, str(fmt), str(qual), token)
