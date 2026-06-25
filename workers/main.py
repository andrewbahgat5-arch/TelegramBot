"""Worker composition root (MASTER_PLAN Component 8.2, Task 5.4 / 6.7).

The worker process's single place that may import both ``services`` and
``infrastructure`` (Section 8.2). It wires the shared singletons (registry, Telegram
client, FFmpeg, Redis cache/queue) and a per-job ``DownloadService`` factory, then
runs concurrently: the provider health-check task (Section 12.6.4), ``worker_count``
``DownloadWorker`` loops (Task 6.6), and the ``CleanupWorker`` sweep (Task 6.10).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# The composition root may build the shared callback signer (a leaf crypto helper over
# the bot token); the worker uses it to sign ad click buttons so the bot verifies them
# with the same scheme (flow 16.7 W6). import-linter permits workers -> bot here.
from bot.callbacks.factory import CallbackSigner
from core.config import Settings
from core.logging import configure_logging, get_logger
from core.sentry import init_sentry
from infrastructure.database.engine import create_engine
from infrastructure.database.repositories.active_download import ActiveDownloadRepository
from infrastructure.database.repositories.ad_audience_rule import AdAudienceRuleRepository
from infrastructure.database.repositories.ad_button import AdButtonRepository
from infrastructure.database.repositories.advertisement import AdRepository
from infrastructure.database.repositories.audience_segment import AudienceSegmentMemberRepository
from infrastructure.database.repositories.broadcast import BroadcastRepository
from infrastructure.database.repositories.cached_file import CachedFileRepository
from infrastructure.database.repositories.download import DownloadRepository
from infrastructure.database.repositories.job import JobRepository
from infrastructure.database.repositories.job_waiter import JobWaiterRepository
from infrastructure.database.repositories.media import MediaRepository
from infrastructure.database.repositories.setting import SettingsRepository
from infrastructure.database.repositories.user import UserRepository
from infrastructure.database.session import create_session_factory
from infrastructure.downloader.ffmpeg_client import FFmpegClient
from infrastructure.downloader.provider_settings import ProviderSettingsAdapter
from infrastructure.downloader.providers.ytdlp_provider import YtdlpProvider
from infrastructure.downloader.registry import DownloaderRegistry
from infrastructure.redis.cache import RedisCache
from infrastructure.redis.client import create_redis_clients
from infrastructure.redis.locks import RedisLock
from infrastructure.redis.queue import RedisQueue
from infrastructure.telegram.ad_sender import TelegramAdSender
from infrastructure.telegram.client import build_bot
from infrastructure.telegram.file_sender import TelegramFileSender, TelegramMessageSender
from services.ad_service import AdService
from services.audience_service import AudienceService
from services.cache_service import CacheService
from services.download_service import DownloadService
from services.notification_service import NotificationService
from services.queue_service import QueueService
from services.settings_service import SettingsService
from services.url_analyzer import URLAnalyzerService
from workers.broadcast_worker import BroadcastWorker
from workers.cleanup_worker import CleanupWorker
from workers.download_worker import DownloadWorker

_log = get_logger("workers.main")

_DEFAULT_HEALTH_INTERVAL = 120
_DEFAULT_BROADCAST_CHUNK_SIZE = 25


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


async def _read_broadcast_chunk_size(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    async with session_factory() as session:
        row = await SettingsRepository(session).get_by_key("broadcast_chunk_size")
    return int(row.value) if row is not None else _DEFAULT_BROADCAST_CHUNK_SIZE


def make_download_service_factory(
    *,
    settings: Settings,
    registry: DownloaderRegistry,
    cache_service: CacheService,
    redis_cache: RedisCache,
    transcoder: FFmpegClient,
    file_sender: TelegramFileSender,
    ad_sender: TelegramAdSender,
    ad_signer: CallbackSigner,
    notification_service: NotificationService,
) -> Callable[[AsyncSession], DownloadService]:
    """Return a ``session -> DownloadService`` builder (per-job unit of work)."""

    def build(session: AsyncSession) -> DownloadService:
        settings_service = SettingsService(
            SettingsRepository(session), redis_cache, cache_ttl=settings.cache_settings_ttl
        )
        analyzer = URLAnalyzerService(registry, cache_service, MediaRepository(session))
        ad_service = AdService(
            ad_repo=AdRepository(session),
            settings=settings_service,
            sender=ad_sender,
            signer=ad_signer,
            button_repo=AdButtonRepository(session),
            audience=AudienceService(
                rule_repo=AdAudienceRuleRepository(session),
                member_repo=AudienceSegmentMemberRepository(session),
            ),
        )
        return DownloadService(
            job_repo=JobRepository(session),
            cached_file_repo=CachedFileRepository(session),
            download_repo=DownloadRepository(session),
            job_waiter_repo=JobWaiterRepository(session),
            active_download_repo=ActiveDownloadRepository(session),
            user_repo=UserRepository(session),
            analyzer=analyzer,
            downloader=registry,
            transcoder=transcoder,
            file_sender=file_sender,
            notification_service=notification_service,
            cache_service=cache_service,
            settings_service=settings_service,
            settings=settings,
            ad_service=ad_service,
        )

    return build


async def main() -> None:  # pragma: no cover - process entry; wiring covered by unit tests
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level, settings.log_format)
    if settings.sentry_enabled:
        init_sentry(settings)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    redis_clients = create_redis_clients(settings)

    redis_cache = RedisCache(redis_clients.cache)
    cache_service = CacheService(redis_cache, RedisLock(redis_clients.cache), settings)
    queue_service = QueueService(RedisQueue(redis_clients.queue))
    registry = build_registry(settings, session_factory, redis_clients.cache)

    bot = build_bot(settings)
    file_sender = TelegramFileSender(bot)
    ad_sender = TelegramAdSender(bot)
    ad_signer = CallbackSigner(settings.bot_token.get_secret_value())
    message_sender = TelegramMessageSender(bot)
    notification_service = NotificationService(message_sender)
    transcoder = FFmpegClient(settings.ffmpeg_path)

    build_download_service = make_download_service_factory(
        settings=settings,
        registry=registry,
        cache_service=cache_service,
        redis_cache=redis_cache,
        transcoder=transcoder,
        file_sender=file_sender,
        ad_sender=ad_sender,
        ad_signer=ad_signer,
        notification_service=notification_service,
    )

    def build_ad_service(session: AsyncSession) -> AdService:
        settings_service = SettingsService(
            SettingsRepository(session), redis_cache, cache_ttl=settings.cache_settings_ttl
        )
        return AdService(
            ad_repo=AdRepository(session),
            settings=settings_service,
            sender=ad_sender,
            signer=ad_signer,
            button_repo=AdButtonRepository(session),
            audience=AudienceService(
                rule_repo=AdAudienceRuleRepository(session),
                member_repo=AudienceSegmentMemberRepository(session),
            ),
        )

    interval = await _read_health_interval(session_factory)
    chunk_size = await _read_broadcast_chunk_size(session_factory)
    cleanup = CleanupWorker(Path(settings.download_temp_dir))
    broadcast_worker = BroadcastWorker(
        session_factory=session_factory,
        build_broadcast_repo=BroadcastRepository,
        build_user_repo=UserRepository,
        sender=message_sender,
        chunk_size=chunk_size,
        ad_sender=ad_sender,
        build_ad_service=build_ad_service,
    )

    tasks = [
        provider_health_check_task(registry, interval),
        cleanup.run_forever(),
        broadcast_worker.run_forever(),
    ]
    for _ in range(settings.worker_count):
        worker = DownloadWorker(
            queue_service=queue_service,
            session_factory=session_factory,
            build_download_service=build_download_service,
            max_retries=settings.worker_max_retries,
        )
        tasks.append(worker.run_forever())

    _log.info(
        "worker_starting",
        workers=settings.worker_count,
        health_interval_seconds=interval,
        broadcast_chunk_size=chunk_size,
    )
    try:
        await asyncio.gather(*tasks)
    finally:
        await bot.session.close()
        await redis_clients.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
