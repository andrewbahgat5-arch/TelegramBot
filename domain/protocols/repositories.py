"""Repository protocols (MASTER_PLAN Task 2.6, Component 9.4).

These interfaces are what the service layer depends on. They are deliberately
model-agnostic — ``domain`` may not import ``infrastructure`` (Section 8) — so each
protocol is generic over the entity type ``T`` that the concrete repository binds.
Concrete repositories in ``infrastructure/database/repositories`` satisfy these
structurally.

Repositories never commit; they ``add``/``flush`` only. The unit of work is owned
by the entry point (e.g. ``DbSessionMiddleware``).
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Sequence
from typing import Any, Protocol, TypeVar

T = TypeVar("T")


class Repository(Protocol[T]):
    """Common CRUD surface shared by all repositories."""

    async def add(self, entity: T) -> T: ...
    async def get_by_id(self, id_: Any) -> T | None: ...
    async def list_paginated(self, *, limit: int = 50, offset: int = 0) -> Sequence[T]: ...
    async def delete(self, entity: T) -> None: ...


class UserRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_telegram_id(self, telegram_id: int) -> T | None: ...
    async def create_user(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        language: str | None,
        role: str,
    ) -> T: ...
    async def touch_last_activity(self, telegram_id: int, when: datetime.datetime) -> None: ...
    async def reset_daily_download_count_if_needed(
        self, user: T, *, today: datetime.date | None = None
    ) -> T: ...
    async def increment_download_counters(
        self, user_id: int, *, today: datetime.date | None = None
    ) -> None:
        """Atomic, lazy-reset counter bump for one completed download (16.6, D-012)."""
        ...

    async def count_all(self) -> int:
        """Total registered users (admin /stats)."""
        ...

    async def count_banned(self) -> int:
        """Currently-banned users (admin /stats)."""
        ...

    async def sum_total_downloads(self) -> int:
        """Lifetime delivered-download count across all users (admin /stats)."""
        ...

    async def count_for_broadcast(self, *, role: str | None, language: str | None) -> int:
        """Count the non-banned audience matching the broadcast filters (16.8)."""
        ...

    async def page_for_broadcast(
        self, *, after_id: int, limit: int, role: str | None, language: str | None
    ) -> Sequence[T]:
        """One id-cursor page of the non-banned broadcast audience, ascending (16.8)."""
        ...


class MediaRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_platform_video(self, platform: str, video_id: str) -> T | None: ...
    async def upsert_metadata(
        self,
        *,
        platform: str,
        video_id: str,
        title: str,
        source_url: str,
        duration: int | None = None,
        thumbnail_url: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> T: ...


class CachedFileRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_media_format_quality(
        self, media_id: int, format_: str, quality: str
    ) -> T | None: ...
    async def upsert(
        self,
        *,
        media_id: int,
        format_: str,
        quality: str,
        telegram_file_id: str,
        telegram_unique_file_id: str,
        file_size: int | None,
    ) -> T:
        """UPSERT on ``(media_id, format, quality)``; bump usage + last_used (16.1 W5)."""
        ...

    async def bump_usage(self, cached_file_id: int) -> None:
        """Increment usage_count and refresh last_used_at on a cache hit (16.2)."""
        ...


class JobRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_uuid(self, job_id: uuid.UUID) -> T | None: ...
    async def create(
        self,
        *,
        job_id: uuid.UUID,
        user_id: int,
        media_id: int,
        format_: str,
        quality: str,
        priority: int,
        correlation_id: uuid.UUID | None,
        status: str,
    ) -> T:
        """Insert a ``jobs`` row with an app-generated UUIDv7 id (D-013)."""
        ...

    async def set_status(
        self,
        job_id: uuid.UUID,
        status: str,
        *,
        started_at: datetime.datetime | None = None,
        finished_at: datetime.datetime | None = None,
        error_message: str | None = None,
        increment_retry: bool = False,
    ) -> None:
        """Advance a job's state machine (Section 12.3) by id (UPDATE only)."""
        ...


class ActiveDownloadRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_media_format_quality(
        self, media_id: int, format_: str, quality: str
    ) -> T | None: ...
    async def insert_if_absent(
        self, *, media_id: int, format_: str, quality: str, job_id: uuid.UUID
    ) -> bool:
        """INSERT ON CONFLICT DO NOTHING; True if inserted, False on duplicate (16.1)."""
        ...

    async def delete_by_job(self, job_id: uuid.UUID) -> int:
        """Remove the active-download marker for a finished job (16.1 W9)."""
        ...


class JobWaiterRepositoryProtocol(Repository[T], Protocol[T]):
    async def list_for_job(self, job_id: uuid.UUID) -> Sequence[T]: ...
    async def delete_for_job(self, job_id: uuid.UUID) -> int: ...
    async def add_waiter(
        self, *, job_id: uuid.UUID, user_id: int, correlation_id: uuid.UUID | None
    ) -> bool:
        """INSERT ON CONFLICT (job_id,user_id) DO NOTHING; True if newly added (12.4)."""
        ...


class SettingsStoreProtocol(Protocol):
    """The settings persistence surface that ``SettingsService`` depends on.

    Returns are ``Any`` (a settings-row-like object exposing ``value: str`` and
    ``value_type: str``). ``Any`` avoids coupling the protocol to the ORM model,
    whose ``Mapped[str]`` columns do not structurally match a ``str`` attribute.
    """

    async def get_by_key(self, key: str) -> Any: ...
    async def upsert(self, key: str, value: str, *, updated_by: int | None = None) -> Any: ...
    async def list_all(self) -> Sequence[Any]:
        """Every settings row (admin ``/settings`` listing). Rows expose ``key``/``value``."""
        ...


class SettingsRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_key(self, key: str) -> T | None: ...
    async def upsert(self, key: str, value: str, *, updated_by: int | None = None) -> T: ...


class DownloadRepositoryProtocol(Repository[T], Protocol[T]):
    async def list_for_user(
        self, user_id: int, *, limit: int = 10, offset: int = 0
    ) -> Sequence[T]: ...
    async def get_for_user(self, download_id: int, user_id: int) -> T | None:
        """Fetch one history row by id, scoped to its owner (resend, 16.3)."""
        ...

    async def create_completed(
        self,
        *,
        user_id: int,
        cached_file_id: int | None,
        platform: str,
        format_: str,
        quality: str,
        file_size: int | None,
        status: str = "completed",
    ) -> T:
        """Insert a denormalized history row for a delivered download (10.5, 16.1 W7)."""
        ...


class BroadcastRepositoryProtocol(Repository[T], Protocol[T]):
    async def create_pending(
        self,
        *,
        created_by: int,
        message_text: str,
        target_language: str | None,
        target_role: str | None,
        expected_total: int,
    ) -> T:
        """Insert a ``broadcasts`` row in ``pending`` state for the worker (10.9, 16.8)."""
        ...

    async def get_next_pending(self) -> T | None:
        """Oldest ``pending`` broadcast for the worker to process (16.8)."""
        ...

    async def set_status(
        self, broadcast_id: int, status: str, *, completed_at: datetime.datetime | None = None
    ) -> None:
        """Advance a broadcast's lifecycle (pending → in_progress → completed)."""
        ...

    async def add_counts(self, broadcast_id: int, *, sent: int, failed: int) -> None:
        """Increment ``total_sent`` / ``total_failed`` after a delivered chunk (16.8)."""
        ...


class AdRepositoryProtocol(Repository[T], Protocol[T]): ...


class ErrorLogRepositoryProtocol(Repository[T], Protocol[T]): ...


class UserPreferenceRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_user_id(self, user_id: int) -> T | None: ...
