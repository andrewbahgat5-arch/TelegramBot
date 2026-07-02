"""Unit tests for the admin handlers (MASTER_PLAN Task 8.2, Sprint 11.5 i18n)."""

from __future__ import annotations

import datetime
from typing import cast
from unittest.mock import AsyncMock

from aiogram.filters import CommandObject
from aiogram.types import Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.admin import (
    OwnerFilter,
    handle_ban,
    handle_broadcast,
    handle_setting_set,
    handle_stats,
    handle_unban,
    handle_userinfo,
    handle_users,
)
from core.i18n import translate
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from services.broadcast_service import BroadcastService
from services.queue_service import QueueService
from services.settings_service import SettingsService
from services.user_service import UserService
from tests.unit._fakes import (
    FakeBroadcastRepo,
    FakeCache,
    FakeQueueBackend,
    FakeSettingsStore,
    FakeUser,
    FakeUserRepo,
    make_cache_service,
)

_EVENT = cast(TelegramObject, object())
_LOCALE = "en"


def _session() -> AsyncSession:
    return cast(AsyncSession, object())  # factories ignore it in these tests


def _message() -> AsyncMock:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    return message


def _answer_text(message: AsyncMock) -> str:
    args = message.answer.await_args
    assert args is not None
    return cast(str, args.args[0])


def _owner() -> UserSnapshot:
    return UserSnapshot(
        id=1,
        telegram_id=999,
        role=UserRole.OWNER,
        is_banned=False,
        is_premium=False,
        daily_download_count=0,
        daily_download_count_reset_date=datetime.date(2026, 6, 24),
        total_downloads=0,
    )


def _user_service(users: FakeUserRepo) -> UserService:
    cache, _ = make_cache_service()
    return UserService(users, cache, owner_telegram_id=999)


def _settings_service(data: dict[str, tuple[str, str]]) -> SettingsService:
    return SettingsService(FakeSettingsStore(data), FakeCache(), cache_ttl=60)


# --- /stats ---------------------------------------------------------------
async def test_stats_reports_user_and_queue_totals() -> None:
    users = FakeUserRepo()
    users.by_tid[1] = FakeUser(id=1, telegram_id=1, total_downloads=5)
    users.by_tid[2] = FakeUser(id=2, telegram_id=2, total_downloads=3, is_banned=True)
    queue = QueueService(FakeQueueBackend())
    message = _message()

    await handle_stats(
        message, _session(), lambda s: _user_service(users), queue, translate, _LOCALE
    )

    text = _answer_text(message)
    assert "Users: <b>2</b>" in text and "banned: 1" in text
    assert "Lifetime downloads: <b>8</b>" in text


# --- /userinfo ------------------------------------------------------------
async def test_userinfo_shows_user_detail() -> None:
    users = FakeUserRepo()
    users.by_tid[55] = FakeUser(id=9, telegram_id=55, first_name="Sam", total_downloads=4)
    message = _message()

    await handle_userinfo(
        message,
        CommandObject(args="55"),
        _session(),
        lambda s: _user_service(users),
        translate,
        _LOCALE,
    )

    text = _answer_text(message)
    assert "Sam" in text and "55" in text and "Downloads: 4" in text


async def test_userinfo_missing_user_reports_not_found() -> None:
    message = _message()
    await handle_userinfo(
        message,
        CommandObject(args="404"),
        _session(),
        lambda s: _user_service(FakeUserRepo()),
        translate,
        _LOCALE,
    )
    assert "No user" in _answer_text(message)


async def test_userinfo_without_args_shows_usage() -> None:
    message = _message()
    await handle_userinfo(
        message,
        CommandObject(args=None),
        _session(),
        lambda s: _user_service(FakeUserRepo()),
        translate,
        _LOCALE,
    )
    assert "Usage" in _answer_text(message)


# --- /ban + /unban --------------------------------------------------------
async def test_ban_sets_audit_fields() -> None:
    users = FakeUserRepo()
    users.by_tid[55] = FakeUser(id=9, telegram_id=55)
    message = _message()

    await handle_ban(
        message,
        CommandObject(args="55 spamming"),
        _session(),
        lambda s: _user_service(users),
        translate,
        _LOCALE,
    )

    assert users.by_tid[55].is_banned is True
    assert users.by_tid[55].ban_reason == "spamming"
    assert "Banned" in _answer_text(message)


async def test_ban_unknown_user_reports_not_found() -> None:
    message = _message()
    await handle_ban(
        message,
        CommandObject(args="55"),
        _session(),
        lambda s: _user_service(FakeUserRepo()),
        translate,
        _LOCALE,
    )
    assert "No user" in _answer_text(message)


async def test_unban_clears_flag() -> None:
    users = FakeUserRepo()
    users.by_tid[55] = FakeUser(id=9, telegram_id=55, is_banned=True)
    message = _message()

    await handle_unban(
        message,
        CommandObject(args="55"),
        _session(),
        lambda s: _user_service(users),
        translate,
        _LOCALE,
    )

    assert users.by_tid[55].is_banned is False
    assert "Unbanned" in _answer_text(message)


# --- /setting_set (scriptable fallback; /settings now opens the inline panel) ----
async def test_setting_set_updates_valid_value() -> None:
    message = _message()
    store_data = {"free_daily_limit": ("10", "int")}
    service = SettingsService(FakeSettingsStore(store_data), FakeCache(), cache_ttl=60)
    await handle_setting_set(
        message,
        CommandObject(args="free_daily_limit 25"),
        _session(),
        _owner(),
        lambda s: service,
        translate,
        _LOCALE,
    )
    assert "Updated" in _answer_text(message)
    assert await service.get("free_daily_limit") == 25


async def test_setting_set_rejects_unknown_key() -> None:
    message = _message()
    service = _settings_service({"free_daily_limit": ("10", "int")})
    await handle_setting_set(
        message,
        CommandObject(args="made_up_key 5"),
        _session(),
        _owner(),
        lambda s: service,
        translate,
        _LOCALE,
    )
    assert "Unknown setting key" in _answer_text(message)


async def test_setting_set_rejects_bad_value() -> None:
    message = _message()
    service = _settings_service({"free_daily_limit": ("10", "int")})
    await handle_setting_set(
        message,
        CommandObject(args="free_daily_limit not-a-number"),
        _session(),
        _owner(),
        lambda s: service,
        translate,
        _LOCALE,
    )
    assert "Invalid value" in _answer_text(message)


# --- /broadcast -----------------------------------------------------------
async def test_broadcast_queues_and_reports_count() -> None:
    users = FakeUserRepo()
    users.by_tid[1] = FakeUser(id=1, telegram_id=1, language="en")
    users.by_tid[2] = FakeUser(id=2, telegram_id=2, language="en")
    broadcasts = FakeBroadcastRepo()
    service = BroadcastService(broadcast_repo=broadcasts, user_repo=users)
    message = _message()

    await handle_broadcast(
        message,
        CommandObject(args="hello there --lang en"),
        _session(),
        _owner(),
        lambda s: service,
        translate,
        _LOCALE,
    )

    text = _answer_text(message)
    assert "queued to <b>2</b>" in text and "lang=en" in text
    assert broadcasts.rows[0].message_text == "hello there"
    assert broadcasts.rows[0].target_language == "en"


async def test_broadcast_escapes_html_for_safe_delivery() -> None:
    # The worker sends broadcasts with HTML parse mode, so raw command text with HTML
    # metacharacters must be escaped at creation to render verbatim (not break parsing).
    users = FakeUserRepo()
    users.by_tid[1] = FakeUser(id=1, telegram_id=1, language="en")
    broadcasts = FakeBroadcastRepo()
    service = BroadcastService(broadcast_repo=broadcasts, user_repo=users)
    message = _message()

    await handle_broadcast(
        message,
        CommandObject(args="5 < 10 & rising"),
        _session(),
        _owner(),
        lambda s: service,
        translate,
        _LOCALE,
    )

    assert broadcasts.rows[0].message_text == "5 &lt; 10 &amp; rising"


async def test_broadcast_empty_text_is_rejected() -> None:
    service = BroadcastService(broadcast_repo=FakeBroadcastRepo(), user_repo=FakeUserRepo())
    message = _message()
    await handle_broadcast(
        message,
        CommandObject(args="--lang en"),
        _session(),
        _owner(),
        lambda s: service,
        translate,
        _LOCALE,
    )
    assert "Cannot broadcast" in _answer_text(message)


async def test_broadcast_with_at_schedules() -> None:
    users = FakeUserRepo()
    users.by_tid[1] = FakeUser(id=1, telegram_id=1, language="en")
    broadcasts = FakeBroadcastRepo()
    service = BroadcastService(broadcast_repo=broadcasts, user_repo=users)
    message = _message()

    await handle_broadcast(
        message,
        CommandObject(args="hello --lang en --at 2026-07-01T12:00:00Z"),
        _session(),
        _owner(),
        lambda s: service,
        translate,
        _LOCALE,
    )

    assert "scheduled" in _answer_text(message)
    assert broadcasts.rows[0].message_text == "hello"
    assert broadcasts.rows[0].scheduled_at == datetime.datetime(
        2026, 7, 1, 12, 0, tzinfo=datetime.UTC
    )


async def test_broadcast_with_invalid_at_is_rejected() -> None:
    broadcasts = FakeBroadcastRepo()
    service = BroadcastService(broadcast_repo=broadcasts, user_repo=FakeUserRepo())
    message = _message()
    await handle_broadcast(
        message,
        CommandObject(args="hello --at not-a-time"),
        _session(),
        _owner(),
        lambda s: service,
        translate,
        _LOCALE,
    )
    assert "Invalid" in _answer_text(message)
    assert broadcasts.rows == []  # nothing queued


# --- /users ---------------------------------------------------------------
async def test_users_lists_registered_users() -> None:
    users = FakeUserRepo()
    users.by_tid[1] = FakeUser(id=1, telegram_id=111, username="alice", first_name="Alice")
    users.by_tid[2] = FakeUser(id=2, telegram_id=222, first_name="Bob", is_banned=True)
    message = _message()

    await handle_users(message, _session(), lambda s: _user_service(users), translate, _LOCALE)

    text = _answer_text(message)
    assert "alice" in text and "Alice" in text and "111" in text
    assert "Bob" in text and "banned" in text


async def test_users_empty_reports_none() -> None:
    message = _message()
    await handle_users(
        message, _session(), lambda s: _user_service(FakeUserRepo()), translate, _LOCALE
    )
    assert "No users" in _answer_text(message)


# --- authorization --------------------------------------------------------
async def test_owner_filter_blocks_moderator() -> None:
    # Unauthorized admin commands are silently ignored (item #18) — there is no denied
    # reply handler; the role filter simply declines and no handler matches.
    moderator = UserSnapshot.from_row(FakeUser(id=2, telegram_id=2, role="moderator"))
    assert await OwnerFilter(_EVENT, moderator) is False
