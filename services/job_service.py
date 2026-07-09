"""JobService (MASTER_PLAN Component 9.2, Task 6.4, flows 16.1-16.2).

Decides what happens when a user requests a (media, format, quality):

* **Cache hit** — deliver the cached ``file_id`` instantly, record the download,
  bump counters, edit the progress message to ✅ (flow 16.2).
* **Cache miss** — claim the ``active_downloads`` slot, create a ``jobs`` row + the
  originator ``job_waiters`` row, stash the request-side context (progress message,
  lock token) for the worker, and enqueue (flow 16.1 T0-T6).
* **Duplicate active request** — attach the user as a waiter on the in-flight job
  (16.4), register their progress message so the worker notifies them on completion,
  and tell them it is already being prepared. Multi-recipient delivery happens in the
  worker's ``DownloadService._deliver`` (Task 7.1/7.2).

The Redis download lock is acquired here and *released by the worker* on completion
(W11); its token travels in the job context so the worker can compare-and-delete it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Any

from core import metrics
from core.config import Settings
from core.constants import PRIORITY_NORMAL
from core.i18n import resolve_locale
from core.logging import get_logger
from core.uuid7 import uuid7
from domain.entities.media import MediaInfo
from domain.enums import JobStatus, MediaFormat, Quality
from domain.exceptions import CachedFileExpiredError
from domain.protocols.advertising import AdButtonSpec
from domain.protocols.file_sender import FileSenderProtocol
from domain.protocols.repositories import (
    ActiveDownloadRepositoryProtocol,
    CachedFileRepositoryProtocol,
    DownloadRepositoryProtocol,
    JobRepositoryProtocol,
    JobWaiterRepositoryProtocol,
    UserRepositoryProtocol,
)
from services.cache_service import CacheService
from services.caption_ad_mixer import CaptionAdMixer
from services.notification_service import NotificationService
from services.queue_service import QueueService

_log = get_logger("services.job_service")


class RequestKind(StrEnum):
    CACHED = auto()
    QUEUED = auto()
    DUPLICATE = auto()
    BUSY = auto()  # free user already has an in-flight download (single-active cap)


@dataclass(frozen=True, slots=True)
class RequestOutcome:
    """What ``JobService.request`` decided. ``job_id`` is set for QUEUED/DUPLICATE."""

    kind: RequestKind
    job_id: str | None = None


class JobService:
    def __init__(
        self,
        *,
        job_repo: JobRepositoryProtocol[Any],
        cached_file_repo: CachedFileRepositoryProtocol[Any],
        active_download_repo: ActiveDownloadRepositoryProtocol[Any],
        job_waiter_repo: JobWaiterRepositoryProtocol[Any],
        download_repo: DownloadRepositoryProtocol[Any],
        user_repo: UserRepositoryProtocol[Any],
        queue_service: QueueService,
        cache_service: CacheService,
        file_sender: FileSenderProtocol,
        notification_service: NotificationService,
        settings: Settings,
        caption_mixer: CaptionAdMixer | None = None,
    ) -> None:
        self._jobs = job_repo
        self._cached = cached_file_repo
        self._active = active_download_repo
        self._waiters = job_waiter_repo
        self._downloads = download_repo
        self._users = user_repo
        self._queue = queue_service
        self._cache = cache_service
        self._file_sender = file_sender
        self._notifier = notification_service
        self._settings = settings
        self._caption_mixer = caption_mixer

    async def request(
        self,
        *,
        user_id: int,
        telegram_id: int,
        media_id: int,
        info: MediaInfo,
        format_: MediaFormat,
        quality: Quality,
        progress_message_id: int,
        correlation_id: uuid.UUID | None = None,
        single_active: bool = False,
    ) -> RequestOutcome:
        fmt, qual = format_.value, quality.value
        token = await self._cache.acquire_download_lock(media_id, fmt, qual)

        cached = await self._cached.get_by_media_format_quality(media_id, fmt, qual)
        if cached is not None:
            delivered = await self._try_deliver_cached(
                media_id, user_id, telegram_id, info, format_, quality, cached, progress_message_id
            )
            if delivered:
                await self._release_lock(media_id, fmt, qual, token)
                return RequestOutcome(RequestKind.CACHED)
            # The cached file_id was rejected as invalid (e.g. minted by a different
            # bot/API server, or expired) — it was evicted; fall through and download
            # it fresh, keeping the lock we already hold.

        # Single-active-job cap (free users): only a cache miss creates a queued job, so
        # the guard sits here — instant cache hits above are never blocked. A free user
        # with an in-flight job cannot start a second download (16-free-cap, spam guard).
        # The window bounds it to *recent* jobs so a stuck/orphaned job ages out instead
        # of blocking forever (#24); the dead job is reaped separately in Sprint 10.
        if single_active and (
            await self._jobs.count_active_for_user(
                user_id, within_seconds=self._settings.worker_job_timeout
            )
            > 0
        ):
            await self._release_lock(media_id, fmt, qual, token)
            _log.info("job_rejected_user_busy", user_id=user_id)
            return RequestOutcome(RequestKind.BUSY)

        job_id = uuid7()
        claimed = await self._active.insert_if_absent(
            media_id=media_id, format_=fmt, quality=qual, job_id=job_id
        )
        if not claimed:
            existing = await self._active.get_by_media_format_quality(media_id, fmt, qual)
            await self._release_lock(media_id, fmt, qual, token)
            if existing is None:  # conflict cleared between insert and read — rare
                return RequestOutcome(RequestKind.DUPLICATE)
            await self._waiters.add_waiter(
                job_id=existing.job_id, user_id=user_id, correlation_id=correlation_id
            )
            # Fan-out (16.4): register this waiter's progress message so the worker
            # edits it to ✅/❌ alongside the originator's on completion (Task 7.1).
            await self._cache.add_waiter_progress(
                str(existing.job_id), user_id, telegram_id, progress_message_id
            )
            _log.info("job_duplicate_attached", job_id=str(existing.job_id), user_id=user_id)
            return RequestOutcome(RequestKind.DUPLICATE, job_id=str(existing.job_id))

        await self._jobs.create(
            job_id=job_id,
            user_id=user_id,
            media_id=media_id,
            format_=fmt,
            quality=qual,
            priority=PRIORITY_NORMAL,
            correlation_id=correlation_id,
            status=JobStatus.QUEUED.value,
        )
        metrics.record_job_created()
        await self._waiters.add_waiter(
            job_id=job_id, user_id=user_id, correlation_id=correlation_id
        )
        await self._cache.set_job_context(
            str(job_id),
            {
                "telegram_id": telegram_id,
                "message_id": progress_message_id,
                "lock_token": token,
                "media_id": media_id,
                "platform": info.platform,
                "title": info.title,
                "format": fmt,
                "quality": qual,
                # Per-waiter progress messages, keyed by user id. The originator is the
                # first waiter; fan-out duplicates append themselves (16.4, Task 7.1).
                "progress": {
                    str(user_id): {"telegram_id": telegram_id, "message_id": progress_message_id}
                },
            },
            ttl=self._settings.cache_lock_ttl,
        )
        await self._queue.enqueue(str(job_id), priority=PRIORITY_NORMAL)
        _log.info("job_queued", job_id=str(job_id), user_id=user_id, format=fmt, quality=qual)
        return RequestOutcome(RequestKind.QUEUED, job_id=str(job_id))

    async def _caption_addon(
        self, user_id: int, base: str | None
    ) -> tuple[str | None, tuple[AdButtonSpec, ...]]:
        """Base caption + any due caption-layer ad for the requester (two-layer ads)."""
        if self._caption_mixer is None:
            return base, ()
        user = await self._users.get_by_id(user_id)
        if user is None:
            return base, ()
        # Cache-hit counters bump *after* delivery, so the caption ad's every-N sees the
        # post-increment total (consistent with the follow-up layer, D-010).
        return await self._caption_mixer.decorate_for_user(user, base, user.total_downloads + 1)

    async def _try_deliver_cached(
        self,
        media_id: int,
        user_id: int,
        telegram_id: int,
        info: MediaInfo,
        format_: MediaFormat,
        quality: Quality,
        cached: Any,
        progress_message_id: int,
    ) -> bool:
        """Deliver from cache (16.2). Returns False if the file_id was invalid+evicted.

        Delivery is attempted **first**: only after the file actually reaches the user
        do we record the download, bump counters, and edit the progress message to ✅.
        If Telegram rejects the cached ``file_id`` (a different bot/API server minted
        it, or it expired), the stale ``cached_files`` row + Redis key are evicted and
        the caller re-downloads it fresh.
        """
        cached_id: int = cached.id
        file_id: str = cached.telegram_file_id
        file_size: int | None = cached.file_size
        caption, buttons = await self._caption_addon(user_id, info.title)
        try:
            await self._file_sender.send_cached(
                telegram_id,
                file_id,
                format_=format_,
                quality=quality,
                caption=caption,
                buttons=buttons,
            )
        except CachedFileExpiredError:
            await self._cached.delete(cached)
            await self._cache.delete_file_id(media_id, format_.value, quality.value)
            _log.warning(
                "cache_file_expired_refetching",
                media_id=media_id,
                format=format_.value,
                quality=quality.value,
            )
            return False

        await self._cached.bump_usage(cached_id)
        await self._cache.set_file_id(media_id, format_.value, quality.value, file_id)
        await self._downloads.create_completed(
            user_id=user_id,
            cached_file_id=cached_id,
            platform=info.platform,
            format_=format_.value,
            quality=quality.value,
            file_size=file_size,
            title=info.title,
            duration_seconds=info.duration,
            size_bytes=file_size,
        )
        await self._users.increment_download_counters(user_id)
        # Invalidate the user snapshot so the next rate-limit read sees the new count
        # (otherwise the cached daily_download_count is stale for up to CACHE_USER_TTL).
        await self._cache.delete_user(telegram_id)
        requester = await self._users.get_by_id(user_id)
        locale = resolve_locale(requester.language if requester is not None else None)
        await self._notifier.notify_completed(telegram_id, progress_message_id, locale)
        _log.info("cache_hit_delivered", user_id=user_id, quality=quality.value)
        # TODO(Sprint 9, Task 9.3): AdService.maybe_show(user) after delivery.
        return True

    async def _release_lock(self, media_id: int, fmt: str, qual: str, token: str | None) -> None:
        if token is not None:
            await self._cache.release_download_lock(media_id, fmt, qual, token)
