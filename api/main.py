"""API composition root (MASTER_PLAN Component 8.2, Task 10.2 / 10.4, D-049).

The api process's single place that may import ``infrastructure`` (Section 8.2). It
wires the database engine, Redis clients, queue and worker-heartbeat views into the
readiness checker and the metrics live-gauge refresh, builds the FastAPI app, and
serves it with uvicorn. It also wires the ``/v1/admin/*`` surface (Task 8.3, D-051):
the admin router is mounted only when ``ADMIN_API_KEY`` is configured, otherwise those
paths 404. health/ready/metrics are always public.
"""

from __future__ import annotations

import uvicorn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.pool import QueuePool

from api.app import create_app
from api.readiness import ReadinessChecker
from api.routes.admin import create_admin_router
from core import metrics
from core.config import Settings
from core.logging import configure_logging, get_logger
from core.sentry import init_sentry, set_component
from infrastructure.database.engine import create_engine
from infrastructure.database.repositories.download import DownloadRepository
from infrastructure.database.repositories.error_log import ErrorLogRepository
from infrastructure.database.repositories.job import JobRepository
from infrastructure.database.repositories.setting import SettingsRepository
from infrastructure.database.repositories.user import UserRepository
from infrastructure.database.session import create_session_factory
from infrastructure.redis.cache import RedisCache
from infrastructure.redis.client import create_redis_clients
from infrastructure.redis.heartbeat import WorkerHeartbeat
from infrastructure.redis.locks import RedisLock
from infrastructure.redis.queue import RedisQueue
from services.admin_service import AdminService
from services.cache_service import CacheService
from services.queue_service import QueueService
from services.settings_service import SettingsService
from services.user_service import UserService

_log = get_logger("api.main")
_COMPONENT = "api"


def _pool_in_use(engine: AsyncEngine) -> int:
    """Connections checked out of the pool (0 for non-queue pools, e.g. NullPool)."""
    pool = engine.pool
    return pool.checkedout() if isinstance(pool, QueuePool) else 0


async def main() -> None:  # pragma: no cover - process entry; logic covered by unit tests
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level, settings.log_format)
    if settings.sentry_enabled:
        init_sentry(settings)
        set_component(_COMPONENT)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    redis_clients = create_redis_clients(settings)
    queue_service = QueueService(RedisQueue(redis_clients.queue))
    heartbeat = WorkerHeartbeat(redis_clients.cache)

    # Service factories for the admin API (Task 8.3). Process singletons (the Redis
    # cache + lock) are shared; per-request repositories bind to the request session.
    redis_cache = RedisCache(redis_clients.cache)
    cache_service = CacheService(redis_cache, RedisLock(redis_clients.cache), settings)

    def make_user_service(session: AsyncSession) -> UserService:
        return UserService(
            UserRepository(session),
            cache_service,
            owner_telegram_id=settings.bot_owner_telegram_id,
        )

    def make_settings_service(session: AsyncSession) -> SettingsService:
        return SettingsService(
            SettingsRepository(session), redis_cache, cache_ttl=settings.cache_settings_ttl
        )

    def make_admin_service(session: AsyncSession) -> AdminService:
        return AdminService(
            job_repo=JobRepository(session),
            error_repo=ErrorLogRepository(session),
            download_repo=DownloadRepository(session),
        )

    admin_router = None
    if settings.admin_api_enabled:
        admin_router = create_admin_router(
            api_key=settings.admin_api_key.get_secret_value(),
            session_factory=session_factory,
            user_service_factory=make_user_service,
            settings_service_factory=make_settings_service,
            admin_service_factory=make_admin_service,
            queue_service=queue_service,
        )
        _log.info("admin_api_enabled")
    else:
        # Key unset: the /v1/admin/* surface is not mounted, so those paths 404.
        _log.info("admin_api_disabled")

    async def db_ping() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def redis_ping() -> None:
        await redis_clients.cache.ping()

    checker = ReadinessChecker(
        db_ping=db_ping,
        redis_ping=redis_ping,
        queue_depth=queue_service.depth,
        active_workers=heartbeat.count_active,
    )

    async def refresh_metrics() -> None:
        """Read live cross-process signal into the gauges at scrape time (D-050)."""
        try:
            depth = await queue_service.depth()
        except Exception as exc:  # a transient read must not blank the whole scrape
            _log.warning("metrics_queue_depth_read_failed", error=str(exc))
            depth = 0
        try:
            workers = await heartbeat.count_active()
        except Exception as exc:
            _log.warning("metrics_active_workers_read_failed", error=str(exc))
            workers = 0
        try:
            await redis_clients.cache.ping()
            redis_ok = True
        except Exception as exc:
            _log.warning("metrics_redis_ping_failed", error=str(exc))
            redis_ok = False
        metrics.set_live_gauges(
            queue_depth_value=depth,
            active_workers_value=workers,
            db_pool_in_use_value=_pool_in_use(engine),
            redis_connected_value=redis_ok,
        )

    app = create_app(checker=checker, refresh_metrics=refresh_metrics, admin_router=admin_router)

    _log.info("api_starting", host=settings.api_bind_host, port=settings.api_bind_port)
    config = uvicorn.Config(
        app,
        host=settings.api_bind_host,
        port=settings.api_bind_port,
        log_level=settings.log_level.lower(),
        log_config=None,
    )
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        await redis_clients.aclose()
        await engine.dispose()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
