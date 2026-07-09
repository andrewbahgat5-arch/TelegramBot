"""HistoryService (MASTER_PLAN Component 9.2, Task 7.3, flow 16.3).

Reads a user's download history and re-sends a past download on demand.

* **List** — paginated, newest-first read of ``downloads`` (denormalized
  platform/format/quality/size/date, so no joins are needed to render a page).
* **Resend** — deliver a past download again. When the file is still cached
  (``cached_files`` row present and Telegram accepts the ``file_id``) the resend is
  instant and records **no** new ``downloads`` row (resends do not duplicate history,
  16.3 step 5); only ``cached_files.usage_count`` is bumped. If Telegram rejects the
  ``file_id`` (a different bot/API server minted it, or it expired) the stale cache is
  evicted and we fall back to a fresh download via ``JobService.request`` — the new
  job's completion is the user's resend (16.3 step 4).

Schema note (surfaced for Owner review): ``downloads`` (§10.5) carries no ``media_id``
column, so a row whose ``cached_file_id`` is NULL (its ``cached_files`` parent was
deleted, FK ``ON DELETE SET NULL``) cannot be reconstructed into a fresh download —
there is nothing left to point at the source media. Those resends return
``NEEDS_RELINK`` (ask the user to send the link again). The feasible fallback path
(cache row present but the ``file_id`` is rejected) reuses ``cached_files.media_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Any

from core.logging import get_logger
from domain.entities.user import UserSnapshot
from domain.enums import MediaFormat, Quality
from domain.exceptions import CachedFileExpiredError
from domain.protocols.advertising import AdButtonSpec
from domain.protocols.file_sender import FileSenderProtocol
from domain.protocols.repositories import (
    CachedFileRepositoryProtocol,
    DownloadRepositoryProtocol,
)
from services.cache_service import CacheService
from services.caption_ad_mixer import CaptionAdMixer
from services.job_service import JobService, RequestKind
from services.settings_service import SettingNotFoundError, SettingsService
from services.url_analyzer import URLAnalyzerService

_log = get_logger("services.history_service")

_PAGE_SIZE_KEY = "history_page_size"
_DEFAULT_PAGE_SIZE = 7


class ResendKind(StrEnum):
    RESENT = auto()
    REQUEUED = auto()
    NEEDS_RELINK = auto()
    NOT_FOUND = auto()


@dataclass(frozen=True, slots=True)
class HistoryPage:
    """One page of a user's history, newest first."""

    rows: list[Any]
    page: int
    has_prev: bool
    has_next: bool
    format_filter: str | None = None
    audio_count: int = 0
    video_count: int = 0


class HistoryService:
    def __init__(
        self,
        *,
        download_repo: DownloadRepositoryProtocol[Any],
        cached_file_repo: CachedFileRepositoryProtocol[Any],
        job_service: JobService,
        analyzer: URLAnalyzerService,
        file_sender: FileSenderProtocol,
        cache_service: CacheService,
        settings_service: SettingsService,
        caption_mixer: CaptionAdMixer | None = None,
    ) -> None:
        self._downloads = download_repo
        self._cached = cached_file_repo
        self._jobs = job_service
        self._analyzer = analyzer
        self._file_sender = file_sender
        self._cache = cache_service
        self._settings = settings_service
        self._caption_mixer = caption_mixer

    async def list_history(
        self,
        user_id: int,
        *,
        page: int = 0,
        format_filter: str | None = None,
    ) -> HistoryPage:
        page = max(0, page)
        page_size = await self._page_size()
        rows = list(
            await self._downloads.list_for_user(
                user_id,
                limit=page_size + 1,
                offset=page * page_size,
                format_filter=format_filter,
            )
        )
        has_next = len(rows) > page_size
        counts = await self._downloads.count_by_format(user_id)
        return HistoryPage(
            rows=rows[:page_size],
            page=page,
            has_prev=page > 0,
            has_next=has_next,
            format_filter=format_filter,
            audio_count=counts.get("audio", 0),
            video_count=counts.get("video", 0),
        )

    async def _page_size(self) -> int:
        try:
            size: int = await self._settings.get(_PAGE_SIZE_KEY)
        except SettingNotFoundError:
            return _DEFAULT_PAGE_SIZE
        return size

    async def _caption_addon(
        self, user: UserSnapshot | None
    ) -> tuple[str | None, tuple[AdButtonSpec, ...]]:
        if self._caption_mixer is None or user is None:
            return None, ()
        return await self._caption_mixer.decorate_for_user(user, None, user.total_downloads)

    async def resend(
        self,
        *,
        download_id: int,
        user_id: int,
        telegram_id: int,
        progress_message_id: int,
        user: UserSnapshot | None = None,
    ) -> ResendKind:
        download = await self._downloads.get_for_user(download_id, user_id)
        if download is None:
            return ResendKind.NOT_FOUND
        if download.cached_file_id is None:
            return ResendKind.NEEDS_RELINK

        cached = await self._cached.get_by_id(download.cached_file_id)
        if cached is None:
            return ResendKind.NEEDS_RELINK

        format_ = MediaFormat(download.format)
        quality = Quality(download.quality)
        caption, buttons = await self._caption_addon(user)
        try:
            await self._file_sender.send_cached(
                telegram_id,
                cached.telegram_file_id,
                format_=format_,
                quality=quality,
                caption=caption,
                buttons=buttons,
            )
        except CachedFileExpiredError:
            return await self._resend_fallback(
                cached, format_, quality, user_id, telegram_id, progress_message_id
            )

        await self._cached.bump_usage(cached.id)
        _log.info("history_resent_from_cache", user_id=user_id, download_id=download_id)
        return ResendKind.RESENT

    async def _resend_fallback(
        self,
        cached: Any,
        format_: MediaFormat,
        quality: Quality,
        user_id: int,
        telegram_id: int,
        progress_message_id: int,
    ) -> ResendKind:
        media_id: int = cached.media_id
        await self._cached.delete(cached)
        await self._cache.delete_file_id(media_id, format_.value, quality.value)
        analyzed = await self._analyzer.analyze_by_media_id(media_id)
        if analyzed is None:
            _log.warning("history_resend_media_gone", user_id=user_id, media_id=media_id)
            return ResendKind.NEEDS_RELINK
        outcome = await self._jobs.request(
            user_id=user_id,
            telegram_id=telegram_id,
            media_id=media_id,
            info=analyzed.info,
            format_=format_,
            quality=quality,
            progress_message_id=progress_message_id,
        )
        _log.info("history_resend_requeued", user_id=user_id, media_id=media_id)
        return ResendKind.RESENT if outcome.kind is RequestKind.CACHED else ResendKind.REQUEUED
