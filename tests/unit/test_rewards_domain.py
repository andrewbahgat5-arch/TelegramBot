"""Unit tests for the reward taxonomy (`domain/rewards.py`) and the Reward entity.

These guard the Open/Closed seam: every reward type has a stacking definition, and
the stacking rules aggregate active rewards as specified.
"""

from __future__ import annotations

import datetime

import pytest

from domain.entities.reward import Reward
from domain.rewards import REWARD_DEFINITIONS, RewardType, StackingRule, definition_for

_NOW = datetime.datetime(2026, 7, 6, 12, 0, tzinfo=datetime.UTC)


def test_every_reward_type_has_a_definition() -> None:
    # OCP guard: a new RewardType without a registry entry fails here, not silently.
    for rt in RewardType:
        assert rt in REWARD_DEFINITIONS
        assert REWARD_DEFINITIONS[rt].reward_type is rt


def test_definition_for_daily_download_bonus_sums() -> None:
    assert definition_for(RewardType.DAILY_DOWNLOAD_BONUS).stacking is StackingRule.SUM


def test_reward_type_values_are_stable_strings() -> None:
    # Persisted in rewards.reward_type — the string values must not drift.
    assert RewardType.DAILY_DOWNLOAD_BONUS.value == "daily_download_bonus"
    assert RewardType.AD_FREE.value == "ad_free"


@pytest.mark.parametrize(
    ("rule", "values", "expected"),
    [
        (StackingRule.SUM, [5, 3, 2], 10),
        (StackingRule.SUM, [], 0),
        (StackingRule.MAX, [1, 4, 2], 4),
        (StackingRule.MAX, [], 0),
        (StackingRule.ANY, [0, 0], 1),  # presence of any active reward → "on"
        (StackingRule.ANY, [7], 1),
        (StackingRule.ANY, [], 0),
    ],
)
def test_stacking_rule_aggregate(rule: StackingRule, values: list[int], expected: int) -> None:
    assert rule.aggregate(values) == expected


def _reward(expires_at: datetime.datetime | None) -> Reward:
    return Reward(
        id=1,
        user_id=1,
        reward_type=RewardType.DAILY_DOWNLOAD_BONUS,
        value=5,
        param=None,
        source="referral",
        granted_at=_NOW,
        expires_at=expires_at,
    )


def test_reward_permanent_is_active() -> None:
    assert _reward(expires_at=None).is_active(_NOW) is True


def test_reward_future_expiry_is_active() -> None:
    assert _reward(expires_at=_NOW + datetime.timedelta(days=1)).is_active(_NOW) is True


def test_reward_past_expiry_is_inactive() -> None:
    assert _reward(expires_at=_NOW - datetime.timedelta(seconds=1)).is_active(_NOW) is False
