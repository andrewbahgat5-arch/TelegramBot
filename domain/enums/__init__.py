"""Domain enumerations (MASTER_PLAN 9.4).

Strongly-typed enumerations shared across layers. Each is a ``StrEnum`` so its
members serialize directly to their persisted string form.
"""

from __future__ import annotations

from domain.enums.ad_audience import AudienceDimension, AudienceEffect, AudienceMode
from domain.enums.ad_placement import AdDeliveryMode, AdPlacement
from domain.enums.ad_type import AdType
from domain.enums.error_type import ErrorType
from domain.enums.job_status import JobStatus
from domain.enums.media_format import MediaFormat
from domain.enums.quality import Quality
from domain.enums.user_role import UNLIMITED_ROLES, UserRole

__all__ = [
    "UNLIMITED_ROLES",
    "AdDeliveryMode",
    "AdPlacement",
    "AdType",
    "AudienceDimension",
    "AudienceEffect",
    "AudienceMode",
    "ErrorType",
    "JobStatus",
    "MediaFormat",
    "Quality",
    "UserRole",
]
