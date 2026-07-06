"""Reward domain entity (D-075) — an immutable view of a ``rewards`` row.

Framework-free (Section 8): built from an ORM row by attribute access only, so
``domain`` keeps its leaf position. A reward is *active* when it has not expired;
a null ``expires_at`` is permanent (e.g. the referral daily-download bonus, D-066).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from domain.rewards import RewardType


@dataclass(frozen=True, slots=True)
class Reward:
    """Immutable snapshot of a granted reward."""

    id: int
    user_id: int
    reward_type: RewardType
    value: int
    param: str | None
    source: str
    granted_at: datetime.datetime
    expires_at: datetime.datetime | None = None

    def is_active(self, now: datetime.datetime) -> bool:
        """True when the reward has not expired (null expiry = permanent)."""
        return self.expires_at is None or self.expires_at > now

    @classmethod
    def from_row(cls, row: Any) -> Reward:
        """Build from a ``rewards`` ORM row (attribute access only)."""
        return cls(
            id=row.id,
            user_id=row.user_id,
            reward_type=RewardType(row.reward_type),
            value=row.value,
            param=row.param,
            source=row.source,
            granted_at=row.granted_at,
            expires_at=row.expires_at,
        )
