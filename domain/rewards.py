"""Reward taxonomy — the Reward Engine's open-for-extension core (D-075).

A referral (or any future source) grants one or more **Rewards**. Each reward has a
*type*; each type declares how multiple *active* rewards of that type **stack**. A
consumer (the download-limit logic today; ad delivery / queue / premium tomorrow)
asks the :class:`~services.reward_service.RewardService` for the *aggregated active
value* of a type — it never hard-codes a reward source (e.g. "referral bonus").

**Open/Closed Principle:** adding a new reward type is a two-line change here — a new
:class:`RewardType` member plus a :data:`REWARD_DEFINITIONS` entry. No engine or
existing-consumer code changes. The download limit no longer knows referrals exist;
it only knows the ``DAILY_DOWNLOAD_BONUS`` effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RewardType(str, Enum):
    """A kind of reward. The value is persisted verbatim in ``rewards.reward_type``.

    Only ``DAILY_DOWNLOAD_BONUS`` is consumed by existing business logic today; the
    others are recognised, grantable, and stack-defined, ready for their subsystems
    to consume them without touching the engine.
    """

    DAILY_DOWNLOAD_BONUS = "daily_download_bonus"  # +N downloads on the daily limit
    PREMIUM_DAYS = "premium_days"  # +N days of premium access
    DOWNLOAD_CREDITS = "download_credits"  # +N one-time downloads (consumed once)
    QUEUE_PRIORITY = "queue_priority"  # elevated queue priority level
    AD_FREE = "ad_free"  # no advertisements while active
    UNLOCK_QUALITY = "unlock_quality"  # unlock a media quality (param = quality code)


class StackingRule(Enum):
    """How multiple *active* rewards of one type combine (requirement §7).

    The rule is configured per type in :data:`REWARD_DEFINITIONS`; the engine applies
    it uniformly, so a new type just picks a rule.
    """

    SUM = "sum"  # additive — bonuses, credits, premium days
    MAX = "max"  # highest wins — a level (queue priority, quality tier)
    ANY = "any"  # boolean — "on" if at least one active reward exists (ad-free)

    def aggregate(self, values: list[int]) -> int:
        """Combine the ``value``s of the currently-active rewards of a type.

        Callers pass only *active* (non-expired) reward values; expiry is filtered
        upstream. ``ANY`` returns 1 when any active reward exists regardless of value.
        """
        if not values:
            return 0
        if self is StackingRule.SUM:
            return sum(values)
        if self is StackingRule.MAX:
            return max(values)
        return 1  # ANY


@dataclass(frozen=True, slots=True)
class RewardDefinition:
    """The stacking behaviour (and a human description) for one reward type."""

    reward_type: RewardType
    stacking: StackingRule
    description: str


# The registry — the single place a reward type declares how it stacks. Extend here.
REWARD_DEFINITIONS: dict[RewardType, RewardDefinition] = {
    RewardType.DAILY_DOWNLOAD_BONUS: RewardDefinition(
        RewardType.DAILY_DOWNLOAD_BONUS,
        StackingRule.SUM,
        "Extra downloads added to the daily limit.",
    ),
    RewardType.PREMIUM_DAYS: RewardDefinition(
        RewardType.PREMIUM_DAYS, StackingRule.SUM, "Extra days of premium access."
    ),
    RewardType.DOWNLOAD_CREDITS: RewardDefinition(
        RewardType.DOWNLOAD_CREDITS, StackingRule.SUM, "One-time download credits."
    ),
    RewardType.QUEUE_PRIORITY: RewardDefinition(
        RewardType.QUEUE_PRIORITY, StackingRule.MAX, "Elevated queue priority level."
    ),
    RewardType.AD_FREE: RewardDefinition(
        RewardType.AD_FREE, StackingRule.ANY, "No advertisements while active."
    ),
    RewardType.UNLOCK_QUALITY: RewardDefinition(
        RewardType.UNLOCK_QUALITY, StackingRule.MAX, "Unlock a higher media quality (param = code)."
    ),
}


def definition_for(reward_type: RewardType) -> RewardDefinition:
    """The :class:`RewardDefinition` for ``reward_type`` (KeyError if unregistered)."""
    return REWARD_DEFINITIONS[reward_type]
