"""Security · Abuse Protection (MASTER_PLAN §25.9.3).

Spam throttling, daily limits, and cooldowns must hold; the Owner is exempt.
Per-user counters cannot be bypassed by varying request content.
"""

from __future__ import annotations

import pytest

from domain.exceptions import (
    CooldownActiveError,
    DailyLimitExceededError,
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
) -> RateLimitService:
    data = dict(DEFAULT_RATE_SETTINGS)
    if overrides:
        data.update(overrides)
    settings_service = SettingsService(FakeSettingsStore(data), FakeCache())
    cache_service, _ = make_cache_service()
    return RateLimitService(settings_service, cache_service, FakeUserRepo())


# --- Message-rate spam ----------------------------------------------------
async def test_message_spam_blocked_at_limit() -> None:
    svc = _service()
    for _ in range(30):  # rate_limit_messages_per_minute = 30
        await svc.check_message_rate(user_id=777)
    with pytest.raises(RateLimitExceededError):
        await svc.check_message_rate(user_id=777)


async def test_rate_limit_keyed_per_user_not_per_payload() -> None:
    # An abuser cannot "reset" their quota by varying request content: the throttle
    # is keyed by user id, so a single user's 31st message is blocked regardless.
    svc = _service()
    for _ in range(30):
        await svc.check_message_rate(user_id=42)
    with pytest.raises(RateLimitExceededError):
        await svc.check_message_rate(user_id=42)
    # A different user is unaffected (isolation).
    await svc.check_message_rate(user_id=43)


# --- Download abuse -------------------------------------------------------
async def test_daily_limit_blocks_excess_downloads() -> None:
    svc = _service()
    user = FakeUser(id=1, telegram_id=1, daily_download_count=10)  # free_daily_limit = 10
    with pytest.raises(DailyLimitExceededError):
        await svc.check_download(user)


async def test_cooldown_blocks_rapid_redownload() -> None:
    svc = _service()
    user = FakeUser(id=2, telegram_id=2)
    await svc.check_download(user)  # first arms the cooldown
    with pytest.raises(CooldownActiveError):
        await svc.check_download(user)  # immediate retry blocked


async def test_banned_user_cannot_download() -> None:
    svc = _service()
    user = FakeUser(id=3, telegram_id=3, is_banned=True)
    with pytest.raises(PermissionDeniedError):
        await svc.check_download(user)


async def test_owner_is_exempt_from_limits() -> None:
    svc = _service()
    owner = FakeUser(id=4, telegram_id=4, role="owner", daily_download_count=10_000)
    for _ in range(5):  # no daily cap, no cooldown for the owner
        await svc.check_download(owner)
