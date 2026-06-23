"""RateLimitService (MASTER_PLAN Component 9.2, Task 4.2).

The single home for every rate-limit decision (Section 14.5):

* per-user message throttle — Redis counter with a 60 s window
  (``rate_limit_messages_per_minute``);
* per-download daily limit and cooldown (Section 16.5), with the lazy daily-count
  reset (D-012) delegated to the repository.

Limit values are read via ``SettingsService`` (operator-tunable); counters live in
Redis via ``CacheService``. The authoritative daily count lives on the ``users``
row, so ``check_download`` takes the user row (not the cached snapshot).
"""

from __future__ import annotations

import datetime
from typing import Any

from domain.exceptions import (
    CooldownActiveError,
    DailyLimitExceededError,
    MaintenanceModeError,
    PermissionDeniedError,
    RateLimitExceededError,
)
from domain.protocols.repositories import UserRepositoryProtocol
from services.cache_service import CacheService
from services.settings_service import SettingsService

_MESSAGE_WINDOW_SECONDS = 60

# Effective-plan → settings keys (Section 13.4). V1 traffic is all ``free``; the
# ``premium`` keys are read only once V2 grants premium (Section 16.5 resolution).
_DAILY_LIMIT_KEY = {"free": "free_daily_limit", "premium": "premium_daily_limit"}
_COOLDOWN_KEY = {
    "free": "download_cooldown_seconds",
    "premium": "premium_download_cooldown_seconds",
}


class RateLimitService:
    def __init__(
        self,
        settings: SettingsService,
        cache: CacheService,
        repo: UserRepositoryProtocol[Any],
    ) -> None:
        self._settings = settings
        self._cache = cache
        self._repo = repo

    async def check_message_rate(self, user_id: int) -> None:
        """Throttle inbound messages per user (Section 14.5). Raises on exceed."""
        limit: int = await self._settings.get("rate_limit_messages_per_minute")
        count = await self._cache.incr_message_count(user_id, ttl=_MESSAGE_WINDOW_SECONDS)
        if count > limit:
            raise RateLimitExceededError("Too many requests. Please slow down.")

    async def check_download(self, user: Any) -> None:
        """Authorize a download request for ``user`` (Section 16.5).

        On success, arms the per-user cooldown. ``user`` is the authoritative
        ``users`` row (the daily count is reset lazily here, D-012).
        """
        if user.is_banned:  # defensive — AuthMiddleware already rejects banned users
            raise PermissionDeniedError("You are banned from using this bot.")

        if await self._settings.get("maintenance_mode"):
            raise MaintenanceModeError("The bot is under maintenance. Please try again later.")

        plan = _effective_plan(user)
        daily_limit: int = await self._settings.get(_DAILY_LIMIT_KEY[plan])
        cooldown: int = await self._settings.get(_COOLDOWN_KEY[plan])

        await self._repo.reset_daily_download_count_if_needed(user)
        if user.daily_download_count >= daily_limit:
            raise DailyLimitExceededError("Daily download limit reached. Try again tomorrow.")

        if await self._cache.is_on_cooldown(user.id):
            raise CooldownActiveError("Please wait before requesting another download.")

        await self._cache.set_cooldown(user.id, ttl=cooldown)


def _effective_plan(user: Any) -> str:
    """``premium`` while a premium grant is active, else ``free`` (Section 16.5)."""
    expires = user.premium_expires_at
    if user.is_premium and expires is not None and expires > datetime.datetime.now(datetime.UTC):
        return "premium"
    return "free"
