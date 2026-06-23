"""Unit tests for UserService (MASTER_PLAN Task 4.1)."""

from __future__ import annotations

import dataclasses
import datetime

import pytest

from core.redis_keys import RedisKeys
from domain.enums import UserRole
from services.user_service import UserService
from tests.unit._fakes import FakeCache, FakeUserRepo, make_cache_service

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


async def test_unban_preserves_audit_fields() -> None:
    svc, repo, _ = _service()
    await svc.get_or_create_user(telegram_id=1001)
    await svc.ban(1001, reason="spam")
    snap = await svc.unban(1001)
    assert snap is not None and snap.is_banned is False
    row = repo.by_tid[1001]
    # Audit trail is retained (Section 9.1 AuthMiddleware / D — preserve audit fields).
    assert row.banned_at is not None
    assert row.ban_reason == "spam"


async def test_set_role_updates_role() -> None:
    svc, repo, _ = _service()
    await svc.get_or_create_user(telegram_id=1001)
    snap = await svc.set_role(1001, UserRole.MODERATOR)
    assert snap is not None and snap.role is UserRole.MODERATOR
    assert repo.by_tid[1001].role == "moderator"


@pytest.mark.parametrize("op", ["ban", "unban", "set_role"])
async def test_mutations_on_missing_user_return_none(op: str) -> None:
    svc, _, _ = _service()
    if op == "ban":
        assert await svc.ban(404) is None
    elif op == "unban":
        assert await svc.unban(404) is None
    else:
        assert await svc.set_role(404, UserRole.USER) is None
