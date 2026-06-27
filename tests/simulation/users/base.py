"""UserProfile base class (MASTER_PLAN §25.15.1, component 25.15.8)."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import ClassVar

from tests.simulation.actions import SimulatedAction

# A small pool of fixed, deterministic URLs so dry-runs are reproducible and never
# hit the network. The real sandbox transport (Phase B) uses the same set.
SAMPLE_URLS: tuple[str, ...] = (
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.tiktok.com/@user/video/7000000000000000000",
    "https://twitter.com/user/status/1500000000000000000",
    "https://www.instagram.com/reel/ABCdef123/",
)


class UserProfile(ABC):
    """Base for all simulated user behaviors.

    A profile is deterministic given the same ``user_id`` and seeded ``rng``: it
    yields the action stream for one simulated session (≈ one user's day).
    """

    name: ClassVar[str] = "base"

    def __init__(self, user_id: int, rng: random.Random) -> None:
        self.user_id = user_id
        self._rng = rng

    @abstractmethod
    def actions(self) -> Iterator[SimulatedAction]:
        """Yield this user's scheduled actions for one session."""

    def _pick_url(self) -> str:
        return self._rng.choice(SAMPLE_URLS)
