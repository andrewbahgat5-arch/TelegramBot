"""ORM models (MASTER_PLAN 10, Task 2.5). One class per table."""

from __future__ import annotations

from infrastructure.database.models.active_download import ActiveDownload
from infrastructure.database.models.ad_audience_rule import AdAudienceRule
from infrastructure.database.models.ad_button import AdButton
from infrastructure.database.models.ad_event import AdEvent
from infrastructure.database.models.ad_placement import AdPlacementLink
from infrastructure.database.models.advertisement import Advertisement
from infrastructure.database.models.audience_expression import AudienceExpression, AudienceRule
from infrastructure.database.models.audience_segment import AudienceSegment, AudienceSegmentMember
from infrastructure.database.models.base import Base
from infrastructure.database.models.broadcast import Broadcast
from infrastructure.database.models.cached_file import CachedFile
from infrastructure.database.models.download import Download
from infrastructure.database.models.error_log import ErrorLog
from infrastructure.database.models.job import Job
from infrastructure.database.models.job_waiter import JobWaiter
from infrastructure.database.models.media_metadata import MediaMetadata
from infrastructure.database.models.message_template import MessageTemplate
from infrastructure.database.models.referral import Referral
from infrastructure.database.models.reward import Reward
from infrastructure.database.models.setting import Setting
from infrastructure.database.models.user import User
from infrastructure.database.models.user_preference import UserPreference
from infrastructure.database.models.youtube_cookie import YoutubeCookie, YoutubeCookieEvent

__all__ = [
    "ActiveDownload",
    "AdAudienceRule",
    "AdButton",
    "AdEvent",
    "AdPlacementLink",
    "Advertisement",
    "AudienceExpression",
    "AudienceRule",
    "AudienceSegment",
    "AudienceSegmentMember",
    "Base",
    "Broadcast",
    "CachedFile",
    "Download",
    "ErrorLog",
    "Job",
    "JobWaiter",
    "MediaMetadata",
    "MessageTemplate",
    "Referral",
    "Reward",
    "Setting",
    "User",
    "UserPreference",
    "YoutubeCookie",
    "YoutubeCookieEvent",
]
