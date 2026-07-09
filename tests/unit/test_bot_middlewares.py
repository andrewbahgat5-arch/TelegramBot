"""Unit tests for the bot middleware stack (MASTER_PLAN Tasks 4.3 to 4.6).

Each middleware is exercised in isolation with fakes for the aiogram event surface
and the per-update services. No network or real Telegram objects are involved.
"""

from __future__ import annotations

import types
from collections.abc import Awaitable, Callable
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
import structlog
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.db_session import DbSessionMiddleware
from bot.middlewares.logging import LoggingMiddleware
from bot.middlewares.throttle import THROTTLE_MESSAGE, ThrottleMiddleware
from core.i18n import translate
from domain.entities.user import UserSnapshot
from services.rate_limit_service import RateLimitService
from services.reward_service import RewardService
from services.settings_service import SettingsService
from services.user_service import UserService
from tests.unit._fakes import (
    DEFAULT_RATE_SETTINGS,
    FakeCache,
    FakeRewardRepo,
    FakeSettingsStore,
    FakeUser,
    FakeUserRepo,
    make_cache_service,
)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]
_EVENT = cast(TelegramObject, object())


def _ok_handler(calls: list[dict[str, Any]]) -> Handler:
    async def handler(event: TelegramObject, data: dict[str, Any]) -> str:
        calls.append(data)
        return "handled"

    return handler


# --- LoggingMiddleware ----------------------------------------------------
async def test_logging_binds_and_clears_correlation_id() -> None:
    mw = LoggingMiddleware()
    seen: dict[str, Any] = {}

    async def handler(event: TelegramObject, data: dict[str, Any]) -> str:
        seen["ctx"] = structlog.contextvars.get_contextvars().get("correlation_id")
        seen["data"] = data["correlation_id"]
        return "ok"

    result = await mw(handler, _EVENT, {})
    assert result == "ok"
    assert seen["ctx"] == seen["data"] is not None
    # Context is unbound once the update is handled.
    assert "correlation_id" not in structlog.contextvars.get_contextvars()


# --- DbSessionMiddleware --------------------------------------------------
class _FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _factory(session: _FakeSession) -> async_sessionmaker[AsyncSession]:
    return cast(async_sessionmaker[AsyncSession], lambda: session)


async def test_db_session_commits_on_success() -> None:
    session = _FakeSession()
    mw = DbSessionMiddleware(_factory(session))
    calls: list[dict[str, Any]] = []
    await mw(_ok_handler(calls), _EVENT, {})
    assert session.committed and not session.rolled_back
    assert calls[0]["session"] is session


async def test_db_session_rolls_back_on_error() -> None:
    session = _FakeSession()
    mw = DbSessionMiddleware(_factory(session))

    async def boom(event: TelegramObject, data: dict[str, Any]) -> None:
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        await mw(boom, _EVENT, {})
    assert session.rolled_back and not session.committed


# --- AuthMiddleware -------------------------------------------------------
def _user_service(repo: FakeUserRepo) -> UserService:
    cache_service, _ = make_cache_service()
    return UserService(repo, cache_service, owner_telegram_id=999)


def _tg_user(uid: int = 1) -> object:
    # A deliberately uncataloged language_code (not "en"/"ar") — proves the
    # created row's language comes from the configured default, never from
    # Telegram's auto-detected code (Sprint 11.5).
    return types.SimpleNamespace(id=uid, username="neo", first_name="Thomas", language_code="ru")


async def test_auth_creates_user_and_attaches_snapshot() -> None:
    repo = FakeUserRepo()
    mw = AuthMiddleware(lambda session: _user_service(repo), default_locale="en")
    calls: list[dict[str, Any]] = []
    data: dict[str, Any] = {"session": object(), "event_from_user": _tg_user()}

    result = await mw(_ok_handler(calls), _EVENT, data)
    assert result == "handled"
    assert data["user"].telegram_id == 1
    assert repo.by_tid[1].telegram_id == 1


async def test_auth_creates_user_with_configured_default_locale_not_telegram_code() -> None:
    repo = FakeUserRepo()
    mw = AuthMiddleware(lambda session: _user_service(repo), default_locale="en")
    data: dict[str, Any] = {"session": object(), "event_from_user": _tg_user()}

    await mw(_ok_handler([]), _EVENT, data)
    assert data["user"].language == "en"
    assert repo.by_tid[1].language == "en"


async def test_auth_blocks_banned_user() -> None:
    from bot.middlewares.auth import _reply_timestamps

    _reply_timestamps.clear()
    repo = FakeUserRepo()
    repo.by_tid[1] = FakeUser(id=1, telegram_id=1, is_banned=True)
    mw = AuthMiddleware(lambda session: _user_service(repo), default_locale="en")
    calls: list[dict[str, Any]] = []
    event = AsyncMock(spec=Message)
    event.answer = AsyncMock()
    data: dict[str, Any] = {"session": object(), "event_from_user": _tg_user()}

    result = await mw(_ok_handler(calls), cast(TelegramObject, event), data)
    assert result is None
    assert calls == []  # handler skipped
    event.answer.assert_awaited_once_with(translate("user.banned", "en"), reply_markup=None)


async def test_auth_banned_callback_query_gets_alert() -> None:
    from bot.middlewares.auth import _reply_timestamps

    _reply_timestamps.clear()
    repo = FakeUserRepo()
    repo.by_tid[1] = FakeUser(id=1, telegram_id=1, is_banned=True)
    mw = AuthMiddleware(lambda session: _user_service(repo), default_locale="en")
    calls: list[dict[str, Any]] = []
    event = AsyncMock(spec=CallbackQuery)
    event.answer = AsyncMock()
    data: dict[str, Any] = {"session": object(), "event_from_user": _tg_user()}

    result = await mw(_ok_handler(calls), cast(TelegramObject, event), data)
    assert result is None and calls == []
    event.answer.assert_awaited_once_with(
        translate("user.banned", "en"), show_alert=True
    )


async def test_auth_passes_through_without_from_user() -> None:
    repo = FakeUserRepo()
    mw = AuthMiddleware(lambda session: _user_service(repo), default_locale="en")
    calls: list[dict[str, Any]] = []
    await mw(_ok_handler(calls), _EVENT, {"session": object()})
    assert len(calls) == 1
    assert "user" not in calls[0]


# --- ThrottleMiddleware ---------------------------------------------------
def _rate_service(limit: str) -> RateLimitService:
    data = dict(DEFAULT_RATE_SETTINGS)
    data["rate_limit_messages_per_minute"] = (limit, "int")
    settings_service = SettingsService(FakeSettingsStore(data), FakeCache())
    cache_service, _ = make_cache_service()
    return RateLimitService(
        settings_service, cache_service, FakeUserRepo(), RewardService(FakeRewardRepo())
    )


def _snapshot() -> UserSnapshot:
    return UserSnapshot.from_row(FakeUser(id=1, telegram_id=1))


async def test_throttle_allows_under_limit() -> None:
    mw = ThrottleMiddleware(lambda session: _rate_service("30"))
    calls: list[dict[str, Any]] = []
    data: dict[str, Any] = {"session": object(), "user": _snapshot()}
    await mw(_ok_handler(calls), _EVENT, data)
    assert len(calls) == 1


async def test_throttle_blocks_over_limit() -> None:
    mw = ThrottleMiddleware(lambda session: _rate_service("0"))  # 0 → first msg blocked
    calls: list[dict[str, Any]] = []
    event = AsyncMock(spec=Message)
    event.answer = AsyncMock()
    data: dict[str, Any] = {"session": object(), "user": _snapshot()}

    result = await mw(_ok_handler(calls), cast(TelegramObject, event), data)
    assert result is None
    assert calls == []
    event.answer.assert_awaited_once_with(THROTTLE_MESSAGE)


async def test_throttle_passthrough_without_user() -> None:
    mw = ThrottleMiddleware(lambda session: _rate_service("0"))
    calls: list[dict[str, Any]] = []
    await mw(_ok_handler(calls), _EVENT, {"session": object()})
    assert len(calls) == 1  # no user → throttle does not apply


async def test_throttle_never_blocks_owner() -> None:
    # Even with the limit at 0, the Owner passes through unthrottled (#21).
    mw = ThrottleMiddleware(lambda session: _rate_service("0"))
    calls: list[dict[str, Any]] = []
    owner = UserSnapshot.from_row(FakeUser(id=1, telegram_id=1, role="owner"))
    data: dict[str, Any] = {"session": object(), "user": owner}
    await mw(_ok_handler(calls), _EVENT, data)
    assert len(calls) == 1  # owner bypassed the throttle


async def test_throttle_blocks_callback_query() -> None:
    mw = ThrottleMiddleware(lambda session: _rate_service("0"))
    calls: list[dict[str, Any]] = []
    event = AsyncMock(spec=CallbackQuery)
    event.answer = AsyncMock()
    data: dict[str, Any] = {"session": object(), "user": _snapshot()}

    result = await mw(_ok_handler(calls), cast(TelegramObject, event), data)
    assert result is None and calls == []
    event.answer.assert_awaited_once_with(THROTTLE_MESSAGE, show_alert=True)
