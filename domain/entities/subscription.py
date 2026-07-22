"""Subscription domain entity (VERSION_2_MASTER_PLAN §5.1, §6.2).

Immutable, framework-free view of a ``subscriptions`` row. :meth:`is_active_at`
encodes the lazy-expiry rule (V2-D-007): an ``active`` row whose ``expires_at`` has
passed resolves as Free, exactly as ``_effective_plan()`` does today — correctness
never depends on a scheduler tick.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from domain.enums import SubscriptionSource, SubscriptionStatus


@dataclass(frozen=True, slots=True)
class Subscription:
    """Immutable snapshot of a ``subscriptions`` row."""

    id: UUID
    user_id: int
    plan_id: int
    status: SubscriptionStatus
    source: SubscriptionSource
    starts_at: datetime.datetime
    expires_at: datetime.datetime
    notified_milestones: int = 0
    granted_by: int | None = None

    @classmethod
    def from_row(cls, row: Any) -> Subscription:
        """Build from a ``subscriptions`` ORM row (attribute access only)."""
        return cls(
            id=row.id if isinstance(row.id, UUID) else UUID(str(row.id)),
            user_id=row.user_id,
            plan_id=row.plan_id,
            status=SubscriptionStatus(row.status),
            source=SubscriptionSource(row.source),
            starts_at=row.starts_at,
            expires_at=row.expires_at,
            notified_milestones=row.notified_milestones,
            granted_by=row.granted_by,
        )

    def is_active_at(self, now: datetime.datetime) -> bool:
        """True when this row grants entitlements at ``now`` (status active + unexpired)."""
        return self.status is SubscriptionStatus.ACTIVE and self.expires_at > now
