"""Unit tests for PlanCatalog + EntitlementService (VERSION_2_MASTER_PLAN §5.1, V2.1)."""

from __future__ import annotations

import datetime
from uuid import uuid4

import pytest

from domain.entities.plan import Plan
from domain.entities.subscription import Subscription
from domain.entitlements import EntitlementError
from domain.enums import SubscriptionSource, SubscriptionStatus
from services.entitlement_service import EntitlementService, PlanCatalog

_NOW = datetime.datetime(2026, 7, 22, 12, 0, tzinfo=datetime.UTC)


def _ents(daily: int, cooldown: int, *, ad_free: bool) -> dict[str, object]:
    return {
        "daily_download_limit": daily,
        "cooldown_seconds": cooldown,
        "max_file_size_bytes": 52_428_800,
        "ad_free": ad_free,
        "playlists_enabled": False,
    }


def _plan(id_: int, code: str, ents: dict[str, object]) -> Plan:
    return Plan(
        id=id_, code=code, name=code.title(), is_active=True, sort_order=id_, entitlements=ents
    )


_FREE = _plan(1, "free", _ents(10, 30, ad_free=False))
_PREMIUM = _plan(2, "premium", _ents(100, 5, ad_free=True))


def _catalog() -> PlanCatalog:
    return PlanCatalog([_FREE, _PREMIUM])


def _sub(plan_id: int, status: SubscriptionStatus, expires_at: datetime.datetime) -> Subscription:
    return Subscription(
        id=uuid4(),
        user_id=1,
        plan_id=plan_id,
        status=status,
        source=SubscriptionSource.MANUAL_GRANT,
        starts_at=_NOW - datetime.timedelta(days=1),
        expires_at=expires_at,
    )


# --- PlanCatalog validation ------------------------------------------------
def test_catalog_requires_free_plan() -> None:
    with pytest.raises(EntitlementError, match="no 'free' plan"):
        PlanCatalog([_PREMIUM])


def test_catalog_rejects_invalid_plan_entitlements() -> None:
    broken = _plan(3, "free", {"daily_download_limit": 10})  # missing keys
    with pytest.raises(EntitlementError):
        PlanCatalog([broken])


# --- resolution matrix (the parity surface) --------------------------------
def test_no_active_subscription_resolves_free() -> None:
    resolved = EntitlementService(_catalog()).resolve(None, now=_NOW)
    assert resolved.plan_code == "free"
    assert resolved.entitlements.daily_download_limit == 10


def test_active_premium_resolves_premium() -> None:
    sub = _sub(2, SubscriptionStatus.ACTIVE, _NOW + datetime.timedelta(days=5))
    resolved = EntitlementService(_catalog()).resolve(sub, now=_NOW)
    assert resolved.plan_code == "premium"
    assert resolved.entitlements.ad_free is True


def test_expired_active_row_resolves_free_lazily() -> None:
    # status is still 'active' but expiry has passed — resolver degrades to Free (V2-D-007).
    sub = _sub(2, SubscriptionStatus.ACTIVE, _NOW - datetime.timedelta(seconds=1))
    resolved = EntitlementService(_catalog()).resolve(sub, now=_NOW)
    assert resolved.plan_code == "free"


def test_canceled_row_resolves_free() -> None:
    sub = _sub(2, SubscriptionStatus.CANCELED, _NOW + datetime.timedelta(days=5))
    resolved = EntitlementService(_catalog()).resolve(sub, now=_NOW)
    assert resolved.plan_code == "free"


def test_dangling_plan_id_falls_back_to_free() -> None:
    sub = _sub(999, SubscriptionStatus.ACTIVE, _NOW + datetime.timedelta(days=5))
    resolved = EntitlementService(_catalog()).resolve(sub, now=_NOW)
    assert resolved.plan_code == "free"
