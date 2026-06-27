"""Casual user profile (MASTER_PLAN §25.15.1).

1-3 downloads/day, small files, long idle (5-30 min) between actions.
"""

from __future__ import annotations

from collections.abc import Iterator

from tests.simulation.actions import ActionKind, SimulatedAction
from tests.simulation.users import register_profile
from tests.simulation.users.base import UserProfile


@register_profile
class CasualProfile(UserProfile):
    name = "Casual"

    def actions(self) -> Iterator[SimulatedAction]:
        yield SimulatedAction(ActionKind.START, delay_before=0.0)
        for _ in range(self._rng.randint(1, 3)):
            idle = self._rng.uniform(300.0, 1800.0)  # 5-30 min think-time
            yield SimulatedAction(ActionKind.SEND_URL, delay_before=idle, url=self._pick_url())
            yield SimulatedAction(ActionKind.CLICK_FORMAT, delay_before=self._rng.uniform(2, 6))
            yield SimulatedAction(
                ActionKind.CLICK_QUALITY,
                delay_before=self._rng.uniform(2, 6),
                is_download=True,
                label="small",
            )
