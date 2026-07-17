"""Unit test for the bot composition root wiring (MASTER_PLAN Task 4.9).

Exercises ``build_dispatcher`` (the testable part of ``bot/main.py``): it must
construct a dispatcher, install the middleware stack, and include both routers —
without any network or backing services.
"""

from __future__ import annotations

from typing import cast

from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.callbacks.factory import CallbackSigner
from bot.main import build_dispatcher
from services.ad_service import AdService
from services.admin_notification_service import AdminNotificationService
from services.admin_service import AdminService
from services.audience_service import AudienceService
from services.broadcast_service import BroadcastService
from services.history_service import HistoryService
from services.job_service import JobService
from services.notification_service import NotificationService
from services.queue_service import QueueService
from services.rate_limit_service import RateLimitService
from services.referral_service import ReferralService
from services.settings_service import SettingsService
from services.template_service import TemplateService
from services.url_analyzer import URLAnalyzerService
from services.user_health import UserHealthChecker
from services.user_preference_service import UserPreferenceService
from services.user_service import UserService
from tests.unit._fakes import FakeMessageSender, FakeQueueBackend, load_settings


def _user_factory(session: AsyncSession) -> UserService:
    return cast(UserService, None)


def _admin_notification_factory(session: AsyncSession) -> AdminNotificationService:
    return cast(AdminNotificationService, None)


def _rate_factory(session: AsyncSession) -> RateLimitService:
    return cast(RateLimitService, None)


def _analyzer_factory(session: AsyncSession) -> URLAnalyzerService:
    return cast(URLAnalyzerService, None)


def _job_factory(session: AsyncSession) -> JobService:
    return cast(JobService, None)


def _history_factory(session: AsyncSession) -> HistoryService:
    return cast(HistoryService, None)


def _settings_factory(session: AsyncSession) -> SettingsService:
    return cast(SettingsService, None)


def _broadcast_factory(session: AsyncSession) -> BroadcastService:
    return cast(BroadcastService, None)


def _ad_factory(session: AsyncSession) -> AdService:
    return cast(AdService, None)


def _audience_factory(session: AsyncSession) -> AudienceService:
    return cast(AudienceService, None)


def _admin_factory(session: AsyncSession) -> AdminService:
    return cast(AdminService, None)


def _referral_factory(session: AsyncSession) -> ReferralService:
    return cast(ReferralService, None)


def _preference_factory(session: AsyncSession) -> UserPreferenceService:
    return cast(UserPreferenceService, None)


def _health_checker_factory(bot: Bot) -> UserHealthChecker:
    return cast(UserHealthChecker, None)


def test_build_dispatcher_wires_middlewares_and_routers() -> None:
    # A durable FSM store is threaded through so the compose wizard survives restarts (#6);
    # the module-level routers can only attach to one Dispatcher, so this is asserted here.
    from aiogram.fsm.storage.memory import MemoryStorage

    storage = MemoryStorage()
    dp = build_dispatcher(
        load_settings(),
        user_service_factory=_user_factory,
        admin_notification_factory=_admin_notification_factory,
        rate_limit_service_factory=_rate_factory,
        analyzer_factory=_analyzer_factory,
        job_service_factory=_job_factory,
        history_service_factory=_history_factory,
        settings_service_factory=_settings_factory,
        broadcast_service_factory=_broadcast_factory,
        ad_service_factory=_ad_factory,
        audience_service_factory=_audience_factory,
        admin_service_factory=_admin_factory,
        referral_service_factory=_referral_factory,
        preference_service_factory=_preference_factory,
        template_service=cast(TemplateService, None),
        health_checker_factory=_health_checker_factory,
        queue_service=QueueService(FakeQueueBackend()),
        notification_service=NotificationService(FakeMessageSender()),
        callback_signer=CallbackSigner("test-secret"),
        session_factory=cast(async_sessionmaker[AsyncSession], lambda: None),
        storage=storage,
    )
    assert isinstance(dp, Dispatcher)
    # start + membership + help + admin + admin_panel + ads + download + history routers.
    assert len(dp.sub_routers) == 8
    assert dp.fsm.storage is storage
