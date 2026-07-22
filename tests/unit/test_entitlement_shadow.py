"""Unit tests for shadow-mode entitlement parity (V2-D-024, V2.1)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import pytest

from domain.entities.plan import Plan
from domain.enums import SubscriptionSource, SubscriptionStatus
from services import entitlement_shadow
from services.entitlement_service import EntitlementService, PlanCatalog
from services.entitlement_shadow import ShadowParity, legacy_plan_code

_NOW = datetime.datetime(2026, 7, 22, 12, 0, tzinfo=datetime.UTC)


def _ents(daily: int, *, ad_free: bool) -> dict[str, object]:
    return {
        "daily_download_limit": daily,
        "cooldown_seconds": 30,
        "max_file_size_bytes": 1,
        "ad_free": ad_free,
        "playlists_enabled": False,
    }


def _catalog() -> PlanCatalog:
    return PlanCatalog(
        [
            Plan(1, "free", "Free", True, 0, _ents(10, ad_free=False)),
            Plan(2, "premium", "Premium", True, 1, _ents(100, ad_free=True)),
        ]
    )


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


class _FakeSubs:
    def __init__(self, row: _SubRow | None = None) -> None:
        self._row = row

    async def get_active_for_user(self, user_id: int) -> _SubRow | None:
        return self._row


def _active_premium_row() -> _SubRow:
    return _SubRow(
        id="0190000000007000800000000000abcd",
        user_id=7,
        plan_id=2,
        status=SubscriptionStatus.ACTIVE.value,
        source=SubscriptionSource.MANUAL_GRANT.value,
        starts_at=_NOW - datetime.timedelta(days=1),
        expires_at=_NOW + datetime.timedelta(days=5),
    )


# --- legacy_plan_code ------------------------------------------------------
def test_legacy_plan_code_premium_when_flagged_and_unexpired() -> None:
    assert (
        legacy_plan_code(
            is_premium=True, premium_expires_at=_NOW + datetime.timedelta(days=1), now=_NOW
        )
        == "premium"
    )


def test_legacy_plan_code_free_when_expired() -> None:
    assert (
        legacy_plan_code(
            is_premium=True, premium_expires_at=_NOW - datetime.timedelta(days=1), now=_NOW
        )
        == "free"
    )


def test_legacy_plan_code_free_when_not_premium() -> None:
    assert legacy_plan_code(is_premium=False, premium_expires_at=None, now=_NOW) == "free"


# --- ShadowParity.check ----------------------------------------------------
@pytest.fixture
def mismatches(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(
        entitlement_shadow.metrics, "record_entitlement_parity_mismatch", captured.append
    )
    return captured


async def test_no_mismatch_when_premium_user_has_active_premium_row(mismatches: list[str]) -> None:
    parity = ShadowParity(EntitlementService(_catalog()), _FakeSubs(_active_premium_row()))
    await parity.check(
        user_id=7, is_premium=True, premium_expires_at=_NOW + datetime.timedelta(days=5), now=_NOW
    )
    assert mismatches == []


async def test_mismatch_when_premium_user_has_no_subscription(mismatches: list[str]) -> None:
    # The gap the backfill closes: legacy=premium, resolver=free (no row yet).
    parity = ShadowParity(EntitlementService(_catalog()), _FakeSubs(None))
    await parity.check(
        user_id=7, is_premium=True, premium_expires_at=_NOW + datetime.timedelta(days=5), now=_NOW
    )
    assert mismatches == ["plan_code"]


async def test_no_mismatch_for_free_user_without_subscription(mismatches: list[str]) -> None:
    parity = ShadowParity(EntitlementService(_catalog()), _FakeSubs(None))
    await parity.check(user_id=7, is_premium=False, premium_expires_at=None, now=_NOW)
    assert mismatches == []
