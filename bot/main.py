"""Bot composition root (MASTER_PLAN Component 9.1 ``BotApp``, Task 4.9).

The single place that may import both ``services`` and ``infrastructure`` for the
bot process (Section 8.2). It wires concrete adapters to the protocols the service
layer depends on, builds the aiogram dispatcher, installs the middleware stack, and
runs the bot (long-polling by default; webhook optional, selected by config).

Middleware order matters (Section 9.1):

    logging  →  db_session  →  auth  →  throttle  →  handler

``logging`` and ``db_session`` are cross-cutting and wrap *every* update; ``auth``
and ``throttle`` need ``event_from_user`` and so attach to the message and
callback-query observers.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.callbacks.factory import CallbackSigner
from bot.handlers import admin as admin_handler
from bot.handlers import admin_panel as admin_panel_handler
from bot.handlers import ads as ads_handler
from bot.handlers import download as download_handler
from bot.handlers import help as help_handler
from bot.handlers import history as history_handler
from bot.handlers import start as start_handler
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.db_session import DbSessionMiddleware
from bot.middlewares.logging import LoggingMiddleware
from bot.middlewares.throttle import ThrottleMiddleware
from core.alerting import TelegramAlertProcessor
from core.config import Settings
from core.logging import configure_logging, get_logger
from core.sentry import init_sentry, set_component
from infrastructure.database.ad_event_recorder import AdEventRecorder
from infrastructure.database.engine import create_engine
from infrastructure.database.repositories.active_download import ActiveDownloadRepository
from infrastructure.database.repositories.ad_audience_rule import AdAudienceRuleRepository
from infrastructure.database.repositories.ad_button import AdButtonRepository
from infrastructure.database.repositories.advertisement import AdRepository
from infrastructure.database.repositories.audience_expression import AudienceExpressionRepository
from infrastructure.database.repositories.audience_segment import (
    AudienceSegmentMemberRepository,
    AudienceSegmentRepository,
)
from infrastructure.database.repositories.broadcast import BroadcastRepository
from infrastructure.database.repositories.cached_file import CachedFileRepository
from infrastructure.database.repositories.download import DownloadRepository
from infrastructure.database.repositories.error_log import ErrorLogRepository
from infrastructure.database.repositories.job import JobRepository
from infrastructure.database.repositories.job_waiter import JobWaiterRepository
from infrastructure.database.repositories.media import MediaRepository
from infrastructure.database.repositories.setting import SettingsRepository
from infrastructure.database.repositories.user import UserRepository
from infrastructure.database.session import create_session_factory
from infrastructure.downloader.provider_settings import ProviderSettingsAdapter
from infrastructure.downloader.providers.ytdlp_provider import YtdlpProvider
from infrastructure.downloader.registry import DownloaderRegistry
from infrastructure.redis.cache import RedisCache
from infrastructure.redis.client import create_redis_clients
from infrastructure.redis.locks import RedisLock
from infrastructure.redis.queue import RedisQueue
from infrastructure.telegram.ad_sender import TelegramAdSender
from infrastructure.telegram.alerter import TelegramAlerter, make_alert_sink
from infrastructure.telegram.client import build_bot
from infrastructure.telegram.file_sender import TelegramFileSender, TelegramMessageSender
from services.ad_service import AdService
from services.admin_service import AdminService
from services.audience_service import AudienceService
from services.broadcast_service import BroadcastService
from services.cache_service import CacheService
from services.history_service import HistoryService
from services.job_service import JobService
from services.notification_service import NotificationService
from services.queue_service import QueueService
from services.rate_limit_service import RateLimitService
from services.settings_service import SettingsService
from services.url_analyzer import URLAnalyzerService
from services.user_service import UserService

_log = get_logger("bot.main")


def build_dispatcher(
    settings: Settings,
    *,
    user_service_factory: Callable[[AsyncSession], UserService],
    rate_limit_service_factory: Callable[[AsyncSession], RateLimitService],
    analyzer_factory: Callable[[AsyncSession], URLAnalyzerService],
    job_service_factory: Callable[[AsyncSession], JobService],
    history_service_factory: Callable[[AsyncSession], HistoryService],
    settings_service_factory: Callable[[AsyncSession], SettingsService],
    broadcast_service_factory: Callable[[AsyncSession], BroadcastService],
    ad_service_factory: Callable[[AsyncSession], AdService],
    audience_service_factory: Callable[[AsyncSession], AudienceService],
    admin_service_factory: Callable[[AsyncSession], AdminService],
    queue_service: QueueService,
    notification_service: NotificationService,
    callback_signer: CallbackSigner,
    session_factory: async_sessionmaker[AsyncSession],
) -> Dispatcher:
    """Build the dispatcher and install the Section 9.1 middleware stack."""
    dp = Dispatcher()
    # Workflow data injected into handlers by parameter name (download/history/admin).
    dp["analyzer_factory"] = analyzer_factory
    dp["job_service_factory"] = job_service_factory
    dp["history_service_factory"] = history_service_factory
    dp["rate_limit_service_factory"] = rate_limit_service_factory
    dp["user_service_factory"] = user_service_factory
    dp["settings_service_factory"] = settings_service_factory
    dp["broadcast_service_factory"] = broadcast_service_factory
    dp["ad_service_factory"] = ad_service_factory
    dp["audience_service_factory"] = audience_service_factory
    dp["admin_service_factory"] = admin_service_factory
    dp["queue_service"] = queue_service
    dp["notification_service"] = notification_service
    dp["callback_signer"] = callback_signer

    dp.update.outer_middleware(LoggingMiddleware())
    dp.update.outer_middleware(DbSessionMiddleware(session_factory))

    auth = AuthMiddleware(user_service_factory)
    throttle = ThrottleMiddleware(rate_limit_service_factory)
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(auth)
        observer.outer_middleware(throttle)

    dp.include_router(start_handler.router)
    dp.include_router(help_handler.router)
    dp.include_router(admin_handler.router)
    dp.include_router(admin_panel_handler.router)
    dp.include_router(ads_handler.router)
    dp.include_router(download_handler.router)
    dp.include_router(history_handler.router)
    return dp


async def main() -> None:
    # pydantic-settings populates every field from the environment / .env; mypy
    # cannot see that, so the no-arg constructor is annotated (as in tests).
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level, settings.log_format)
    if settings.sentry_enabled:
        init_sentry(settings)
        set_component("bot")

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    redis_clients = create_redis_clients(settings)
    # Process singleton: writes ad_events off the hot path on its own sessions (D-052).
    ad_event_recorder = AdEventRecorder(session_factory)

    redis_cache = RedisCache(redis_clients.cache)
    cache_service = CacheService(redis_cache, RedisLock(redis_clients.cache), settings)
    queue_service = QueueService(RedisQueue(redis_clients.queue))

    # The registry is a process singleton (holds provider health state). It reads
    # provider settings via an adapter that opens its own short-lived sessions.
    registry = DownloaderRegistry(
        ProviderSettingsAdapter(session_factory), redis=redis_clients.cache
    )
    registry.register(YtdlpProvider(settings.ytdlp_path))
    callback_signer = CallbackSigner(settings.bot_token.get_secret_value())

    bot = build_bot(settings)
    file_sender = TelegramFileSender(bot)
    ad_sender = TelegramAdSender(bot)
    notification_service = NotificationService(TelegramMessageSender(bot))

    # Telegram alerter (Task 10.3): re-install logging with the CRITICAL-record sink
    # now that the bot exists. No-op when no alerts chat is configured.
    if settings.telegram_alerts_chat_id is not None:
        alerter = TelegramAlerter(bot, settings.telegram_alerts_chat_id)
        configure_logging(
            settings.log_level,
            settings.log_format,
            extra_processors=[TelegramAlertProcessor(make_alert_sink(alerter))],
        )

    def make_user_service(session: AsyncSession) -> UserService:
        return UserService(
            UserRepository(session),
            cache_service,
            owner_telegram_id=settings.bot_owner_telegram_id,
        )

    def make_rate_limit_service(session: AsyncSession) -> RateLimitService:
        settings_service = SettingsService(
            SettingsRepository(session), redis_cache, cache_ttl=settings.cache_settings_ttl
        )
        return RateLimitService(settings_service, cache_service, UserRepository(session))

    def make_url_analyzer(session: AsyncSession) -> URLAnalyzerService:
        return URLAnalyzerService(registry, cache_service, MediaRepository(session))

    def make_job_service(session: AsyncSession) -> JobService:
        return JobService(
            job_repo=JobRepository(session),
            cached_file_repo=CachedFileRepository(session),
            active_download_repo=ActiveDownloadRepository(session),
            job_waiter_repo=JobWaiterRepository(session),
            download_repo=DownloadRepository(session),
            user_repo=UserRepository(session),
            queue_service=queue_service,
            cache_service=cache_service,
            file_sender=file_sender,
            notification_service=notification_service,
            settings=settings,
        )

    def make_history_service(session: AsyncSession) -> HistoryService:
        return HistoryService(
            download_repo=DownloadRepository(session),
            cached_file_repo=CachedFileRepository(session),
            job_service=make_job_service(session),
            analyzer=make_url_analyzer(session),
            file_sender=file_sender,
            cache_service=cache_service,
            settings_service=make_settings_service(session),
        )

    def make_settings_service(session: AsyncSession) -> SettingsService:
        return SettingsService(
            SettingsRepository(session), redis_cache, cache_ttl=settings.cache_settings_ttl
        )

    def make_broadcast_service(session: AsyncSession) -> BroadcastService:
        return BroadcastService(
            broadcast_repo=BroadcastRepository(session),
            user_repo=UserRepository(session),
            expression_repo=AudienceExpressionRepository(session),
        )

    def make_audience_service(session: AsyncSession) -> AudienceService:
        return AudienceService(
            rule_repo=AdAudienceRuleRepository(session),
            member_repo=AudienceSegmentMemberRepository(session),
            segment_repo=AudienceSegmentRepository(session),
        )

    def make_admin_service(session: AsyncSession) -> AdminService:
        return AdminService(
            job_repo=JobRepository(session),
            error_repo=ErrorLogRepository(session),
            download_repo=DownloadRepository(session),
        )

    def make_ad_service(session: AsyncSession) -> AdService:
        return AdService(
            ad_repo=AdRepository(session),
            settings=make_settings_service(session),
            sender=ad_sender,
            signer=callback_signer,
            button_repo=AdButtonRepository(session),
            audience=make_audience_service(session),
            event_recorder=ad_event_recorder,
        )

    dp = build_dispatcher(
        settings,
        user_service_factory=make_user_service,
        rate_limit_service_factory=make_rate_limit_service,
        analyzer_factory=make_url_analyzer,
        job_service_factory=make_job_service,
        history_service_factory=make_history_service,
        settings_service_factory=make_settings_service,
        broadcast_service_factory=make_broadcast_service,
        ad_service_factory=make_ad_service,
        audience_service_factory=make_audience_service,
        admin_service_factory=make_admin_service,
        queue_service=queue_service,
        notification_service=notification_service,
        callback_signer=callback_signer,
        session_factory=session_factory,
    )

    _log.info("bot_starting", mode="webhook" if settings.use_webhook else "polling")
    try:
        if settings.use_webhook:
            await _run_webhook(bot, dp, settings)
        else:
            await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await redis_clients.aclose()
        await engine.dispose()


async def _run_webhook(bot: Bot, dp: Dispatcher, settings: Settings) -> None:
    """Optional webhook mode (Task 4.9). Long-polling is the default path."""
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web

    secret = settings.bot_webhook_secret.get_secret_value()
    await bot.set_webhook(settings.bot_webhook_url, secret_token=secret)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.api_bind_host, port=settings.api_bind_port)
    await site.start()
    await asyncio.Event().wait()  # run until cancelled


if __name__ == "__main__":
    asyncio.run(main())
