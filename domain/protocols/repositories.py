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
    async def reset_daily_download_count_if_needed(
        self, user: T, *, today: datetime.date | None = None
    ) -> T: ...


class MediaRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_platform_video(self, platform: str, video_id: str) -> T | None: ...


class CachedFileRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_media_format_quality(
        self, media_id: int, format_: str, quality: str
    ) -> T | None: ...


class JobRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_uuid(self, job_id: uuid.UUID) -> T | None: ...


class ActiveDownloadRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_media_format_quality(
        self, media_id: int, format_: str, quality: str
    ) -> T | None: ...


class JobWaiterRepositoryProtocol(Repository[T], Protocol[T]):
    async def list_for_job(self, job_id: uuid.UUID) -> Sequence[T]: ...
    async def delete_for_job(self, job_id: uuid.UUID) -> int: ...


class SettingsRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_key(self, key: str) -> T | None: ...
    async def upsert(self, key: str, value: str, *, updated_by: int | None = None) -> T: ...


class DownloadRepositoryProtocol(Repository[T], Protocol[T]):
    async def list_for_user(
        self, user_id: int, *, limit: int = 10, offset: int = 0
    ) -> Sequence[T]: ...


class BroadcastRepositoryProtocol(Repository[T], Protocol[T]): ...


class AdRepositoryProtocol(Repository[T], Protocol[T]): ...


class ErrorLogRepositoryProtocol(Repository[T], Protocol[T]): ...


class UserPreferenceRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_user_id(self, user_id: int) -> T | None: ...
