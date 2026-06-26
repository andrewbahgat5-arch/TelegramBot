"""AdminService (MASTER_PLAN Component 9.2, Task 8.3).

Read-only query hub for the two HTTP admin surfaces that no existing service owns:
the jobs listing (``GET /v1/admin/jobs``) and the error-log browse
(``GET /v1/admin/errors``). The other admin endpoints delegate to their existing
owners — ``UserService`` (stats / users / ban / unban), ``SettingsService`` (settings
list + update) and ``QueueService`` (queue summary) — so this service exists *only*
for the job/error reads.

It depends on **narrow read protocols** (``JobReadRepository`` /
``ErrorReadRepository``) rather than the broad repository protocols, so it never pulls
in the heavy ``JobService`` transport dependencies (file sender, notifier) just to list
rows. Concrete repositories satisfy these structurally. The service is framework-free
(Section 8): it returns immutable view dataclasses built by attribute access only,
never ORM rows or aiogram types.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class JobReadRepository(Protocol):
    """The slice of the jobs repository the admin listing needs."""

    async def list_recent(
        self, *, limit: int = 50, offset: int = 0, status: str | None = None
    ) -> Sequence[Any]: ...

    async def count_active_for_user(
        self, user_id: int, *, within_seconds: int | None = None
    ) -> int: ...


class ErrorReadRepository(Protocol):
    """The slice of the error-log repository the admin browse needs."""

    async def list_recent(
        self, *, limit: int = 50, offset: int = 0, error_type: str | None = None
    ) -> Sequence[Any]: ...


class DownloadReadRepository(Protocol):
    """The slice of the downloads repository the admin User Info view needs."""

    async def count_for_user(self, user_id: int) -> int: ...


@dataclass(frozen=True, slots=True)
class JobView:
    """An immutable ``jobs`` row view for the admin ``/jobs`` surface (10.6)."""

    id: str
    user_id: int
    media_id: int
    format: str
    quality: str
    status: str
    priority: int
    retry_count: int
    error_message: str | None
    created_at: datetime.datetime
    started_at: datetime.datetime | None
    finished_at: datetime.datetime | None


@dataclass(frozen=True, slots=True)
class ErrorLogView:
    """An immutable ``error_logs`` row view for the admin ``/errors`` browse (10.12)."""

    id: int
    user_id: int | None
    job_id: str | None
    correlation_id: str | None
    error_type: str
    message: str
    created_at: datetime.datetime


class AdminService:
    def __init__(
        self,
        *,
        job_repo: JobReadRepository,
        error_repo: ErrorReadRepository,
        download_repo: DownloadReadRepository,
    ) -> None:
        self._jobs = job_repo
        self._errors = error_repo
        self._downloads = download_repo

    async def list_jobs(
        self, *, limit: int = 50, offset: int = 0, status: str | None = None
    ) -> list[JobView]:
        """A page of recent jobs (newest first), optionally filtered by ``status``."""
        rows = await self._jobs.list_recent(limit=limit, offset=offset, status=status)
        return [_job_view(row) for row in rows]

    async def browse_errors(
        self, *, limit: int = 50, offset: int = 0, error_type: str | None = None
    ) -> list[ErrorLogView]:
        """A page of recent error logs (newest first), optionally filtered by type."""
        rows = await self._errors.list_recent(limit=limit, offset=offset, error_type=error_type)
        return [_error_view(row) for row in rows]

    async def count_user_downloads(self, user_id: int) -> int:
        """Lifetime download-history count for one user (admin User Info, Sprint 9.6)."""
        return await self._downloads.count_for_user(user_id)

    async def count_user_active_jobs(self, user_id: int) -> int:
        """In-flight job count for one user (admin User Info, Sprint 9.6)."""
        return await self._jobs.count_active_for_user(user_id)


def _job_view(row: Any) -> JobView:
    return JobView(
        id=str(row.id),
        user_id=row.user_id,
        media_id=row.media_id,
        format=row.format,
        quality=row.quality,
        status=row.status,
        priority=row.priority,
        retry_count=row.retry_count,
        error_message=row.error_message,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _error_view(row: Any) -> ErrorLogView:
    return ErrorLogView(
        id=row.id,
        user_id=row.user_id,
        job_id=None if row.job_id is None else str(row.job_id),
        correlation_id=None if row.correlation_id is None else str(row.correlation_id),
        error_type=row.error_type,
        message=row.message,
        created_at=row.created_at,
    )
