"""Unit tests for the five V1 user profiles (MASTER_PLAN Task 11.7, §25.15.1)."""

from __future__ import annotations

import random
from pathlib import Path

from core.config import Settings
from tests.simulation.bot_client.client import StubBotClient
from tests.simulation.runner import SimulationRunner
from tests.simulation.users import PROFILE_REGISTRY
from tests.simulation.users.premium import PremiumProfile

ENV_EXAMPLE = str(Path(__file__).resolve().parents[2] / ".env.example")


def _settings() -> Settings:
    return Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]


def _rng(seed: int) -> random.Random:
    return random.Random(seed)  # noqa: S311 - deterministic test data, not crypto


def test_v1_registry_has_four_profiles_excluding_premium() -> None:
    assert set(PROFILE_REGISTRY) == {"Casual", "Active", "Heavy", "Abuse"}
    assert "Premium" not in PROFILE_REGISTRY


def test_premium_profile_is_disabled_for_v1() -> None:
    assert PremiumProfile.enabled is False
    assert PremiumProfile.name == "Premium"


def test_each_profile_emits_deterministic_actions() -> None:
    for cls in PROFILE_REGISTRY.values():
        first = list(cls(user_id=1, rng=_rng(99)).actions())
        second = list(cls(user_id=1, rng=_rng(99)).actions())
        assert first, f"{cls.name} emitted no actions"
        assert [a.kind for a in first] == [a.kind for a in second]
        assert [round(a.delay_before, 6) for a in first] == [
            round(a.delay_before, 6) for a in second
        ]


async def test_abuse_profile_is_fully_blocked() -> None:
    runner = SimulationRunner(
        settings=_settings(), client=StubBotClient(rng=_rng(5)), seed=5
    )
    summary = await runner.run(level="L1", profiles=[PROFILE_REGISTRY["Abuse"]])
    # The core requirement (§25.15.1 / M-22): zero successful downloads for abusers.
    assert summary.successful_downloads == 0
    assert summary.blocked_downloads > 0


async def test_casual_profile_downloads_succeed() -> None:
    runner = SimulationRunner(
        settings=_settings(), client=StubBotClient(rng=_rng(11)), seed=11
    )
    summary = await runner.run(level="L1", profiles=[PROFILE_REGISTRY["Casual"]])
    assert summary.successful_downloads > 0
    assert summary.blocked_downloads == 0
