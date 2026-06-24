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

Sprint 6 is single-user; the waiter loop already iterates all waiters so Sprint 7
fan-out is a delivery-only change (Task 7.2).
"""

from __future__ import annotations

import datetime
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from core.config import Settings
from core.logging import get_logger
from domain.entities.media import AUDIO_TARGET_BY_QUALITY, MediaInfo
from domain.enums import JobStatus, MediaFormat, Quality
from domain.exceptions import (
    DownloadTimeoutError,
    ExtractionFailedError,
    FileTooLargeError,
    InfrastructureError,
    TelegramUploadError,
)
from domain.protocols.downloader import DownloaderProtocol, ProviderRetryElsewhere
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
from services.notification_service import NotificationService, ProgressStage
from services.settings_service import SettingNotFoundError, SettingsService
from services.url_analyzer import URLAnalyzerService

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
        dest = Path(self._settings.download_temp_dir) / job_id_str
        started = time.monotonic()

        try:
            await self._jobs.set_status(job_id, JobStatus.PROCESSING.value, started_at=now_utc())
            await self._stage(chat_id, message_id, ProgressStage.DOWNLOADING)

            analyzed = await self._analyzer.analyze_by_media_id(media_id)
            if analyzed is None:
                raise ExtractionFailedError("The media is no longer available.")
            info = analyzed.info

            produced, file_size = await self._produce_file(
                info, format_, quality, dest, chat_id, message_id
            )
            await self._enforce_size_limit(file_size)

            await self._stage(chat_id, message_id, ProgressStage.UPLOADING)
            upload_started = time.monotonic()
            uploaded = await self._deliver(
                job_id, produced, info, format_, quality, file_size, media_id
            )
            _log.info(
                "upload_seconds",
                job_id=job_id_str,
                upload_seconds=round(time.monotonic() - upload_started, 3),
                file_size=file_size,
            )

            await self._cache.set_file_id(media_id, format_.value, quality.value, uploaded.file_id)
            await self._waiters.delete_for_job(job_id)
            await self._active.delete_by_job(job_id)
            await self._jobs.set_status(job_id, JobStatus.COMPLETED.value, finished_at=now_utc())
            if chat_id is not None and message_id is not None:
                await self._notifier.notify_completed(chat_id, message_id)
            await self._release_lock(ctx)
            await self._cache.delete_job_context(job_id_str)
            _log.info(
                "job_completed",
                job_id=job_id_str,
                job_processing_seconds=round(time.monotonic() - started, 3),
            )
        finally:
            shutil.rmtree(dest, ignore_errors=True)

    async def _produce_file(
        self,
        info: MediaInfo,
        format_: MediaFormat,
        quality: Quality,
        dest: Path,
        chat_id: int | None,
        message_id: int | None,
    ) -> tuple[Path, int]:
        download_started = time.monotonic()
        downloaded = await self._downloader.download(info, format_, quality, dest)
        _log.info(
            "download_seconds",
            download_seconds=round(time.monotonic() - download_started, 3),
            platform=info.platform,
            format=format_.value,
            quality=quality.value,
        )
        produced = downloaded.path
        target = AUDIO_TARGET_BY_QUALITY.get(quality)
        if format_ is MediaFormat.AUDIO and target is not None:
            await self._stage(chat_id, message_id, ProgressStage.PROCESSING)
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
        produced: Path,
        info: MediaInfo,
        format_: MediaFormat,
        quality: Quality,
        file_size: int,
        media_id: int,
    ) -> UploadedFile:
        """Deliver exactly one file to each waiter (16.1 W4-W7).

        The first waiter's **upload is their delivery** — we never send them the file
        a second time. That upload mints the reusable ``file_id``, which is cached and
        re-sent to any additional waiters (fan-out, Sprint 7). One file per user.
        """
        waiters = list(await self._waiters.list_for_job(job_id))
        users = [await self._users.get_by_id(w.user_id) for w in waiters]
        pairs = [(w, u) for w, u in zip(waiters, users, strict=True) if u is not None]
        if not pairs:  # pragma: no cover - the originator is always a waiter
            raise ExtractionFailedError("No recipient for the completed job.")

        first_waiter, first_user = pairs[0]
        uploaded = await self._file_sender.upload(
            produced,
            format_=format_,
            quality=quality,
            chat_id=first_user.telegram_id,
            filename=_safe_filename(info.title, produced.suffix),
            caption=info.title,
        )
        cached = await self._cached.upsert(
            media_id=media_id,
            format_=format_.value,
            quality=quality.value,
            telegram_file_id=uploaded.file_id,
            telegram_unique_file_id=uploaded.unique_file_id,
            file_size=file_size,
        )
        for index, (waiter, user) in enumerate(pairs):
            await self._downloads.create_completed(
                user_id=waiter.user_id,
                cached_file_id=cached.id,
                platform=info.platform,
                format_=format_.value,
                quality=quality.value,
                file_size=file_size,
            )
            await self._users.increment_download_counters(waiter.user_id)
            if index != 0:  # the first waiter already received it via the upload
                await self._file_sender.send_cached(
                    user.telegram_id,
                    uploaded.file_id,
                    format_=format_,
                    quality=quality,
                    caption=info.title,
                )
        return uploaded

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
        await self._stage(ctx.get("telegram_id"), ctx.get("message_id"), ProgressStage.QUEUED)
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
        chat_id, message_id = ctx.get("telegram_id"), ctx.get("message_id")
        if chat_id is not None and message_id is not None:
            await self._notifier.notify_failed(chat_id, message_id)
        await self._waiters.delete_for_job(job_id)
        await self._active.delete_by_job(job_id)
        await self._release_lock(ctx)
        await self._cache.delete_job_context(job_id_str)
        _log.warning("job_permanently_failed", job_id=job_id_str, reason=reason)

    async def _stage(
        self, chat_id: int | None, message_id: int | None, stage: ProgressStage
    ) -> None:
        if chat_id is not None and message_id is not None:
            await self._notifier.notify_stage(chat_id, message_id, stage)

    async def _release_lock(self, ctx: dict[str, object]) -> None:
        token = ctx.get("lock_token")
        media_id, fmt, qual = ctx.get("media_id"), ctx.get("format"), ctx.get("quality")
        if isinstance(token, str) and isinstance(media_id, int):
            await self._cache.release_download_lock(media_id, str(fmt), str(qual), token)
