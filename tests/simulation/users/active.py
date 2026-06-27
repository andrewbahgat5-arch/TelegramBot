"""Active user profile (MASTER_PLAN §25.15.1).

5-20 downloads/day, varied formats, ~5 min between actions.
"""

from __future__ import annotations

from collections.abc import Iterator

from tests.simulation.actions import ActionKind, SimulatedAction
from tests.simulation.users import register_profile
from tests.simulation.users.base import UserProfile


@register_profile
class ActiveProfile(UserProfile):
    name = "Active"

    def actions(self) -> Iterator[SimulatedAction]:
        yield SimulatedAction(ActionKind.START, delay_before=0.0)
        for _ in range(self._rng.randint(5, 20)):
            idle = self._rng.uniform(180.0, 420.0)  # ~5 min think-time
            yield SimulatedAction(ActionKind.SEND_URL, delay_before=idle, url=self._pick_url())
            yield SimulatedAction(ActionKind.CLICK_FORMAT, delay_before=self._rng.uniform(1, 4))
            yield SimulatedAction(
                ActionKind.CLICK_QUALITY,
                delay_before=self._rng.uniform(1, 4),
                is_download=True,
            )
