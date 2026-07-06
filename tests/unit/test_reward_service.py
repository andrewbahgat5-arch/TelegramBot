"""Unit tests for RewardService (the generic Reward Engine, D-075)."""

from __future__ import annotations

import datetime

from domain.rewards import RewardType
from services.reward_service import RewardService
from tests.unit._fakes import FakeRewardRepo

_NOW = datetime.datetime(2026, 7, 6, 12, 0, tzinfo=datetime.UTC)


def _service(repo: FakeRewardRepo | None = None) -> tuple[RewardService, FakeRewardRepo]:
    repo = repo or FakeRewardRepo()
    return RewardService(repo, clock=lambda: _NOW), repo


async def test_grant_persists_a_reward() -> None:
    svc, repo = _service()
    reward = await svc.grant(7, RewardType.DAILY_DOWNLOAD_BONUS, value=5, source="referral")
    assert reward.user_id == 7
    assert reward.reward_type is RewardType.DAILY_DOWNLOAD_BONUS
    assert reward.value == 5
    assert reward.source == "referral"
    assert reward.expires_at is None  # permanent by default
    assert repo.rewards == [reward]


async def test_active_value_sums_daily_download_bonus() -> None:
    svc, _ = _service()
    await svc.grant(1, RewardType.DAILY_DOWNLOAD_BONUS, value=5, source="referral")
    await svc.grant(1, RewardType.DAILY_DOWNLOAD_BONUS, value=3, source="admin")
    assert await svc.active_value(1, RewardType.DAILY_DOWNLOAD_BONUS) == 8  # SUM


async def test_active_value_is_zero_without_rewards() -> None:
    svc, _ = _service()
    assert await svc.active_value(1, RewardType.DAILY_DOWNLOAD_BONUS) == 0


async def test_active_value_uses_max_for_queue_priority() -> None:
    svc, _ = _service()
    await svc.grant(1, RewardType.QUEUE_PRIORITY, value=1, source="admin")
    await svc.grant(1, RewardType.QUEUE_PRIORITY, value=3, source="admin")
    assert await svc.active_value(1, RewardType.QUEUE_PRIORITY) == 3  # MAX


async def test_active_value_uses_any_for_ad_free() -> None:
    svc, _ = _service()
    await svc.grant(1, RewardType.AD_FREE, value=0, source="admin")
    assert await svc.active_value(1, RewardType.AD_FREE) == 1  # ANY → "on"


async def test_expired_reward_is_excluded() -> None:
    svc, _ = _service()
    await svc.grant(
        1,
        RewardType.DAILY_DOWNLOAD_BONUS,
        value=5,
        source="referral",
        expires_at=_NOW - datetime.timedelta(seconds=1),  # already expired
    )
    await svc.grant(
        1,
        RewardType.DAILY_DOWNLOAD_BONUS,
        value=2,
        source="referral",
        expires_at=_NOW + datetime.timedelta(days=1),  # still active
    )
    assert await svc.active_value(1, RewardType.DAILY_DOWNLOAD_BONUS) == 2


async def test_active_value_is_scoped_to_the_user() -> None:
    svc, _ = _service()
    await svc.grant(1, RewardType.DAILY_DOWNLOAD_BONUS, value=5, source="referral")
    assert await svc.active_value(2, RewardType.DAILY_DOWNLOAD_BONUS) == 0


async def test_active_rewards_returns_only_active() -> None:
    svc, _ = _service()
    await svc.grant(1, RewardType.DAILY_DOWNLOAD_BONUS, value=5, source="referral")
    await svc.grant(
        1,
        RewardType.AD_FREE,
        value=0,
        source="admin",
        expires_at=_NOW - datetime.timedelta(seconds=1),
    )
    active = await svc.active_rewards(1)
    assert [r.reward_type for r in active] == [RewardType.DAILY_DOWNLOAD_BONUS]
