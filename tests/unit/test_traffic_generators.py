"""Unit tests for the traffic generators (MASTER_PLAN Task 11.8, §25.15.3)."""

from __future__ import annotations

import random

from tests.simulation.traffic import TRAFFIC_REGISTRY
from tests.simulation.traffic.base import TrafficGenerator
from tests.simulation.traffic.generators import (
    PeakHour,
    PlatformPattern,
    ScheduledSpike,
    Viral,
)
from tests.simulation.users import PROFILE_REGISTRY


def _rng(seed: int) -> random.Random:
    return random.Random(seed)  # noqa: S311 - deterministic test data, not crypto


def test_registry_has_all_five_generators() -> None:
    assert set(TRAFFIC_REGISTRY) == {
        "RandomTraffic",
        "ScheduledSpike",
        "PeakHour",
        "Viral",
        "PlatformPattern",
    }


def test_every_generator_plans_exactly_total_users_deterministically() -> None:
    for cls in TRAFFIC_REGISTRY.values():
        gen = cls()
        first = gen.plan(total_users=100, rng=_rng(1), window_s=60.0)
        second = gen.plan(total_users=100, rng=_rng(1), window_s=60.0)
        assert len(first) == 100
        assert [(s.user_id, s.profile, round(s.start_offset_s, 6)) for s in first] == [
            (s.user_id, s.profile, round(s.start_offset_s, 6)) for s in second
        ]


def test_offsets_within_window() -> None:
    for cls in TRAFFIC_REGISTRY.values():
        plan = cls().plan(total_users=200, rng=_rng(2), window_s=60.0)
        assert all(0.0 <= s.start_offset_s <= 60.0 for s in plan)


def test_only_known_profiles_assigned() -> None:
    known = set(PROFILE_REGISTRY.values())
    for cls in TRAFFIC_REGISTRY.values():
        plan = cls().plan(total_users=100, rng=_rng(3))
        assert {s.profile for s in plan} <= known


def test_scheduled_spike_clusters_at_end() -> None:
    plan = ScheduledSpike(spike_fraction=0.8, spike_window_s=30.0).plan(
        total_users=100, rng=_rng(4), window_s=60.0
    )
    in_spike = sum(1 for s in plan if s.start_offset_s >= 30.0)
    assert in_spike >= 20  # the ~20% spike cohort lands in the final 30s window


def test_viral_offsets_are_monotonic_nondecreasing() -> None:
    plan = Viral().plan(total_users=100, rng=_rng(5), window_s=60.0)
    offsets = [s.start_offset_s for s in plan]
    assert offsets == sorted(offsets)  # accelerating arrivals never go backwards


def test_peak_hour_concentrates_near_middle() -> None:
    plan = PeakHour().plan(total_users=500, rng=_rng(6), window_s=60.0)
    near_mid = sum(1 for s in plan if 20.0 <= s.start_offset_s <= 40.0)
    assert near_mid > 250  # majority within the central third


def test_platform_pattern_rejects_unknown_platform() -> None:
    try:
        PlatformPattern(platform="myspace")
    except ValueError as exc:
        assert "unknown platform" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for unknown platform")


def test_profiles_of_helper_matches_plan() -> None:
    plan = Viral().plan(total_users=10, rng=_rng(7))
    assert TrafficGenerator.profiles_of(plan) == [s.profile for s in plan]
