"""SubscriptionService — the ONLY subscription write path (VERSION_2_MASTER_PLAN §5.1).

Grant / extend / remove / set_expiration with the V2-D-022 semantics. The one-active-row
invariant is enforced by the DB partial unique index (V2-D-003), not by an application
check: a grant that would collide is prevented by first canceling the current active row
in the same transaction. Every mutation emits a structured audit log with the actor
(``granted_by``). Future payment providers call this same service — they are subscription
*sources*, not new architecture (V2-D-006).

In V2.1 no admin UI calls this yet (shadow mode); it exists so V2.2 wires the panel to a
tested service and so the backfill script can use it. ``invalidate_user`` is an optional
hook the caller supplies to drop the user's cached snapshot after a write (wired live at
cutover); in shadow mode nothing reads the resolved entitlements, so it may be ``None``.
"""

from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable

from core.logging import get_logger
from domain.entities.subscription import Subscription as SubscriptionEntity
from domain.enums import SubscriptionSource, SubscriptionStatus
from domain.exceptions import AppError
from infrastructure.database.repositories.plan import PlanRepository
from infrastructure.database.repositories.subscription import SubscriptionRepository

_log = get_logger("services.subscriptions")

_DEFAULT_PAID_PLAN = "premium"

Clock = Callable[[], datetime.datetime]
Invalidator = Callable[[int], Awaitable[None]]


class SubscriptionError(AppError):
    """Raised when a subscription write cannot be performed (e.g. unknown plan)."""


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class SubscriptionService:
    def __init__(
        self,
        subscriptions: SubscriptionRepository,
        plans: PlanRepository,
        *,
        clock: Clock = _utcnow,
        invalidate_user: Invalidator | None = None,
    ) -> None:
        self._subs = subscriptions
        self._plans = plans
        self._clock = clock
        self._invalidate_user = invalidate_user

    async def grant(
        self,
        user_id: int,
        duration: datetime.timedelta,
        *,
        granted_by: int | None,
        plan_code: str = _DEFAULT_PAID_PLAN,
        source: SubscriptionSource = SubscriptionSource.MANUAL_GRANT,
    ) -> SubscriptionEntity:
        """Start a fresh subscription **now**, expiring after ``duration`` (V2-D-022).

        Any current active row is canceled first, so "grant" always means "this plan,
        from now, for this long" regardless of prior state.
        """
        now = self._clock()
        plan_id = await self._plan_id(plan_code)
        await self._cancel_active(user_id, now)
        row = await self._subs.create_active(
            user_id=user_id,
            plan_id=plan_id,
            source=source.value,
            starts_at=now,
            expires_at=now + duration,
            granted_by=granted_by,
        )
        await self._audit("grant", user_id, granted_by, new_expiry=row.expires_at)
        await self._after_write(user_id)
        return SubscriptionEntity.from_row(row)

    async def extend(
        self,
        user_id: int,
        duration: datetime.timedelta,
        *,
        granted_by: int | None,
        plan_code: str = _DEFAULT_PAID_PLAN,
    ) -> SubscriptionEntity:
        """Add ``duration`` to the current expiry if active, else start now (V2-D-022)."""
        now = self._clock()
        active = await self._subs.get_active_for_user(user_id)
        if active is not None:
            old_expiry = active.expires_at
            await self._subs.set_expiry(active, active.expires_at + duration, now=now)
            await self._audit(
                "extend", user_id, granted_by, old_expiry=old_expiry, new_expiry=active.expires_at
            )
            await self._after_write(user_id)
            return SubscriptionEntity.from_row(active)
        # No active row — extend-from-now is a grant.
        return await self.grant(user_id, duration, granted_by=granted_by, plan_code=plan_code)

    async def set_expiration(
        self,
        user_id: int,
        expires_at: datetime.datetime,
        *,
        granted_by: int | None,
        plan_code: str = _DEFAULT_PAID_PLAN,
    ) -> SubscriptionEntity:
        """Override the active row's expiry absolutely; create one if none exists (V2-D-022)."""
        now = self._clock()
        active = await self._subs.get_active_for_user(user_id)
        if active is not None:
            old_expiry = active.expires_at
            await self._subs.set_expiry(active, expires_at, now=now)
            await self._audit(
                "set_expiration", user_id, granted_by, old_expiry=old_expiry, new_expiry=expires_at
            )
            await self._after_write(user_id)
            return SubscriptionEntity.from_row(active)
        plan_id = await self._plan_id(plan_code)
        row = await self._subs.create_active(
            user_id=user_id,
            plan_id=plan_id,
            source=SubscriptionSource.MANUAL_GRANT.value,
            starts_at=now,
            expires_at=expires_at,
            granted_by=granted_by,
        )
        await self._audit("set_expiration", user_id, granted_by, new_expiry=expires_at)
        await self._after_write(user_id)
        return SubscriptionEntity.from_row(row)

    async def remove(self, user_id: int, *, removed_by: int | None) -> bool:
        """Cancel the active subscription (immediate downgrade to Free). No-op if none."""
        now = self._clock()
        active = await self._subs.get_active_for_user(user_id)
        if active is None:
            return False
        await self._subs.set_status(active, SubscriptionStatus.CANCELED, now=now)
        await self._audit("remove", user_id, removed_by, old_expiry=active.expires_at)
        await self._after_write(user_id)
        return True

    # --- internals --------------------------------------------------------
    async def _plan_id(self, plan_code: str) -> int:
        plan = await self._plans.get_by_code(plan_code)
        if plan is None:
            raise SubscriptionError(f"unknown plan code: {plan_code!r}")
        return plan.id

    async def _cancel_active(self, user_id: int, now: datetime.datetime) -> None:
        active = await self._subs.get_active_for_user(user_id)
        if active is not None:
            await self._subs.set_status(active, SubscriptionStatus.CANCELED, now=now)

    async def _after_write(self, user_id: int) -> None:
        if self._invalidate_user is not None:
            await self._invalidate_user(user_id)

    async def _audit(
        self,
        action: str,
        user_id: int,
        actor: int | None,
        *,
        old_expiry: datetime.datetime | None = None,
        new_expiry: datetime.datetime | None = None,
    ) -> None:
        _log.info(
            "subscription_changed",
            action=action,
            user_id=user_id,
            actor=actor,
            old_expiry=old_expiry.isoformat() if old_expiry else None,
            new_expiry=new_expiry.isoformat() if new_expiry else None,
        )
