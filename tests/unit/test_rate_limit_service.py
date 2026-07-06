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


# --- daily-reset boundary / date-edge cases (Owner req #11, D-012) ---------
async def test_no_reset_when_reset_date_is_today() -> None:
    # Boundary: reset_date == today must NOT reset — same-day usage still counts, so a
    # user at the cap is rejected rather than silently getting a fresh quota.
    svc, _ = _service()
    user = FakeUser(
        id=1,
        telegram_id=1,
        daily_download_count=10,  # free_daily_limit
        daily_download_count_reset_date=_today(),
    )
    with pytest.raises(DailyLimitExceededError):
        await svc.check_download(user)
    assert user.daily_download_count == 10  # untouched


async def test_reset_when_reset_date_is_far_in_the_past() -> None:
    # A long-idle user (400 days) resets exactly once to today, not proportionally.
    svc, _ = _service()
    user = FakeUser(
        id=1,
        telegram_id=1,
        daily_download_count=10,
        daily_download_count_reset_date=_today() - datetime.timedelta(days=400),
    )
    await svc.check_download(user)
    assert user.daily_download_count == 0
    assert user.daily_download_count_reset_date == _today()


# --- permanent referral bonus and the daily limit (Owner req #11, D-066) ---
# D-066 / SPRINT_13_PLAN §13.7: the referral bonus is added on top of the base
# daily limit (effective = base + referral_bonus_downloads), is permanent, and is
# NEVER cleared by the D-012 lazy daily-counter reset.
async def test_referral_bonus_raises_effective_daily_limit() -> None:
    svc, _ = _service()
    user = FakeUser(
        id=1,
        telegram_id=1,
        daily_download_count=12,  # over base free (10), under base + bonus (15)
        referral_bonus_downloads=5,
        daily_download_count_reset_date=_today(),
    )
    await svc.check_download(user)  # must not raise — the +5 bonus counts (D-066)


async def test_referral_bonus_still_enforces_at_combined_cap() -> None:
    svc, _ = _service()
    user = FakeUser(
        id=1,
        telegram_id=1,
        daily_download_count=15,  # exactly base (10) + bonus (5)
        referral_bonus_downloads=5,
        daily_download_count_reset_date=_today(),
    )
    with pytest.raises(DailyLimitExceededError):
        await svc.check_download(user)


async def test_referral_bonus_stacks_on_premium_limit() -> None:
    svc, _ = _service()
    user = FakeUser(
        id=1,
        telegram_id=1,
        is_premium=True,
        premium_expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        daily_download_count=102,  # over premium (100), under premium + bonus (105)
        referral_bonus_downloads=5,
        daily_download_count_reset_date=_today(),
    )
    await svc.check_download(user)  # must not raise — bonus stacks on premium too


async def test_referral_bonus_survives_daily_reset() -> None:
    # Yesterday's usage is wiped by the lazy reset; the permanent bonus is not.
    svc, _ = _service()
    user = FakeUser(
        id=1,
        telegram_id=1,
        daily_download_count=13,  # yesterday, near the base + bonus cap
        referral_bonus_downloads=5,
        daily_download_count_reset_date=_today() - datetime.timedelta(days=1),
    )
    await svc.check_download(user)  # resets the count, bonus intact → passes
    assert user.daily_download_count == 0
    assert user.referral_bonus_downloads == 5  # bonus never reset (D-066)


# --- Owner bypass (#21) ---------------------------------------------------
async def test_owner_bypasses_all_limits_and_no_cooldown() -> None:
    # Maintenance on + a huge daily count: the Owner is still authorized and is NOT
    # placed on cooldown (unlimited downloads/requests, #21).
    svc, cache_service = _service({"maintenance_mode": ("true", "bool")})
    owner = FakeUser(
        id=1,
        telegram_id=1,
        role="owner",
        daily_download_count=9999,
        daily_download_count_reset_date=_today(),
    )
    await svc.check_download(owner)  # must not raise
    assert await cache_service.is_on_cooldown(1) is False  # type: ignore[attr-defined]


# --- authorize_download (#15: reads the authoritative row) ----------------
def _service_with_user(
    user: FakeUser, overrides: dict[str, tuple[str, str]] | None = None
) -> RateLimitService:
    data = dict(DEFAULT_RATE_SETTINGS)
    if overrides:
        data.update(overrides)
    cache_service, _ = make_cache_service()
    repo = FakeUserRepo()
    repo.by_tid[user.telegram_id] = user
    return RateLimitService(
        SettingsService(FakeSettingsStore(data), FakeCache()), cache_service, repo
    )


async def test_authorize_download_loads_fresh_row_and_enforces() -> None:
    user = FakeUser(
        id=5, telegram_id=5, daily_download_count=1, daily_download_count_reset_date=_today()
    )
    svc = _service_with_user(user, {"free_daily_limit": ("1", "int")})
    with pytest.raises(DailyLimitExceededError):
        await svc.authorize_download(5)


async def test_authorize_download_missing_user_is_noop() -> None:
    svc, _ = _service()
    await svc.authorize_download(404)  # no row → nothing to authorize, no error


# --- limit change is immediately effective (#23) --------------------------
async def test_limit_change_takes_effect_immediately() -> None:
    # Reader (rate-limit service) and writer (/setting_set) share the same store + cache,
    # exactly as the bot wires them (both over the one Redis). No stale quota survives.
    store = FakeSettingsStore({**DEFAULT_RATE_SETTINGS, "free_daily_limit": ("1", "int")})
    cache = FakeCache()
    cache_service, _ = make_cache_service()
    repo = FakeUserRepo()
    repo.by_tid[5] = FakeUser(
        id=5, telegram_id=5, daily_download_count=1, daily_download_count_reset_date=_today()
    )
    svc = RateLimitService(SettingsService(store, cache), cache_service, repo)

    with pytest.raises(DailyLimitExceededError):
        await svc.authorize_download(5)  # at limit 1

    # Owner raises the limit via /setting_set (writer shares store + cache → invalidates).
    await SettingsService(store, cache).set_validated("free_daily_limit", "10")
    await svc.authorize_download(5)  # now passes — the new limit is seen at once
