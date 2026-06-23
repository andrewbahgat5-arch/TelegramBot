"""Worker composition root (MASTER_PLAN Component 8.2, Task 5.4 / 5.10).

The worker process's single composition root. In Sprint 5 it wires the
``DownloaderRegistry`` (with ``YtdlpProvider`` registered) and runs the periodic
provider health-check task (Section 12.6.4). The download/cleanup/broadcast workers
land in later sprints and will be started from here too.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from core.logging import configure_logging, get_logger
from core.sentry import init_sentry
from infrastructure.database.engine import create_engine
from infrastructure.database.repositories.setting import SettingsRepository
from infrastructure.database.session import create_session_factory
from infrastructure.downloader.provider_settings import ProviderSettingsAdapter
from infrastructure.downloader.providers.ytdlp_provider import YtdlpProvider
from infrastructure.downloader.registry import DownloaderRegistry
from infrastructure.redis.client import create_redis_clients

_log = get_logger("workers.main")

_DEFAULT_HEALTH_INTERVAL = 120


def build_registry(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    redis_cache: object,
) -> DownloaderRegistry:
    """Build the registry with every V1 provider registered (Section 12.6.5)."""
    registry = DownloaderRegistry(
        ProviderSettingsAdapter(session_factory),
        redis=redis_cache,  # type: ignore[arg-type]
    )
    registry.register(YtdlpProvider(settings.ytdlp_path))
    return registry


async def provider_health_check_task(registry: DownloaderRegistry, interval_seconds: int) -> None:
    """Refresh provider health every ``interval_seconds`` (Section 12.6.4)."""
    while True:
        await registry.refresh_health()
        await asyncio.sleep(interval_seconds)


async def _read_health_interval(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    async with session_factory() as session:
        row = await SettingsRepository(session).get_by_key("provider_health_check_interval_seconds")
    return int(row.value) if row is not None else _DEFAULT_HEALTH_INTERVAL


async def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level, settings.log_format)
    if settings.sentry_enabled:
        init_sentry(settings)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    redis_clients = create_redis_clients(settings)

    registry = build_registry(settings, session_factory, redis_clients.cache)
    interval = await _read_health_interval(session_factory)

    _log.info("worker_starting", health_interval_seconds=interval)
    try:
        await provider_health_check_task(registry, interval)
    finally:
        await redis_clients.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
