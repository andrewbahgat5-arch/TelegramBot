"""Traffic-generation base types (MASTER_PLAN §25.15.3).

A traffic generator turns a target user count into a deterministic ``TrafficPlan``:
an ordered list of :class:`Spawn`s, each pairing a user with a profile and a
start offset (seconds from the run start). The stub runner consumes the profile
mix; the live sandbox runner (Phase B) also honors the start offsets to reproduce
spikes, peaks, and viral curves.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from tests.simulation.users.base import UserProfile

TrafficPlan = list["Spawn"]


@dataclass(frozen=True, slots=True)
class Spawn:
    user_id: int
    profile: type[UserProfile]
    start_offset_s: float


class TrafficGenerator(ABC):
    """Produces a deterministic spawn plan for ``total_users`` over ``window_s``."""

    name: ClassVar[str] = "base"

    @abstractmethod
    def plan(self, *, total_users: int, rng: random.Random, window_s: float = 60.0) -> TrafficPlan:
        """Return exactly ``total_users`` spawns."""

    @staticmethod
    def profiles_of(plan: TrafficPlan) -> list[type[UserProfile]]:
        """Extract the per-user profile assignment (the stub runner's input)."""
        return [spawn.profile for spawn in plan]
