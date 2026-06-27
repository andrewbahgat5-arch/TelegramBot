"""Abuse user profile (MASTER_PLAN §25.15.1).

Rapid-fire requests, queue-flood attempts, and rate-limit-bypass attempts. This
profile **must always be detected and blocked** — an abuse user achieving any
successful download is a failing test (§25.15.1, validation in 11.10/M-22).
"""

from __future__ import annotations

from collections.abc import Iterator

from tests.simulation.actions import ActionKind, SimulatedAction
from tests.simulation.users import register_profile
from tests.simulation.users.base import UserProfile

# Far beyond any per-user ceiling, with zero think-time (rapid-fire).
_FLOOD_SIZE = 60


@register_profile
class AbuseProfile(UserProfile):
    name = "Abuse"

    def actions(self) -> Iterator[SimulatedAction]:
        yield SimulatedAction(ActionKind.START, delay_before=0.0)
        # Queue flood: a burst of download attempts with no spacing.
        for _ in range(_FLOOD_SIZE):
            yield SimulatedAction(ActionKind.SEND_URL, delay_before=0.0, url=self._pick_url())
            yield SimulatedAction(
                ActionKind.CLICK_QUALITY,
                delay_before=0.0,
                is_download=True,
                label="flood",
            )
        # Rate-limit-bypass attempt: vary the callback payload, same user.
        for _ in range(_FLOOD_SIZE):
            yield SimulatedAction(ActionKind.CLICK_RESEND, delay_before=0.0, is_download=True)
