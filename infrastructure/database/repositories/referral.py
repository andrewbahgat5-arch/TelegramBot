"""ReferralRepository (Sprint 13.7)."""

from __future__ import annotations

import datetime

from sqlalchemy import func, select

from infrastructure.database.models import Referral, User
from infrastructure.database.repositories.base import SqlAlchemyRepository


class ReferralRepository(SqlAlchemyRepository[Referral]):
    model = Referral

    async def create(
        self, *, referrer_id: int, referred_id: int, reward_granted: bool = True
    ) -> Referral:
        """Insert a referral row (referrer/referred are ``users.id``, not telegram ids)."""
        referral = Referral(
            referrer_id=referrer_id, referred_id=referred_id, reward_granted=reward_granted
        )
        return await self.add(referral)

    async def exists_for_referred(self, referred_id: int) -> bool:
        """True if this user has already been referred (``referred_id`` is unique)."""
        result = await self.session.execute(
            select(func.count()).select_from(Referral).where(Referral.referred_id == referred_id)
        )
        return int(result.scalar_one()) > 0

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(Referral))
        return int(result.scalar_one())

    async def count_since(self, since: datetime.datetime) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Referral).where(Referral.created_at >= since)
        )
        return int(result.scalar_one())

    async def count_rewarded(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Referral).where(Referral.reward_granted.is_(True))
        )
        return int(result.scalar_one())

    async def count_for_referrer(self, referrer_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Referral).where(Referral.referrer_id == referrer_id)
        )
        return int(result.scalar_one())

    async def leaderboard(self, *, limit: int = 10) -> list[tuple[int, str | None, str, int, int]]:
        """Top referrers as ``(telegram_id, username, first_name, invites, bonus)``.

        Joined to ``users`` so a single query yields the display fields and the
        referrer's accumulated bonus, ordered by invite count DESC.
        """
        invites = func.count(Referral.id)
        result = await self.session.execute(
            select(
                User.telegram_id,
                User.username,
                User.first_name,
                invites,
                User.referral_bonus_downloads,
            )
            .join(User, User.id == Referral.referrer_id)
            .group_by(
                User.telegram_id,
                User.username,
                User.first_name,
                User.referral_bonus_downloads,
            )
            .order_by(invites.desc())
            .limit(limit)
        )
        return [
            (int(tid), username, first_name or "", int(count), int(bonus))
            for tid, username, first_name, count, bonus in result.all()
        ]
