"""AI-controlled traffic generators (MASTER_PLAN §25.15.3).

Five generators, each a deterministic function of (total_users, seed):

* ``RandomTraffic``   — sample profiles per a configured distribution.
* ``ScheduledSpike``  — most users arrive within a short spike window.
* ``PeakHour``        — arrivals cluster around the middle of the window.
* ``Viral``           — one piece of content; arrivals accelerate over time.
* ``PlatformPattern`` — platform-skewed profile mix (e.g. TikTok-heavy weekend).
"""

from __future__ import annotations

import random
from typing import ClassVar

from tests.simulation.traffic import register_generator
from tests.simulation.traffic.base import Spawn, TrafficGenerator, TrafficPlan
from tests.simulation.users import PROFILE_REGISTRY
from tests.simulation.users.base import UserProfile

# Realistic V1 default mix: mostly casual, some active/heavy, a little abuse.
_DEFAULT_MIX: dict[str, float] = {"Casual": 0.6, "Active": 0.25, "Heavy": 0.1, "Abuse": 0.05}


def _weighted_profiles(
    mix: dict[str, float], total: int, rng: random.Random
) -> list[type[UserProfile]]:
    names = list(mix)
    weights = [mix[n] for n in names]
    chosen = rng.choices(names, weights=weights, k=total)
    return [PROFILE_REGISTRY[n] for n in chosen]


@register_generator
class RandomTraffic(TrafficGenerator):
    name = "RandomTraffic"

    def __init__(self, mix: dict[str, float] | None = None) -> None:
        self._mix = mix or _DEFAULT_MIX

    def plan(self, *, total_users: int, rng: random.Random, window_s: float = 60.0) -> TrafficPlan:
        profiles = _weighted_profiles(self._mix, total_users, rng)
        return [
            Spawn(i + 1, profiles[i], rng.uniform(0.0, window_s)) for i in range(total_users)
        ]


@register_generator
class ScheduledSpike(TrafficGenerator):
    name = "ScheduledSpike"

    def __init__(self, spike_fraction: float = 0.9, spike_window_s: float = 30.0) -> None:
        self._spike_fraction = spike_fraction
        self._spike_window_s = spike_window_s

    def plan(self, *, total_users: int, rng: random.Random, window_s: float = 60.0) -> TrafficPlan:
        profiles = _weighted_profiles(_DEFAULT_MIX, total_users, rng)
        spike_count = int(total_users * self._spike_fraction)
        spawns: list[Spawn] = []
        for i in range(total_users):
            if i < spike_count:
                # baseline arrivals spread across the pre-spike window
                offset = rng.uniform(0.0, max(window_s - self._spike_window_s, 0.0))
            else:
                # the spike: clustered at the end of the window
                offset = window_s - rng.uniform(0.0, self._spike_window_s)
            spawns.append(Spawn(i + 1, profiles[i], offset))
        return spawns


@register_generator
class PeakHour(TrafficGenerator):
    name = "PeakHour"

    def plan(self, *, total_users: int, rng: random.Random, window_s: float = 60.0) -> TrafficPlan:
        profiles = _weighted_profiles(_DEFAULT_MIX, total_users, rng)
        mid = window_s / 2
        spread = window_s / 6 or 1.0
        spawns: list[Spawn] = []
        for i in range(total_users):
            offset = min(max(rng.gauss(mid, spread), 0.0), window_s)  # cluster around mid
            spawns.append(Spawn(i + 1, profiles[i], offset))
        return spawns


@register_generator
class Viral(TrafficGenerator):
    name = "Viral"

    def plan(self, *, total_users: int, rng: random.Random, window_s: float = 60.0) -> TrafficPlan:
        # One piece of content spreading: arrivals accelerate (quadratic curve), so
        # later users pile up — the thundering-herd shape. Profiles drawn live.
        active = PROFILE_REGISTRY["Active"]
        spawns: list[Spawn] = []
        for i in range(total_users):
            fraction = (i / total_users) ** 2 if total_users else 0.0
            spawns.append(Spawn(i + 1, active, fraction * window_s))
        return spawns


@register_generator
class PlatformPattern(TrafficGenerator):
    name = "PlatformPattern"

    # Platform-skewed mixes (e.g. a TikTok-heavy weekend leans on quick casual use).
    _PATTERNS: ClassVar[dict[str, dict[str, float]]] = {
        "tiktok": {"Casual": 0.7, "Active": 0.2, "Heavy": 0.07, "Abuse": 0.03},
        "youtube": {"Casual": 0.45, "Active": 0.3, "Heavy": 0.2, "Abuse": 0.05},
    }

    def __init__(self, platform: str = "tiktok") -> None:
        if platform not in self._PATTERNS:
            raise ValueError(f"unknown platform {platform!r}; expected {sorted(self._PATTERNS)}")
        self.platform = platform
        self._mix = self._PATTERNS[platform]

    def plan(self, *, total_users: int, rng: random.Random, window_s: float = 60.0) -> TrafficPlan:
        profiles = _weighted_profiles(self._mix, total_users, rng)
        return [
            Spawn(i + 1, profiles[i], rng.uniform(0.0, window_s)) for i in range(total_users)
        ]
