"""Unit tests for RateLimitService (MASTER_PLAN Task 4.2, Section 16.5)."""

from __future__ import annotations

import datetime

import pytest

from domain.exceptions import (
    CooldownActiveError,
    DailyLimitExceededError,
    MaintenanceModeError,
    PermissionDeniedError,
    RateLimitExceededError,
)
from services.rate_limit_service import RateLimitService
from services.settings_service import SettingsService
from tests.unit._fakes import (
    DEFAULT_RATE_SETTINGS,
    FakeCache,
    FakeSettingsStore,
    FakeUser,
    FakeUserRepo,
    make_cache_service,
)


def _service(
    overrides: dict[str, tuple[str, str]] | None = None,
) -> tuple[RateLimitService, object]:
    data = dict(DEFAULT_RATE_SETTINGS)
    if overrides:
        data.update(overrides)
    settings_service = SettingsService(FakeSettingsStore(data), FakeCache())
    cache_service, _ = make_cache_service()
    return RateLimitService(settings_service, cache_service, FakeUserRepo()), cache_service


def _today() -> datetime.date:
    return datetime.datetime.now(datetime.UTC).date()


# --- message throttle -----------------------------------------------------
async def test_message_rate_allows_up_to_limit() -> None:
    svc, _ = _service()
    for _ in range(30):
        await svc.check_message_rate(user_id=1)  # 30 allowed


async def test_message_rate_rejects_over_limit() -> None:
    svc, _ = _service()
    for _ in range(30):
        await svc.check_message_rate(user_id=1)
    with pytest.raises(RateLimitExceededError):
        await svc.check_message_rate(user_id=1)  # 31st


# --- download checks ------------------------------------------------------
async def test_download_success_arms_cooldown() -> None:
    svc, cache_service = _service()
    user = FakeUser(id=1, telegram_id=1, daily_download_count_reset_date=_today())
    await svc.check_download(user)
    assert await cache_service.is_on_cooldown(1) is True  # type: ignore[attr-defined]


async def test_banned_user_rejected() -> None:
    svc, _ = _service()
    user = FakeUser(id=1, telegram_id=1, is_banned=True)
    with pytest.raises(PermissionDeniedError):
        await svc.check_download(user)


async def test_maintenance_mode_blocks() -> None:
    svc, _ = _service({"maintenance_mode": ("true", "bool")})
    user = FakeUser(id=1, telegram_id=1, daily_download_count_reset_date=_today())
    with pytest.raises(MaintenanceModeError):
        await svc.check_download(user)


async def test_daily_limit_exceeded() -> None:
    svc, _ = _service()
    user = FakeUser(
        id=1, telegram_id=1, daily_download_count=10, daily_download_count_reset_date=_today()
    )
    with pytest.raises(DailyLimitExceededError):
        await svc.check_download(user)


async def test_cooldown_active_blocks() -> None:
    svc, cache_service = _service()
    await cache_service.set_cooldown(1, ttl=30)  # type: ignore[attr-defined]
    user = FakeUser(id=1, telegram_id=1, daily_download_count_reset_date=_today())
    with pytest.raises(CooldownActiveError):
        await svc.check_download(user)


async def test_premium_plan_uses_higher_limit() -> None:
    svc, _ = _service()
    user = FakeUser(
        id=1,
        telegram_id=1,
        is_premium=True,
        premium_expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        daily_download_count=50,  # over free (10), under premium (100)
        daily_download_count_reset_date=_today(),
    )
    await svc.check_download(user)  # must not raise


async def test_expired_premium_falls_back_to_free() -> None:
    svc, _ = _service()
    user = FakeUser(
        id=1,
        telegram_id=1,
        is_premium=True,
        premium_expires_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1),
        daily_download_count=50,
        daily_download_count_reset_date=_today(),
    )
    with pytest.raises(DailyLimitExceededError):
        await svc.check_download(user)


async def test_lazy_daily_reset_then_pass() -> None:
    svc, _ = _service()
    user = FakeUser(
        id=1,
        telegram_id=1,
        daily_download_count=10,
        daily_download_count_reset_date=_today() - datetime.timedelta(days=1),
    )
    await svc.check_download(user)  # reset to 0 first, then passes
    assert user.daily_download_count == 0
