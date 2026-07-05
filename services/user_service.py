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
from dataclasses import dataclass
from typing import Any

from core.constants import LAST_ACTIVITY_DEBOUNCE_SECONDS
from core.logging import get_logger
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from domain.protocols.repositories import UserRepositoryProtocol
from services.cache_service import CacheService

_log = get_logger("services.user_service")


@dataclass(frozen=True, slots=True)
class UserStats:
    """Aggregate user counts for the admin ``/stats`` command (Task 8.2).

    The richer cohort fields (joined today / this week, active today, premium, staff)
    feed the panel Statistics screen. They default to ``0`` so existing callers that
    only set the core three keep working.
    """

    total_users: int
    banned_users: int
    total_downloads: int
    new_today: int = 0
    new_this_week: int = 0
    active_today: int = 0
    premium_users: int = 0
    staff_users: int = 0
    # Enhanced activity metrics (Sprint 13.4). Default 0 so callers that build a
    # UserStats directly (tests, legacy paths) keep working unchanged.
    active_24h: int = 0
    active_7d: int = 0
    active_30d: int = 0
    inactive_5d: int = 0
    inactive_7d: int = 0
    inactive_30d: int = 0
    active_current_hour: int = 0
    active_previous_hour: int = 0


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

    async def find(self, telegram_id: int) -> UserSnapshot | None:
        """Look up a user without creating one (admin ``/userinfo``). Bypasses the cache."""
        row = await self._repo.get_by_telegram_id(telegram_id)
        return None if row is None else UserSnapshot.from_row(row)

    async def get_stats(self) -> UserStats:
        """Aggregate counts for admin stats (totals, today/week cohorts, premium, staff)."""
        now = datetime.datetime.now(datetime.UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - datetime.timedelta(days=7)
        return UserStats(
            total_users=await self._repo.count_all(),
            banned_users=await self._repo.count_banned(),
            total_downloads=await self._repo.sum_total_downloads(),
            new_today=await self._repo.count_created_since(today_start),
            new_this_week=await self._repo.count_created_since(week_ago),
            active_today=await self._repo.count_active_since(today_start),
            premium_users=await self._repo.count_premium(),
            staff_users=await self._repo.count_staff(),
            active_24h=await self._repo.count_active_in_hours(24),
            active_7d=await self._repo.count_active_in_hours(24 * 7),
            active_30d=await self._repo.count_active_in_hours(24 * 30),
            inactive_5d=await self._repo.count_inactive_days(5),
            inactive_7d=await self._repo.count_inactive_days(7),
            inactive_30d=await self._repo.count_inactive_days(30),
            active_current_hour=await self._repo.count_active_current_hour(),
            active_previous_hour=await self._repo.count_active_previous_hour(),
        )

    async def list_users(self, *, limit: int = 30, offset: int = 0) -> list[UserSnapshot]:
        """A page of users for the owner ``/users`` listing (Task 8.2 follow-up #19)."""
        rows = await self._repo.list_paginated(limit=limit, offset=offset)
        return [UserSnapshot.from_row(row) for row in rows]

    async def set_role(self, telegram_id: int, role: UserRole) -> UserSnapshot | None:
        """Assign ``role`` to a user. Returns the updated snapshot, or None if absent."""
        return await self._mutate(
            telegram_id, lambda row: _apply(row, role=role.value), event="user_role_changed"
        )

    async def set_language(self, telegram_id: int, language: str) -> UserSnapshot | None:
        """Persist a user's explicitly chosen UI language (Sprint 11.5).

        Callers validate ``language`` against ``core.i18n.list_enabled_locales()``
        before calling this — this method just writes whatever it's given.
        """
        return await self._mutate(
            telegram_id, lambda row: _apply(row, language=language), event="user_language_changed"
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
        """Lift a ban and clear the ban fields (``banned_at``, ``ban_reason``) → NULL.

        An unbanned user has no active ban, so the reason/timestamp are cleared rather
        than retained (Owner directive 2026-06-26, D-054): a non-banned user must never
        show a stale ban reason. Durable ban history lives in the audit log (V3).
        """
        return await self._mutate(
            telegram_id,
            lambda row: _apply(row, is_banned=False, banned_at=None, ban_reason=None),
            event="user_unbanned",
        )

    async def set_premium(
        self,
        telegram_id: int,
        *,
        is_premium: bool,
        expires_at: datetime.datetime | None = None,
    ) -> UserSnapshot | None:
        """Toggle a user's premium flag (and ``premium_expires_at``). Returns the snapshot.

        A V1 data write only: it sets the existing ``users`` columns. Premium *enforcement*
        (limits / cooldowns / queue priority) stays V2, but the audience/ads layer keys off
        ``is_premium`` immediately (the PLAN dimension), so a toggle changes which campaigns
        a user matches. Clearing premium also clears ``premium_expires_at``.
        """
        return await self._mutate(
            telegram_id,
            lambda row: _apply(
                row,
                is_premium=is_premium,
                premium_expires_at=expires_at if is_premium else None,
            ),
            event="user_premium_changed",
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
