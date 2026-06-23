"""UserService (MASTER_PLAN Component 9.2, Task 4.1).

User registration, role management, ban administration, and lookups. Reads run
through the Redis user cache (D-014, Section 11.1 layer 3); every write to a
``users`` row invalidates that user's cache entry (Section 11.3). ``last_activity_at``
writes are debounced so the hot path does not write on every update (Section 9.2).

The service is framework-agnostic: it depends on ``UserRepositoryProtocol`` and
``CacheService`` only, never on the ORM model or aiogram types (Section 8). The bot
layer extracts identity primitives from the Telegram update and passes them in.
"""

from __future__ import annotations

import datetime
from typing import Any

from core.constants import LAST_ACTIVITY_DEBOUNCE_SECONDS
from core.logging import get_logger
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from domain.protocols.repositories import UserRepositoryProtocol
from services.cache_service import CacheService

_log = get_logger("services.user_service")


class UserService:
    def __init__(
        self,
        repo: UserRepositoryProtocol[Any],
        cache: CacheService,
        *,
        owner_telegram_id: int,
        debounce_seconds: int = LAST_ACTIVITY_DEBOUNCE_SECONDS,
    ) -> None:
        self._repo = repo
        self._cache = cache
        self._owner_telegram_id = owner_telegram_id
        self._debounce = datetime.timedelta(seconds=debounce_seconds)

    async def get_or_create_user(
        self,
        *,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        language: str | None = None,
    ) -> UserSnapshot:
        """Resolve a Telegram user to a snapshot, creating the row on first contact.

        Cache-first (D-014): a hit returns without touching Postgres. On a miss the
        row is loaded (or created) and the cache is populated.
        """
        cached = await self._cache.get_user(telegram_id)
        if cached is not None:
            return UserSnapshot.from_cache_dict(cached)

        row = await self._repo.get_by_telegram_id(telegram_id)
        if row is None:
            role = UserRole.OWNER if telegram_id == self._owner_telegram_id else UserRole.USER
            row = await self._repo.create_user(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                language=language,
                role=role.value,
            )
            _log.info("user_created", user_id=row.id, role=role.value)

        snapshot = UserSnapshot.from_row(row)
        await self._cache.set_user(telegram_id, snapshot.to_cache_dict())
        return snapshot

    async def record_activity(self, snapshot: UserSnapshot) -> None:
        """Persist ``last_activity_at`` at most once per debounce window per user."""
        now = datetime.datetime.now(datetime.UTC)
        last = snapshot.last_activity_at
        if last is not None and (now - last) < self._debounce:
            return
        await self._repo.touch_last_activity(snapshot.telegram_id, now)
        await self._cache.delete_user(snapshot.telegram_id)

    async def set_role(self, telegram_id: int, role: UserRole) -> UserSnapshot | None:
        """Assign ``role`` to a user. Returns the updated snapshot, or None if absent."""
        return await self._mutate(
            telegram_id, lambda row: _apply(row, role=role.value), event="user_role_changed"
        )

    async def ban(self, telegram_id: int, reason: str | None = None) -> UserSnapshot | None:
        """Ban a user, recording the audit fields (``banned_at``, ``ban_reason``)."""
        now = datetime.datetime.now(datetime.UTC)
        return await self._mutate(
            telegram_id,
            lambda row: _apply(row, is_banned=True, banned_at=now, ban_reason=reason),
            event="user_banned",
        )

    async def unban(self, telegram_id: int) -> UserSnapshot | None:
        """Lift a ban. The audit fields (``banned_at``, ``ban_reason``) are preserved."""
        return await self._mutate(
            telegram_id, lambda row: _apply(row, is_banned=False), event="user_unbanned"
        )

    async def _mutate(self, telegram_id: int, apply: Any, *, event: str) -> UserSnapshot | None:
        row = await self._repo.get_by_telegram_id(telegram_id)
        if row is None:
            return None
        apply(row)
        await self._repo.add(row)
        await self._cache.delete_user(telegram_id)
        _log.info(event, user_id=row.id)
        return UserSnapshot.from_row(row)


def _apply(row: Any, **fields: Any) -> None:
    for name, value in fields.items():
        setattr(row, name, value)
