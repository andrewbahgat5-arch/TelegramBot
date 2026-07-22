"""Shadow-mode entitlement parity check (VERSION_2_MASTER_PLAN §15 Step 1-2, V2-D-024).

In V2.1 the entitlement resolver runs in *shadow*: it computes each user's plan the new
way (from their active subscription) and compares it to the legacy ``is_premium`` path.
Any disagreement increments ``entitlement_parity_mismatch_total{field}`` and logs — the
metric is the **cutover gate**: it must read 0 over the soak window before V2.2 flips
``feature_subscriptions_enabled`` (V2-D-024).

Parity is compared at **plan level**: if the resolver picks the same plan as
``_effective_plan()``, every derived entitlement matches by construction (they are seeded
from the same settings). Comparing plan codes is unambiguous and captures the whole
surface. The check is read-only and, at its call site, fully defensive — it must never
affect the snapshot it rides alongside.
"""

from __future__ import annotations

import datetime

from core import metrics
from core.logging import get_logger
from domain.entities.subscription import Subscription
from infrastructure.database.repositories.subscription import SubscriptionRepository
from services.entitlement_service import EntitlementService

_log = get_logger("services.entitlement_shadow")


def legacy_plan_code(
    *, is_premium: bool, premium_expires_at: datetime.datetime | None, now: datetime.datetime
) -> str:
    """The plan the V1 path resolves — mirrors ``rate_limit_service._effective_plan``."""
    if is_premium and premium_expires_at is not None and premium_expires_at > now:
        return "premium"
    return "free"


class ShadowParity:
    """Compares the resolver's plan to the legacy path for one user (read-only)."""

    def __init__(
        self,
        entitlements: EntitlementService,
        subscriptions: SubscriptionRepository,
    ) -> None:
        self._entitlements = entitlements
        self._subs = subscriptions

    async def check(
        self,
        *,
        user_id: int,
        is_premium: bool,
        premium_expires_at: datetime.datetime | None,
        now: datetime.datetime | None = None,
    ) -> None:
        """Resolve both ways and record a mismatch. Never raises to the caller."""
        now = now or datetime.datetime.now(datetime.UTC)
        legacy = legacy_plan_code(
            is_premium=is_premium, premium_expires_at=premium_expires_at, now=now
        )
        active_row = await self._subs.get_active_for_user(user_id)
        active = Subscription.from_row(active_row) if active_row is not None else None
        resolved = self._entitlements.resolve(active, now=now).plan_code
        if resolved != legacy:
            metrics.record_entitlement_parity_mismatch("plan_code")
            _log.warning(
                "entitlement_parity_mismatch",
                user_id=user_id,
                field="plan_code",
                legacy=legacy,
                resolved=resolved,
            )
