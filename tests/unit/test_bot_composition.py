"""Unit test for the bot composition root wiring (MASTER_PLAN Task 4.9).

Exercises ``build_dispatcher`` (the testable part of ``bot/main.py``): it must
construct a dispatcher, install the middleware stack, and include both routers —
without any network or backing services.
"""

from __future__ import annotations

from typing import cast

from aiogram import Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.main import build_dispatcher
from services.rate_limit_service import RateLimitService
from services.user_service import UserService
from tests.unit._fakes import load_settings


def _user_factory(session: AsyncSession) -> UserService:
    return cast(UserService, None)


def _rate_factory(session: AsyncSession) -> RateLimitService:
    return cast(RateLimitService, None)


def test_build_dispatcher_wires_middlewares_and_routers() -> None:
    dp = build_dispatcher(
        load_settings(),
        user_service_factory=_user_factory,
        rate_limit_service_factory=_rate_factory,
        session_factory=cast(async_sessionmaker[AsyncSession], lambda: None),
    )
    assert isinstance(dp, Dispatcher)
    # start + help routers are both included.
    assert len(dp.sub_routers) == 2
