"""Unit tests for BroadcastService (MASTER_PLAN Task 8.1, flow 16.8)."""

from __future__ import annotations

import pytest

from domain.entities.audience import AudienceRuleSpec
from services.broadcast_service import BroadcastService, InvalidBroadcastError
from tests.unit._fakes import (
    FakeAudienceExpressionRepo,
    FakeBroadcastRepo,
    FakeUser,
    FakeUserRepo,
)


def _build() -> tuple[BroadcastService, FakeBroadcastRepo, FakeUserRepo]:
    broadcasts = FakeBroadcastRepo()
    users = FakeUserRepo()
    service = BroadcastService(broadcast_repo=broadcasts, user_repo=users)
    return service, broadcasts, users


def _build_with_expressions() -> tuple[
    BroadcastService, FakeBroadcastRepo, FakeUserRepo, FakeAudienceExpressionRepo
]:
    broadcasts = FakeBroadcastRepo()
    users = FakeUserRepo()
    expressions = FakeAudienceExpressionRepo()
    service = BroadcastService(
        broadcast_repo=broadcasts, user_repo=users, expression_repo=expressions
    )
    return service, broadcasts, users, expressions


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
    # 4 users minus the banned one minus the moderator (untargeted excludes staff, #14).
    assert broadcast.expected_total == 2
    assert broadcasts.rows == [broadcast]


async def test_create_applies_role_and_language_filters() -> None:
    service, _, users = _build()
    _seed_users(users)

    by_lang = await service.create(created_by_user_id=3, message_text="hi", target_language="en")
    assert by_lang.expected_total == 1  # tg 101 only (103 is staff/moderator, 104 banned, 102 es)

    by_role = await service.create(created_by_user_id=3, message_text="hi", target_role="moderator")
    assert by_role.expected_total == 1  # explicit role targets the moderator


async def test_create_rejects_empty_text() -> None:
    service, _, _ = _build()
    with pytest.raises(InvalidBroadcastError):
        await service.create(created_by_user_id=3, message_text="   ")


async def test_create_rejects_unknown_role() -> None:
    service, _, users = _build()
    _seed_users(users)
    with pytest.raises(InvalidBroadcastError):
        await service.create(created_by_user_id=3, message_text="hi", target_role="wizard")


# --- unified audience engine (Sprint 9.6, D-055) --------------------------
def _seed_premium(users: FakeUserRepo) -> None:
    users.by_tid[201] = FakeUser(id=1, telegram_id=201, role="user", is_premium=True)
    users.by_tid[202] = FakeUser(id=2, telegram_id=202, role="user", is_premium=False)
    users.by_tid[203] = FakeUser(id=3, telegram_id=203, role="user", is_premium=True)
    users.by_tid[204] = FakeUser(id=4, telegram_id=204, role="owner", is_premium=True)


async def test_create_with_expression_persists_rules_and_links_broadcast() -> None:
    service, broadcasts, users, expressions = _build_with_expressions()
    _seed_premium(users)

    broadcast = await service.create(
        created_by_user_id=3,
        message_text="premium only",
        audience_mode="include",
        audience_rules=[AudienceRuleSpec("include", "plan", "premium")],
    )

    # An expression was created, linked, and its rules persisted.
    assert broadcast.audience_expression_id is not None
    mode, rules = await expressions.get_rules(broadcast.audience_expression_id)  # type: ignore[misc]
    assert mode == "include"
    assert rules == [AudienceRuleSpec("include", "plan", "premium")]
    # Audience snapshot counts premium non-staff users only (owner excluded by guard).
    assert broadcast.expected_total == 2  # tg 201 + 203 (204 is owner, 202 free)


async def test_create_with_expression_rejects_unknown_mode() -> None:
    service, _, users, _ = _build_with_expressions()
    _seed_premium(users)
    with pytest.raises(InvalidBroadcastError):
        await service.create(
            created_by_user_id=3,
            message_text="hi",
            audience_mode="sometimes",
            audience_rules=[AudienceRuleSpec("include", "plan", "premium")],
        )


async def test_estimate_recipients_counts_without_persisting() -> None:
    # The Preview estimate (#7) runs the same unified count but creates no expression row.
    service, _, users, expressions = _build_with_expressions()
    _seed_premium(users)
    count = await service.estimate_recipients(
        audience_mode="include",
        audience_rules=[AudienceRuleSpec("include", "plan", "premium")],
    )
    assert count == 2  # tg 201 + 203 (204 owner excluded, 202 free)
    assert expressions.exprs == {}  # nothing persisted — read-only preview


async def test_estimate_recipients_rejects_unknown_mode() -> None:
    service, _, users = _build()
    _seed_premium(users)
    with pytest.raises(InvalidBroadcastError):
        await service.estimate_recipients(audience_mode="whenever", audience_rules=[])


async def test_create_without_expression_repo_falls_back_to_legacy() -> None:
    """The legacy role/language path still works when no expression repo is wired."""
    service, _, users = _build()
    _seed_premium(users)
    broadcast = await service.create(created_by_user_id=3, message_text="hi")
    assert broadcast.audience_expression_id is None
    assert broadcast.expected_total == 3  # three non-staff users (owner excluded)
