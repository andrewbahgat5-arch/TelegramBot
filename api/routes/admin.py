"""HTTP admin API routes (MASTER_PLAN Task 8.3, Section 20.2 / 20.3, D-051).

The LOCKED Section 20.2 ``/v1/admin/*`` surface. Every route parses, delegates to an
existing service, and formats — no business logic lives here (Section 1.5.1):

* ``UserService`` — stats, users list/search, user detail, ban, unban.
* ``SettingsService`` — settings list, settings update.
* ``QueueService`` — queue summary (also feeds ``/stats``).
* ``AdminService`` — jobs listing, error-log browse (the two reads no other service owns).

**Authorization (Section 20.3, owner/key-gated).** The whole surface is gated by a
single ``ADMIN_API_KEY``: this router is only mounted when the key is configured, so
when it is unset every ``/v1/admin/*`` path 404s (the surface does not exist —
"silently ignored"). When it *is* set, a missing or wrong key yields ``401``. With a
single shared key there is no per-request HTTP identity, so the Section 20.2
"(owner only)" markers collapse to "valid-key-only" in V1 (the key is the owner's;
JWT identity arrives in V3 per Section 20.1).

This module imports ``services``/``domain``/``core`` only — never ``infrastructure``
(Section 8, import-linter ``entrypoints-not-infrastructure``). The composition root
``api/main.py`` builds the concrete session factory + service factories and injects
them into :func:`create_admin_router`.

NOTE: this module deliberately does **not** use ``from __future__ import annotations``.
The endpoints are defined inside :func:`create_admin_router` and inject request-scoped
dependencies via ``Annotated[..., Depends(...)]`` that close over local factories; with
stringized annotations FastAPI would resolve them against module globals only (missing
the closure locals) and mis-read them as query params. Eager (real) annotations let
the ``Depends``/``Security`` markers bind correctly. Self-referential model return
types are quoted so the class body still imports.
"""

import hmac
from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.entities.user import UserSnapshot
from services.admin_service import AdminService, ErrorLogView, JobView
from services.queue_service import QueueService
from services.settings_service import (
    InvalidSettingValueError,
    SettingNotFoundError,
    SettingsService,
    SettingView,
)
from services.user_service import UserService

UserServiceFactory = Callable[[AsyncSession], UserService]
SettingsServiceFactory = Callable[[AsyncSession], SettingsService]
AdminServiceFactory = Callable[[AsyncSession], AdminService]

_HEADER_NAME = "X-API-Key"
_MAX_PAGE = 200


# --- Response / request schemas -------------------------------------------------------


class StatsResponse(BaseModel):
    total_users: int
    banned_users: int
    total_downloads: int
    queue_depth: int
    active_downloads: int


class UserResponse(BaseModel):
    id: int
    telegram_id: int
    role: str
    is_banned: bool
    is_premium: bool
    daily_download_count: int
    total_downloads: int
    username: str | None
    first_name: str | None
    language: str | None
    ban_reason: str | None

    @classmethod
    def from_snapshot(cls, snap: UserSnapshot) -> "UserResponse":
        return cls(
            id=snap.id,
            telegram_id=snap.telegram_id,
            role=snap.role.value,
            is_banned=snap.is_banned,
            is_premium=snap.is_premium,
            daily_download_count=snap.daily_download_count,
            total_downloads=snap.total_downloads,
            username=snap.username,
            first_name=snap.first_name,
            language=snap.language,
            ban_reason=snap.ban_reason,
        )


class QueueResponse(BaseModel):
    depth: int
    active: int


class JobResponse(BaseModel):
    id: str
    user_id: int
    media_id: int
    format: str
    quality: str
    status: str
    priority: int
    retry_count: int
    error_message: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None

    @classmethod
    def from_view(cls, view: JobView) -> "JobResponse":
        return cls(
            id=view.id,
            user_id=view.user_id,
            media_id=view.media_id,
            format=view.format,
            quality=view.quality,
            status=view.status,
            priority=view.priority,
            retry_count=view.retry_count,
            error_message=view.error_message,
            created_at=view.created_at.isoformat(),
            started_at=None if view.started_at is None else view.started_at.isoformat(),
            finished_at=None if view.finished_at is None else view.finished_at.isoformat(),
        )


class ErrorResponse(BaseModel):
    id: int
    user_id: int | None
    job_id: str | None
    correlation_id: str | None
    error_type: str
    message: str
    created_at: str

    @classmethod
    def from_view(cls, view: ErrorLogView) -> "ErrorResponse":
        return cls(
            id=view.id,
            user_id=view.user_id,
            job_id=view.job_id,
            correlation_id=view.correlation_id,
            error_type=view.error_type,
            message=view.message,
            created_at=view.created_at.isoformat(),
        )


class SettingResponse(BaseModel):
    key: str
    value: str
    value_type: str

    @classmethod
    def from_view(cls, view: SettingView) -> "SettingResponse":
        return cls(key=view.key, value=view.value, value_type=view.value_type)


class BanRequest(BaseModel):
    reason: str | None = None


class SettingUpdateRequest(BaseModel):
    value: str


# --- Router factory -------------------------------------------------------------------


def create_admin_router(
    *,
    api_key: str,
    session_factory: async_sessionmaker[AsyncSession],
    user_service_factory: UserServiceFactory,
    settings_service_factory: SettingsServiceFactory,
    admin_service_factory: AdminServiceFactory,
    queue_service: QueueService,
) -> APIRouter:
    """Build the ``/v1/admin`` router. Mount only when ``api_key`` is non-empty."""
    header_scheme = APIKeyHeader(name=_HEADER_NAME, auto_error=False)

    async def require_key(provided: Annotated[str | None, Security(header_scheme)]) -> None:
        # Constant-time comparison so a wrong key cannot be probed via timing.
        if provided is None or not hmac.compare_digest(provided, api_key):
            raise HTTPException(status_code=401, detail="invalid or missing admin API key")

    async def get_session() -> AsyncIterator[AsyncSession]:
        # One unit of work per request: commit on success, roll back on any error. The
        # entry point owns the transaction boundary (repositories only add/flush).
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # A request-scoped session dependency. PascalCase: it is a type alias, not a value.
    SessionDep = Annotated[AsyncSession, Depends(get_session)]  # noqa: N806
    router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_key)])

    @router.get("/stats", response_model=StatsResponse)
    async def stats(session: SessionDep) -> StatsResponse:
        agg = await user_service_factory(session).get_stats()
        return StatsResponse(
            total_users=agg.total_users,
            banned_users=agg.banned_users,
            total_downloads=agg.total_downloads,
            queue_depth=await queue_service.depth(),
            active_downloads=await queue_service.active_count(),
        )

    @router.get("/users", response_model=list[UserResponse])
    async def list_users(
        session: SessionDep,
        telegram_id: Annotated[int | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=_MAX_PAGE)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[UserResponse]:
        service = user_service_factory(session)
        if telegram_id is not None:  # ?telegram_id= is exact-match search (Section 20.2)
            snap = await service.find(telegram_id)
            return [UserResponse.from_snapshot(snap)] if snap is not None else []
        snaps = await service.list_users(limit=limit, offset=offset)
        return [UserResponse.from_snapshot(snap) for snap in snaps]

    @router.get("/users/{telegram_id}", response_model=UserResponse)
    async def get_user(telegram_id: int, session: SessionDep) -> UserResponse:
        snap = await user_service_factory(session).find(telegram_id)
        if snap is None:
            raise HTTPException(status_code=404, detail="user not found")
        return UserResponse.from_snapshot(snap)

    @router.post("/users/{telegram_id}/ban", response_model=UserResponse)
    async def ban_user(
        telegram_id: int,
        session: SessionDep,
        body: Annotated[BanRequest | None, Body()] = None,
    ) -> UserResponse:
        reason = body.reason if body is not None else None
        snap = await user_service_factory(session).ban(telegram_id, reason)
        if snap is None:
            raise HTTPException(status_code=404, detail="user not found")
        return UserResponse.from_snapshot(snap)

    @router.post("/users/{telegram_id}/unban", response_model=UserResponse)
    async def unban_user(telegram_id: int, session: SessionDep) -> UserResponse:
        snap = await user_service_factory(session).unban(telegram_id)
        if snap is None:
            raise HTTPException(status_code=404, detail="user not found")
        return UserResponse.from_snapshot(snap)

    @router.get("/jobs", response_model=list[JobResponse])
    async def list_jobs(
        session: SessionDep,
        status: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=_MAX_PAGE)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[JobResponse]:
        views = await admin_service_factory(session).list_jobs(
            limit=limit, offset=offset, status=status
        )
        return [JobResponse.from_view(view) for view in views]

    @router.get("/queue", response_model=QueueResponse)
    async def queue_summary() -> QueueResponse:
        return QueueResponse(
            depth=await queue_service.depth(), active=await queue_service.active_count()
        )

    @router.get("/errors", response_model=list[ErrorResponse])
    async def browse_errors(
        session: SessionDep,
        error_type: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=_MAX_PAGE)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[ErrorResponse]:
        views = await admin_service_factory(session).browse_errors(
            limit=limit, offset=offset, error_type=error_type
        )
        return [ErrorResponse.from_view(view) for view in views]

    @router.get("/settings", response_model=list[SettingResponse])
    async def list_settings(session: SessionDep) -> list[SettingResponse]:
        views = await settings_service_factory(session).list_all()
        return [SettingResponse.from_view(view) for view in views]

    @router.put("/settings/{key}", response_model=SettingResponse)
    async def update_setting(
        key: str, body: SettingUpdateRequest, session: SessionDep
    ) -> SettingResponse:
        service = settings_service_factory(session)
        try:
            # updated_by is None: a single shared key has no per-request user identity.
            await service.set_validated(key, body.value, updated_by=None)
        except SettingNotFoundError:
            raise HTTPException(status_code=404, detail=f"unknown setting key: {key}") from None
        except InvalidSettingValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        view = await service.get_view(key)
        if view is None:  # pragma: no cover - set_validated just upserted this key
            raise HTTPException(status_code=404, detail=f"unknown setting key: {key}")
        return SettingResponse.from_view(view)

    return router
