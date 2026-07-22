"""SubscriptionRepository (VERSION_2_MASTER_PLAN §5.1, §6.2).

Never commits (the caller owns the transaction). The one-active-row invariant is a
DB partial unique index (``ux_subscriptions_one_active``); this repo relies on it
rather than re-checking in Python, so concurrent grants fail at the database, not in a
racy application check (V2-D-003).
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from sqlalchemy import func, select

from core.uuid7 import uuid7
from domain.enums import SubscriptionStatus
from infrastructure.database.models import Subscription
from infrastructure.database.repositories.base import SqlAlchemyRepository


class SubscriptionRepository(SqlAlchemyRepository[Subscription]):
    model = Subscription

    async def get_active_for_user(self, user_id: int) -> Subscription | None:
        """The user's single active row (guaranteed ≤1 by the partial unique index)."""
        result = await self.session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE.value,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_active(
        self,
        *,
        user_id: int,
        plan_id: int,
        source: str,
        starts_at: datetime.datetime,
        expires_at: datetime.datetime,
        granted_by: int | None,
    ) -> Subscription:
        """Insert a new ``active`` subscription with a fresh UUIDv7 id."""
        row = Subscription(
            id=uuid7(),
            user_id=user_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE.value,
            source=source,
            starts_at=starts_at,
            expires_at=expires_at,
            granted_by=granted_by,
        )
        return await self.add(row)

    async def set_expiry(
        self, row: Subscription, expires_at: datetime.datetime, *, now: datetime.datetime
    ) -> None:
        row.expires_at = expires_at
        row.updated_at = now
        await self.session.flush()

    async def set_status(
        self, row: Subscription, status: SubscriptionStatus, *, now: datetime.datetime
    ) -> None:
        row.status = status.value
        row.updated_at = now
        await self.session.flush()

    async def count_active_by_plan(self) -> Sequence[tuple[int, int]]:
        """``[(plan_id, count), …]`` over active rows — for the subscriptions_active gauge."""
        result = await self.session.execute(
            select(Subscription.plan_id, func.count())
            .where(Subscription.status == SubscriptionStatus.ACTIVE.value)
            .group_by(Subscription.plan_id)
        )
        return [(int(pid), int(cnt)) for pid, cnt in result.all()]
