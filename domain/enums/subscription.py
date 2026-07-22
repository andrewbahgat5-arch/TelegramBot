"""Subscription enums (VERSION_2_MASTER_PLAN §6.2, V2-D-001/003/006).

Stored as ``VARCHAR`` columns (the codebase convention — no PG ``ENUM`` types; the
``StrEnum`` is the single source of valid values, enforced app-side). V2.1 only ever
writes ``active``/``expired``/``canceled`` and ``manual_grant``; the remaining values
are reserved for V4/V5 payment + promo flows (V2-D-006) and ship now so adding a
provider later is a new subscription *source*, never a schema change.
"""

from __future__ import annotations

from enum import StrEnum


class SubscriptionStatus(StrEnum):
    """Lifecycle state of a subscription row (``subscriptions.status``)."""

    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELED = "canceled"
    PENDING = "pending"  # reserved for async payment flows (V4)


class SubscriptionSource(StrEnum):
    """Where a subscription came from (``subscriptions.source``)."""

    MANUAL_GRANT = "manual_grant"  # the only V2 source
    STARS = "stars"  # reserved (V4)
    STRIPE = "stripe"  # reserved (V4)
    PAYMOB = "paymob"  # reserved (V4)
    PROMO = "promo"  # reserved (V5 referrals)
