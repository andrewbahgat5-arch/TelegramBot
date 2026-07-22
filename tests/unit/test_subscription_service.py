"""Unit tests for SubscriptionService write semantics (V2-D-022, V2.1)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from core.uuid7 import uuid7
from domain.enums import SubscriptionStatus
from services.subscription_service import SubscriptionService

_NOW = datetime.datetime(2026, 7, 22, 12, 0, tzinfo=datetime.UTC)


@dataclass
class _SubRow:
    id: object
    user_id: int
    plan_id: int
    status: str
    source: str
    starts_at: datetime.datetime
    expires_at: datetime.datetime
    notified_milestones: int = 0
    granted_by: int | None = None
    updated_at: datetime.datetime = _NOW


class _FakeSubscriptionRepo:
    def __init__(self) -> None:
        self.rows: list[_SubRow] = []

    async def get_active_for_user(self, user_id: int) -> _SubRow | None:
        for row in self.rows:
            if row.user_id == user_id and row.status == SubscriptionStatus.ACTIVE.value:
                return row
        return None

    async def create_active(
        self, *, user_id, plan_id, source, starts_at, expires_at, granted_by
    ) -> _SubRow:
        row = _SubRow(
            id=uuid7(),
            user_id=user_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE.value,
            source=source,
            starts_at=starts_at,
            expires_at=expires_at,
            granted_by=granted_by,
        )
        self.rows.append(row)
        return row

    async def set_expiry(self, row, expires_at, *, now) -> None:
        row.expires_at = expires_at
        row.updated_at = now

    async def set_status(self, row, status, *, now) -> None:
        row.status = status.value
        row.updated_at = now


@dataclass
class _FakePlan:
    id: int
    code: str


class _FakePlanRepo:
    def __init__(self) -> None:
        self._by_code = {"free": _FakePlan(1, "free"), "premium": _FakePlan(2, "premium")}

    async def get_by_code(self, code: str):
        return self._by_code.get(code)


def _service() -> tuple[SubscriptionService, _FakeSubscriptionRepo]:
    subs = _FakeSubscriptionRepo()
    invalidated: list[int] = []

    async def _invalidate(uid: int) -> None:
        invalidated.append(uid)

    svc = SubscriptionService(
        subs, _FakePlanRepo(), clock=lambda: _NOW, invalidate_user=_invalidate  # type: ignore[arg-type]
    )
    svc._invalidated = invalidated  # type: ignore[attr-defined]
    return svc, subs


async def test_grant_creates_active_from_now() -> None:
    svc, subs = _service()
    sub = await svc.grant(7, datetime.timedelta(days=30), granted_by=1)
    assert sub.status is SubscriptionStatus.ACTIVE
    assert sub.plan_id == 2  # premium
    assert sub.expires_at == _NOW + datetime.timedelta(days=30)
    assert sub.starts_at == _NOW


async def test_grant_cancels_existing_active_row() -> None:
    svc, subs = _service()
    await svc.grant(7, datetime.timedelta(days=10), granted_by=1)
    await svc.grant(7, datetime.timedelta(days=30), granted_by=1)
    active = [r for r in subs.rows if r.status == "active"]
    canceled = [r for r in subs.rows if r.status == "canceled"]
    assert len(active) == 1  # one-active-row invariant preserved
    assert len(canceled) == 1
    assert active[0].expires_at == _NOW + datetime.timedelta(days=30)


async def test_extend_adds_to_current_expiry_when_active() -> None:
    svc, subs = _service()
    await svc.grant(7, datetime.timedelta(days=10), granted_by=1)
    await svc.extend(7, datetime.timedelta(days=5), granted_by=1)
    active = await subs.get_active_for_user(7)
    assert active is not None
    assert active.expires_at == _NOW + datetime.timedelta(days=15)  # 10 + 5, not from-now


async def test_extend_without_active_starts_from_now() -> None:
    svc, subs = _service()
    sub = await svc.extend(7, datetime.timedelta(days=5), granted_by=1)
    assert sub.expires_at == _NOW + datetime.timedelta(days=5)


async def test_set_expiration_overrides_absolutely() -> None:
    svc, subs = _service()
    await svc.grant(7, datetime.timedelta(days=10), granted_by=1)
    target = _NOW + datetime.timedelta(days=99)
    sub = await svc.set_expiration(7, target, granted_by=1)
    assert sub.expires_at == target


async def test_set_expiration_creates_when_none() -> None:
    svc, subs = _service()
    target = _NOW + datetime.timedelta(days=99)
    sub = await svc.set_expiration(7, target, granted_by=1)
    assert sub.expires_at == target
    assert sub.status is SubscriptionStatus.ACTIVE


async def test_remove_cancels_active_and_invalidates() -> None:
    svc, subs = _service()
    await svc.grant(7, datetime.timedelta(days=10), granted_by=1)
    removed = await svc.remove(7, removed_by=1)
    assert removed is True
    assert await subs.get_active_for_user(7) is None
    assert 7 in svc._invalidated  # type: ignore[attr-defined]


async def test_remove_noop_when_no_active() -> None:
    svc, _ = _service()
    assert await svc.remove(7, removed_by=1) is False
