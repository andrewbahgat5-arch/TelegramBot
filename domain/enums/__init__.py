"""Domain enumerations (MASTER_PLAN 9.4).

Strongly-typed enumerations shared across layers. Each is a ``StrEnum`` so its
members serialize directly to their persisted string form.
"""

from __future__ import annotations

from domain.enums.ad_audience import AudienceDimension, AudienceEffect, AudienceMode
from domain.enums.ad_event import AdEventType
from domain.enums.ad_placement import AdDeliveryMode, AdPlacement
from domain.enums.ad_type import AdType
from domain.enums.cookie_health import (
    NOTIFY_HEALTH,
    RECOVERABLE_HEALTH,
    SELECTABLE_HEALTH,
    CookieHealth,
)
from domain.enums.error_type import ErrorType
from domain.enums.job_status import JobStatus
from domain.enums.media_format import MediaFormat
from domain.enums.quality import Quality
from domain.enums.subscription import SubscriptionSource, SubscriptionStatus
from domain.enums.user_role import UNLIMITED_ROLES, UserRole

__all__ = [
    "NOTIFY_HEALTH",
    "RECOVERABLE_HEALTH",
    "SELECTABLE_HEALTH",
    "UNLIMITED_ROLES",
    "AdDeliveryMode",
    "AdEventType",
    "AdPlacement",
    "AdType",
    "AudienceDimension",
    "AudienceEffect",
    "AudienceMode",
    "CookieHealth",
    "ErrorType",
    "JobStatus",
    "MediaFormat",
    "Quality",
    "SubscriptionSource",
    "SubscriptionStatus",
    "UserRole",
]
