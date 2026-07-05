"""Unit tests for UserService (MASTER_PLAN Task 4.1)."""

from __future__ import annotations

import dataclasses
import datetime

import pytest

from core.redis_keys import RedisKeys
from domain.enums import UserRole
from services.user_service import UserService
from tests.unit._fakes import FakeCache, FakeUser, FakeUserRepo, make_cache_service

OWNER_ID = 555


def _service(*, debounce_seconds: int = 60) -> tuple[UserService, FakeUserRepo, FakeCache]:
    repo = FakeUserRepo()
    cache_service, raw_cache = make_cache_service()
    svc = UserService(
        repo, cache_service, owner_telegram_id=OWNER_ID, debounce_seconds=debounce_seconds
    )
    return svc, repo, raw_cache


async def test_creates_user_with_default_role() -> None:
    svc, repo, _ = _service()
    snap = await svc.get_or_create_user(telegram_id=1001, first_name="A")
    assert snap.role is UserRole.USER
    assert snap.telegram_id == 1001
    assert repo.by_tid[1001].first_name == "A"


async def test_owner_telegram_id_becomes_owner() -> None:
    svc, repo, _ = _service()
    snap = await svc.get_or_create_user(telegram_id=OWNER_ID)
    assert snap.role is UserRole.OWNER


async def test_second_call_reuses_row_no_duplicate() -> None:
    svc, repo, _ = _service()
    first = await svc.get_or_create_user(telegram_id=1001)
    second = await svc.get_or_create_user(telegram_id=1001)
    assert first.id == second.id
    assert len(repo.by_tid) == 1


async def test_cache_hit_skips_repo() -> None:
    svc, repo, raw_cache = _service()
    await svc.get_or_create_user(telegram_id=1001)  # populates cache
    # Drop the row from the repo; a cache hit must still resolve the user.
    repo.by_tid.clear()
    snap = await svc.get_or_create_user(telegram_id=1001)
    assert snap.telegram_id == 1001
    assert repo.by_tid == {}  # repo was never consulted


async def test_get_or_create_populates_cache() -> None:
    svc, _, raw_cache = _service()
    await svc.get_or_create_user(telegram_id=1001)
    assert RedisKeys.user(1001) in raw_cache.store


async def test_get_stats_aggregates_cohorts() -> None:
    svc, repo, _ = _service()
    now = datetime.datetime.now(datetime.UTC)
    old = now - datetime.timedelta(days=30)
    this_week = now - datetime.timedelta(days=3)
    # joined today + active today + premium, 3 downloads.
    repo.by_tid[1] = FakeUser(
        id=1,
        telegram_id=1,
        created_at=now,
        last_activity_at=now,
        is_premium=True,
        total_downloads=3,
    )
    # joined this week (not today), inactive, 1 download.
    repo.by_tid[2] = FakeUser(id=2, telegram_id=2, created_at=this_week, total_downloads=1)
    # old moderator, active today.
    repo.by_tid[3] = FakeUser(
        id=3, telegram_id=3, role="moderator", created_at=old, last_activity_at=now
    )
    # old banned user.
    repo.by_tid[4] = FakeUser(id=4, telegram_id=4, is_banned=True, created_at=old)

    stats = await svc.get_stats()

    assert stats.total_users == 4
    assert stats.banned_users == 1
    assert stats.total_downloads == 4
    assert stats.new_today == 1  # only user 1
    assert stats.new_this_week == 2  # users 1 and 2
    assert stats.active_today == 2  # users 1 and 3
    assert stats.premium_users == 1  # user 1
    assert stats.staff_users == 1  # user 3 (moderator)
    # Enhanced activity metrics (13.4): users 1 & 3 active "now"; 2 & 4 never active.
    assert stats.active_24h == 2
    assert stats.active_7d == 2
    assert stats.active_30d == 2
    assert stats.active_current_hour == 2
    assert stats.active_previous_hour == 0
    assert stats.inactive_5d == 2  # users 2 & 4 (NULL last_activity)
    assert stats.inactive_7d == 2
    assert stats.inactive_30d == 2


async def test_record_activity_writes_when_never_active() -> None:
    svc, repo, _ = _service()
    snap = await svc.get_or_create_user(telegram_id=1001)
    await svc.record_activity(snap)
    assert repo.touch_calls and repo.touch_calls[0][0] == 1001


async def test_record_activity_debounced_within_window() -> None:
    svc, repo, _ = _service(debounce_seconds=60)
    snap = await svc.get_or_create_user(telegram_id=1001)
    recent = dataclasses.replace(snap, last_activity_at=datetime.datetime.now(datetime.UTC))
    await svc.record_activity(recent)
    assert repo.touch_calls == []  # within debounce window → no write


async def test_record_activity_writes_after_window() -> None:
    svc, repo, _ = _service(debounce_seconds=60)
    snap = await svc.get_or_create_user(telegram_id=1001)
    stale = dataclasses.replace(
        snap,
        last_activity_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=2),
    )
    await svc.record_activity(stale)
    assert len(repo.touch_calls) == 1


async def test_ban_sets_audit_and_invalidates_cache() -> None:
    svc, repo, raw_cache = _service()
    await svc.get_or_create_user(telegram_id=1001)
    snap = await svc.ban(1001, reason="spam")
    assert snap is not None and snap.is_banned is True
    row = repo.by_tid[1001]
    assert row.is_banned and row.ban_reason == "spam" and row.banned_at is not None
    assert RedisKeys.user(1001) not in raw_cache.store


async def test_unban_clears_ban_fields() -> None:
    svc, repo, _ = _service()
    await svc.get_or_create_user(telegram_id=1001)
    await svc.ban(1001, reason="spam")
    snap = await svc.unban(1001)
    assert snap is not None and snap.is_banned is False
    assert snap.ban_reason is None  # the snapshot reflects the cleared reason
    row = repo.by_tid[1001]
    # Unban clears the ban metadata so a non-banned user never shows a stale ban (D-054).
    assert row.banned_at is None
    assert row.ban_reason is None


async def test_set_role_updates_role() -> None:
    svc, repo, _ = _service()
    await svc.get_or_create_user(telegram_id=1001)
    snap = await svc.set_role(1001, UserRole.MODERATOR)
    assert snap is not None and snap.role is UserRole.MODERATOR
    assert repo.by_tid[1001].role == "moderator"


async def test_set_premium_grants_and_clears() -> None:
    svc, repo, _ = _service()
    await svc.get_or_create_user(telegram_id=1001)
    expires = datetime.datetime(2026, 12, 31, tzinfo=datetime.UTC)
    snap = await svc.set_premium(1001, is_premium=True, expires_at=expires)
    assert snap is not None and snap.is_premium is True
    assert repo.by_tid[1001].is_premium and repo.by_tid[1001].premium_expires_at == expires
    # Clearing premium also clears the expiry (no stale window).
    snap = await svc.set_premium(1001, is_premium=False)
    assert snap is not None and snap.is_premium is False
    assert repo.by_tid[1001].premium_expires_at is None


@pytest.mark.parametrize("op", ["ban", "unban", "set_role", "set_premium"])
async def test_mutations_on_missing_user_return_none(op: str) -> None:
    svc, _, _ = _service()
    if op == "ban":
        assert await svc.ban(404) is None
    elif op == "unban":
        assert await svc.unban(404) is None
    elif op == "set_premium":
        assert await svc.set_premium(404, is_premium=True) is None
    else:
        assert await svc.set_role(404, UserRole.USER) is None
