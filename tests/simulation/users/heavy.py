"""Heavy user profile (MASTER_PLAN §25.15.1).

Continuous requests, large files, ~30 s between actions.
"""

from __future__ import annotations

from collections.abc import Iterator

from tests.simulation.actions import ActionKind, SimulatedAction
from tests.simulation.users import register_profile
from tests.simulation.users.base import UserProfile


@register_profile
class HeavyProfile(UserProfile):
    name = "Heavy"

    def actions(self) -> Iterator[SimulatedAction]:
        yield SimulatedAction(ActionKind.START, delay_before=0.0)
        for _ in range(self._rng.randint(20, 40)):
            idle = self._rng.uniform(25.0, 35.0)  # ~30 s think-time
            yield SimulatedAction(ActionKind.SEND_URL, delay_before=idle, url=self._pick_url())
            yield SimulatedAction(ActionKind.CLICK_FORMAT, delay_before=self._rng.uniform(1, 3))
            yield SimulatedAction(
                ActionKind.CLICK_QUALITY,
                delay_before=self._rng.uniform(1, 3),
                is_download=True,
                label="large",
            )
