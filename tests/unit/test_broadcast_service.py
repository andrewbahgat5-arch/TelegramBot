"""Unit tests for BroadcastService (MASTER_PLAN Task 8.1, flow 16.8)."""

from __future__ import annotations

import pytest

from services.broadcast_service import BroadcastService, InvalidBroadcastError
from tests.unit._fakes import FakeBroadcastRepo, FakeUser, FakeUserRepo


def _build() -> tuple[BroadcastService, FakeBroadcastRepo, FakeUserRepo]:
    broadcasts = FakeBroadcastRepo()
    users = FakeUserRepo()
    service = BroadcastService(broadcast_repo=broadcasts, user_repo=users)
    return service, broadcasts, users


def _seed_users(users: FakeUserRepo) -> None:
    users.by_tid[101] = FakeUser(id=1, telegram_id=101, role="user", language="en")
    users.by_tid[102] = FakeUser(id=2, telegram_id=102, role="user", language="es")
    users.by_tid[103] = FakeUser(id=3, telegram_id=103, role="moderator", language="en")
    users.by_tid[104] = FakeUser(id=4, telegram_id=104, role="user", language="en", is_banned=True)


async def test_create_snapshots_audience_and_queues_pending() -> None:
    service, broadcasts, users = _build()
    _seed_users(users)

    broadcast = await service.create(created_by_user_id=3, message_text="  hello all  ")

    assert broadcast.status == "pending"
    assert broadcast.message_text == "hello all"  # trimmed
    assert broadcast.expected_total == 3  # 4 users minus the banned one
    assert broadcasts.rows == [broadcast]


async def test_create_applies_role_and_language_filters() -> None:
    service, _, users = _build()
    _seed_users(users)

    by_lang = await service.create(created_by_user_id=3, message_text="hi", target_language="en")
    assert by_lang.expected_total == 2  # tg 101 + 103 (104 is banned, 102 is es)

    by_role = await service.create(created_by_user_id=3, message_text="hi", target_role="moderator")
    assert by_role.expected_total == 1  # only the moderator


async def test_create_rejects_empty_text() -> None:
    service, _, _ = _build()
    with pytest.raises(InvalidBroadcastError):
        await service.create(created_by_user_id=3, message_text="   ")


async def test_create_rejects_unknown_role() -> None:
    service, _, users = _build()
    _seed_users(users)
    with pytest.raises(InvalidBroadcastError):
        await service.create(created_by_user_id=3, message_text="hi", target_role="wizard")
