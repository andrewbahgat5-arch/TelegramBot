"""RewardService — the generic Reward Engine (D-075).

A referral (or any future source) grants **Rewards** through :meth:`grant`. A
consumer asks :meth:`active_value` for the aggregated, currently-active value of a
reward *type* — the engine filters expired rewards and applies the type's stacking
rule (:mod:`domain.rewards`). Consumers name an *effect* (e.g.
``DAILY_DOWNLOAD_BONUS``); they never reference a reward *source*, so a new reward
type or a new granting source needs no change here (Open/Closed Principle).

Framework-free (Section 8): depends only on a repository protocol and a clock.
``user_id`` arguments are ``users.id`` (DB ids), matching the ``rewards`` FK.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable

from domain.entities.reward import Reward
from domain.protocols.repositories import RewardRepositoryProtocol
from domain.rewards import RewardType, definition_for


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class RewardService:
    def __init__(
        self,
        repo: RewardRepositoryProtocol,
        *,
        clock: Callable[[], datetime.datetime] = _utcnow,
    ) -> None:
        self._repo = repo
        self._clock = clock

    async def grant(
        self,
        user_id: int,
        reward_type: RewardType,
        *,
        value: int = 0,
        param: str | None = None,
        source: str = "",
        expires_at: datetime.datetime | None = None,
    ) -> Reward:
        """Grant a reward to a user. ``expires_at=None`` is permanent (never expires)."""
        return await self._repo.create(
            user_id=user_id,
            reward_type=reward_type,
            value=value,
            param=param,
            source=source,
            expires_at=expires_at,
        )

    async def active_value(self, user_id: int, reward_type: RewardType) -> int:
        """Aggregated value of the user's currently-active rewards of ``reward_type``.

        Applies the type's configured stacking rule (SUM / MAX / ANY). Returns 0 when
        the user has no active reward of that type.
        """
        rewards = await self._repo.list_active(user_id, reward_type, now=self._clock())
        return definition_for(reward_type).stacking.aggregate([r.value for r in rewards])

    async def active_rewards(self, user_id: int) -> list[Reward]:
        """Every currently-active reward the user holds (any type)."""
        return await self._repo.list_all_active(user_id, now=self._clock())
