"""Unit tests for AdminService (MASTER_PLAN Task 8.3).

Covers the row→view mapping the HTTP admin API relies on: UUID stringification for
job/error ids and None-handling for optional fields, plus pass-through of the
limit/offset/filter arguments to the narrow read repositories.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import pytest

from services.admin_service import AdminService

pytestmark = pytest.mark.asyncio

_NOW = datetime.datetime(2026, 6, 25, 12, 0, tzinfo=datetime.UTC)


class _Row:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


class _FakeJobRepo:
    def __init__(self, rows: list[_Row], *, active: int = 0) -> None:
        self.rows = rows
        self.active = active
        self.calls: list[dict[str, Any]] = []

    async def list_recent(self, **kw: Any) -> list[_Row]:
        self.calls.append(kw)
        return self.rows

    async def count_active_for_user(
        self, user_id: int, *, within_seconds: int | None = None
    ) -> int:
        return self.active


class _FakeErrorRepo:
    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    async def list_recent(self, **kw: Any) -> list[_Row]:
        self.calls.append(kw)
        return self.rows


class _FakeDownloadRepo:
    def __init__(self, count: int = 0) -> None:
        self.count = count

    async def count_for_user(self, user_id: int) -> int:
        return self.count


def _admin(
    *,
    job_repo: Any = None,
    error_repo: Any = None,
    download_repo: Any = None,
) -> AdminService:
    return AdminService(
        job_repo=job_repo or _FakeJobRepo([]),
        error_repo=error_repo or _FakeErrorRepo([]),
        download_repo=download_repo or _FakeDownloadRepo(),
    )


def _job_row() -> _Row:
    return _Row(
        id=uuid.UUID("01910000-0000-7000-8000-000000000001"),
        user_id=7,
        media_id=42,
        format="video",
        quality="720p",
        status="completed",
        priority=1000,
        retry_count=1,
        error_message=None,
        created_at=_NOW,
        started_at=_NOW,
        finished_at=_NOW,
    )


async def test_list_jobs_maps_uuid_to_str_and_passes_filters() -> None:
    repo = _FakeJobRepo([_job_row()])
    service = _admin(job_repo=repo)

    views = await service.list_jobs(limit=5, offset=2, status="completed")

    assert len(views) == 1
    view = views[0]
    assert view.id == "01910000-0000-7000-8000-000000000001"
    assert view.user_id == 7 and view.status == "completed"
    assert repo.calls == [{"limit": 5, "offset": 2, "status": "completed"}]


async def test_browse_errors_stringifies_optional_uuids() -> None:
    job_id = uuid.UUID("01910000-0000-7000-8000-0000000000aa")
    rows = [
        _Row(
            id=1,
            user_id=None,
            job_id=job_id,
            correlation_id=None,
            error_type="provider_error",
            message="boom",
            created_at=_NOW,
        )
    ]
    repo = _FakeErrorRepo(rows)
    service = _admin(error_repo=repo)

    views = await service.browse_errors(limit=10, error_type="provider_error")

    assert len(views) == 1
    view = views[0]
    assert view.job_id == str(job_id)
    assert view.user_id is None and view.correlation_id is None
    assert repo.calls == [{"limit": 10, "offset": 0, "error_type": "provider_error"}]


async def test_count_user_downloads_and_active_jobs() -> None:
    service = _admin(job_repo=_FakeJobRepo([], active=2), download_repo=_FakeDownloadRepo(count=37))
    assert await service.count_user_downloads(7) == 37
    assert await service.count_user_active_jobs(7) == 2
