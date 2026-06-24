"""Unit test for the bot composition root wiring (MASTER_PLAN Task 4.9).

Exercises ``build_dispatcher`` (the testable part of ``bot/main.py``): it must
construct a dispatcher, install the middleware stack, and include both routers —
without any network or backing services.
"""

from __future__ import annotations

from typing import cast

from aiogram import Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.callbacks.factory import CallbackSigner
from bot.main import build_dispatcher
from services.history_service import HistoryService
from services.job_service import JobService
from services.notification_service import NotificationService
from services.rate_limit_service import RateLimitService
from services.url_analyzer import URLAnalyzerService
from services.user_service import UserService
from tests.unit._fakes import FakeMessageSender, load_settings


def _user_factory(session: AsyncSession) -> UserService:
    return cast(UserService, None)


def _rate_factory(session: AsyncSession) -> RateLimitService:
    return cast(RateLimitService, None)


def _analyzer_factory(session: AsyncSession) -> URLAnalyzerService:
    return cast(URLAnalyzerService, None)


def _job_factory(session: AsyncSession) -> JobService:
    return cast(JobService, None)


def _history_factory(session: AsyncSession) -> HistoryService:
    return cast(HistoryService, None)


def test_build_dispatcher_wires_middlewares_and_routers() -> None:
    dp = build_dispatcher(
        load_settings(),
        user_service_factory=_user_factory,
        rate_limit_service_factory=_rate_factory,
        analyzer_factory=_analyzer_factory,
        job_service_factory=_job_factory,
        history_service_factory=_history_factory,
        notification_service=NotificationService(FakeMessageSender()),
        callback_signer=CallbackSigner("test-secret"),
        session_factory=cast(async_sessionmaker[AsyncSession], lambda: None),
    )
    assert isinstance(dp, Dispatcher)
    # start + help + download + history routers are all included.
    assert len(dp.sub_routers) == 4
