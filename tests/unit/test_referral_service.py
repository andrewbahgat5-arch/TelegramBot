"""Unit tests for services/referral_service.py (Sprint 13.7; Reward Engine D-075).

A successful referral now grants a DAILY_DOWNLOAD_BONUS *reward* to both sides via
the Reward Engine (not a hard-coded column); stats/leaderboard derive the bonus from
active rewards.
"""

from __future__ import annotations

import datetime
import itertools
from typing import Any

import pytest

from domain.rewards import RewardType
from services.referral_service import ReferralService
from services.reward_service import RewardService
from tests.unit._fakes import FakeRewardRepo, FakeUser, FakeUserRepo

pytestmark = pytest.mark.asyncio


class _Ref:
    def __init__(self, referrer_id: int, referred_id: int, reward_granted: bool) -> None:
        self.referrer_id = referrer_id
        self.referred_id = referred_id
        self.reward_granted = reward_granted
        self.created_at = datetime.datetime.now(datetime.UTC)


class FakeReferralRepo:
    def __init__(self, users: FakeUserRepo) -> None:
        self._users = users
        self.rows: list[_Ref] = []

    async def create(
        self, *, referrer_id: int, referred_id: int, reward_granted: bool = True
    ) -> _Ref:
        row = _Ref(referrer_id, referred_id, reward_granted)
        self.rows.append(row)
        return row

    async def exists_for_referred(self, referred_id: int) -> bool:
        return any(r.referred_id == referred_id for r in self.rows)

    async def count_all(self) -> int:
        return len(self.rows)

    async def count_since(self, since: datetime.datetime) -> int:
        return sum(1 for r in self.rows if r.created_at >= since)

    async def count_rewarded(self) -> int:
        return sum(1 for r in self.rows if r.reward_granted)

    async def count_for_referrer(self, referrer_id: int) -> int:
        return sum(1 for r in self.rows if r.referrer_id == referrer_id)

    async def leaderboard(self, *, limit: int = 10) -> list[tuple[int, str | None, str, int, int]]:
        # (telegram_id, username, first_name, invites, user_db_id) — the service fills
        # rewards_earned from the Reward Engine, so this stays reward-agnostic.
        tally: dict[int, int] = {}
        for r in self.rows:
            tally[r.referrer_id] = tally.get(r.referrer_id, 0) + 1
        out: list[tuple[int, str | None, str, int, int]] = []
        for db_id, invites in sorted(tally.items(), key=lambda kv: kv[1], reverse=True)[:limit]:
            user = next((u for u in self._users.by_tid.values() if u.id == db_id), None)
            if user is None:
                continue
            out.append((user.telegram_id, user.username, user.first_name or "", invites, db_id))
        return out


class FakeSettings:
    def __init__(self, *, enabled: bool = True, reward: int = 5) -> None:
        self.values: dict[str, Any] = {
            "referral_enabled": enabled,
            "referral_reward_downloads": reward,
        }

    async def get(self, key: str) -> Any:
        return self.values[key]


def _service(
    *, enabled: bool = True, reward: int = 5, codes: list[str] | None = None
) -> tuple[ReferralService, FakeUserRepo, FakeReferralRepo, RewardService]:
    users = FakeUserRepo()
    referrals = FakeReferralRepo(users)
    rewards = RewardService(FakeRewardRepo())
    seq = iter(codes) if codes else itertools.count()
    svc = ReferralService(
        user_repo=users,
        referral_repo=referrals,
        settings=FakeSettings(enabled=enabled, reward=reward),
        rewards=rewards,
        bot_username="dangeriiivvBot",
        code_generator=(lambda: str(next(seq))),
    )
    return svc, users, referrals, rewards


def _add(users: FakeUserRepo, *, uid: int, tid: int, **kw: Any) -> FakeUser:
    user = FakeUser(id=uid, telegram_id=tid, **kw)
    users.by_tid[tid] = user
    return user


async def test_generate_code_is_idempotent() -> None:
    svc, users, _, _ = _service(codes=["abc123", "zzz999"])
    _add(users, uid=1, tid=100)
    first = await svc.generate_code(1)
    second = await svc.generate_code(1)
    assert first == "abc123"
    assert second == "abc123"  # not regenerated


async def test_generate_code_retries_on_collision() -> None:
    svc, users, _, _ = _service(codes=["dup", "dup", "fresh"])
    _add(users, uid=1, tid=100, referral_code="dup")  # "dup" already taken
    _add(users, uid=2, tid=200)
    code = await svc.generate_code(2)
    assert code == "fresh"


async def test_process_referral_grants_reward_to_both() -> None:
    svc, users, referrals, rewards = _service(reward=5)
    _add(users, uid=1, tid=100, referral_code="ref1")
    referred = _add(users, uid=2, tid=200)

    result = await svc.process_referral("ref1", 2)

    assert result.success and result.reason == "ok"
    assert result.referrer_telegram_id == 100
    assert result.reward_downloads == 5
    assert result.referrer_total_referrals == 1
    # Both sides now hold an active DAILY_DOWNLOAD_BONUS reward of 5 (D-075).
    assert await rewards.active_value(1, RewardType.DAILY_DOWNLOAD_BONUS) == 5
    assert await rewards.active_value(2, RewardType.DAILY_DOWNLOAD_BONUS) == 5
    assert referred.referred_by_id == 1
    assert len(referrals.rows) == 1


async def test_referral_reward_is_permanent() -> None:
    # The granted reward has no expiry (D-066 permanence preserved via the engine).
    svc, users, _, rewards = _service(reward=5)
    _add(users, uid=1, tid=100, referral_code="ref1")
    _add(users, uid=2, tid=200)
    await svc.process_referral("ref1", 2)
    granted = (await rewards.active_rewards(1))[0]
    assert granted.expires_at is None
    assert granted.source == "referral"


async def test_process_referral_disabled() -> None:
    svc, users, _, _ = _service(enabled=False)
    _add(users, uid=1, tid=100, referral_code="ref1")
    _add(users, uid=2, tid=200)
    result = await svc.process_referral("ref1", 2)
    assert not result.success and result.reason == "disabled"


async def test_process_referral_self_referral() -> None:
    svc, users, _, _ = _service()
    _add(users, uid=1, tid=100, referral_code="ref1")
    result = await svc.process_referral("ref1", 1)
    assert result.reason == "self_referral"


async def test_process_referral_unknown_code() -> None:
    svc, users, _, _ = _service()
    _add(users, uid=2, tid=200)
    result = await svc.process_referral("nope", 2)
    assert result.reason == "referrer_not_found"


async def test_process_referral_already_referred() -> None:
    svc, users, referrals, _ = _service()
    _add(users, uid=1, tid=100, referral_code="ref1")
    _add(users, uid=2, tid=200)
    await svc.process_referral("ref1", 2)
    result = await svc.process_referral("ref1", 2)
    assert result.reason == "already_referred"
    assert len(referrals.rows) == 1  # no duplicate


async def test_user_referral_stats_reports_active_bonus() -> None:
    svc, users, _, rewards = _service(codes=["myc0de"])
    _add(users, uid=1, tid=100)
    await rewards.grant(1, RewardType.DAILY_DOWNLOAD_BONUS, value=15, source="referral")
    stats = await svc.get_user_referral_stats(1)
    assert stats.referral_code == "myc0de"
    assert stats.referral_link == "https://t.me/dangeriiivvBot?start=ref_myc0de"
    assert stats.total_bonus_downloads == 15  # derived from active rewards
    assert stats.total_invited == 0


async def test_dashboard_and_leaderboard() -> None:
    svc, users, _, _ = _service()
    _add(users, uid=1, tid=100, referral_code="a", username="ahmed")
    _add(users, uid=2, tid=200, username="ali")
    _add(users, uid=3, tid=300, username="sara")
    await svc.process_referral("a", 2)
    await svc.process_referral("a", 3)

    dash = await svc.get_dashboard()
    assert dash.total_referrals == 2
    assert dash.referrals_today == 2
    assert dash.total_rewards_granted == 2
    assert dash.top_referrers[0].user_id == 100
    assert dash.top_referrers[0].invite_count == 2
    # The referrer earned two +5 daily-download rewards → 10 active bonus.
    assert dash.top_referrers[0].rewards_earned == 10
