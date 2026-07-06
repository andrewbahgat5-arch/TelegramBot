"""RewardRepository (Reward Engine, D-075).

Returns domain :class:`~domain.entities.reward.Reward` snapshots (not ORM rows), so
the service/consumer layers stay framework-free. Active lookups filter expiry in SQL
(``expires_at IS NULL OR expires_at > now``) so only currently-active rewards are
returned; the service aggregates them per the type's stacking rule.
"""

from __future__ import annotations

import datetime

from sqlalchemy import or_, select

from domain.entities.reward import Reward as RewardEntity
from domain.rewards import RewardType
from infrastructure.database.models import Reward
from infrastructure.database.repositories.base import SqlAlchemyRepository


class RewardRepository(SqlAlchemyRepository[Reward]):
    model = Reward

    async def create(
        self,
        *,
        user_id: int,
        reward_type: RewardType,
        value: int,
        param: str | None,
        source: str,
        expires_at: datetime.datetime | None,
    ) -> RewardEntity:
        row = Reward(
            user_id=user_id,
            reward_type=reward_type.value,
            value=value,
            param=param,
            source=source,
            granted_at=datetime.datetime.now(datetime.UTC),
            expires_at=expires_at,
        )
        await self.add(row)  # add + flush → id populated
        return RewardEntity.from_row(row)

    async def list_active(
        self, user_id: int, reward_type: RewardType, *, now: datetime.datetime
    ) -> list[RewardEntity]:
        result = await self.session.execute(
            select(Reward).where(
                Reward.user_id == user_id,
                Reward.reward_type == reward_type.value,
                or_(Reward.expires_at.is_(None), Reward.expires_at > now),
            )
        )
        return [RewardEntity.from_row(row) for row in result.scalars().all()]

    async def list_all_active(self, user_id: int, *, now: datetime.datetime) -> list[RewardEntity]:
        result = await self.session.execute(
            select(Reward).where(
                Reward.user_id == user_id,
                or_(Reward.expires_at.is_(None), Reward.expires_at > now),
            )
        )
        return [RewardEntity.from_row(row) for row in result.scalars().all()]
