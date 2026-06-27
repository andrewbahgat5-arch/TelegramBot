"""Premium user profile (MASTER_PLAN §25.15.1) — V2 stub, disabled in V1.

Higher frequency, priority-queue usage, larger volumes. Intentionally **not**
registered in ``PROFILE_REGISTRY`` (so the CLI cannot select it) until the premium
tier exists (V2). The class is present so the V2 behavior is captured and the
simulation framework needs no structural change to enable it.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import ClassVar

from tests.simulation.actions import ActionKind, SimulatedAction
from tests.simulation.users.base import UserProfile


class PremiumProfile(UserProfile):
    name = "Premium"
    enabled: ClassVar[bool] = False  # V2 — premium tier not enforced in V1

    def actions(self) -> Iterator[SimulatedAction]:
        yield SimulatedAction(ActionKind.START, delay_before=0.0)
        for _ in range(self._rng.randint(20, 50)):
            idle = self._rng.uniform(60.0, 180.0)
            yield SimulatedAction(ActionKind.SEND_URL, delay_before=idle, url=self._pick_url())
            yield SimulatedAction(
                ActionKind.CLICK_QUALITY,
                delay_before=self._rng.uniform(1, 3),
                is_download=True,
                label="priority",
            )
