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
    """The slice of the downloads repository the admin reads (User Info + analytics)."""

    async def count_for_user(self, user_id: int) -> int: ...

    async def count_by_platform(
        self, *, since: datetime.datetime | None = None
    ) -> list[tuple[str, int]]: ...

    async def total_count(self, *, since: datetime.datetime | None = None) -> int: ...


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
class PlatformCount:
    """One platform's download tally and its share of the period total (13.3)."""

    platform: str
    count: int
    share_pct: float


@dataclass(frozen=True, slots=True)
class PlatformStatsView:
    """Per-platform download breakdown for one period, sorted by count DESC (13.3)."""

    platforms: list[PlatformCount]
    total: int
    period: str


@dataclass(frozen=True, slots=True)
class PlatformReportRow:
    """One platform's counts across all periods for the CSV export (13.3)."""

    platform: str
    today: int
    week: int
    month: int
    all_time: int
    share_pct: float


@dataclass(frozen=True, slots=True)
class PlatformReport:
    """The multi-period per-platform report backing the CSV export (13.3)."""

    rows: list[PlatformReportRow]
    total_all_time: int


# Period tokens accepted by get_platform_stats (SPRINT_13_PLAN §13.3).
_VALID_PERIODS: frozenset[str] = frozenset({"today", "week", "month", "all"})


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

    async def get_platform_stats(self, *, period: str = "all") -> PlatformStatsView:
        """Per-platform download breakdown for a period (13.3).

        ``period`` is ``today`` | ``week`` | ``month`` | ``all``; an unknown value is
        treated as ``all`` (fail-open to the widest, non-destructive view).
        """
        if period not in _VALID_PERIODS:
            period = "all"
        pairs = await self._downloads.count_by_platform(since=_since_for_period(period))
        total = sum(count for _, count in pairs)
        platforms = [
            PlatformCount(
                platform=platform,
                count=count,
                share_pct=(count / total * 100.0) if total else 0.0,
            )
            for platform, count in pairs
        ]
        return PlatformStatsView(platforms=platforms, total=total, period=period)

    async def get_platform_report(self) -> PlatformReport:
        """Per-platform counts across today/week/month/all-time for CSV export (13.3)."""
        by_period = {
            name: dict(await self._downloads.count_by_platform(since=_since_for_period(name)))
            for name in ("today", "week", "month", "all")
        }
        all_time = by_period["all"]
        total = sum(all_time.values())
        rows = [
            PlatformReportRow(
                platform=platform,
                today=by_period["today"].get(platform, 0),
                week=by_period["week"].get(platform, 0),
                month=by_period["month"].get(platform, 0),
                all_time=count,
                share_pct=(count / total * 100.0) if total else 0.0,
            )
            for platform, count in sorted(all_time.items(), key=lambda kv: kv[1], reverse=True)
        ]
        return PlatformReport(rows=rows, total_all_time=total)


def _since_for_period(period: str) -> datetime.datetime | None:
    """Map a period token to its inclusive lower bound (``None`` = all time)."""
    now = datetime.datetime.now(datetime.UTC)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return now - datetime.timedelta(days=7)
    if period == "month":
        return now - datetime.timedelta(days=30)
    return None


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
