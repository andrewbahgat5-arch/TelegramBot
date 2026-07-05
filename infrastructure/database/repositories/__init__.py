"""Repository implementations (MASTER_PLAN Task 2.7)."""

from __future__ import annotations

from infrastructure.database.repositories.active_download import ActiveDownloadRepository
from infrastructure.database.repositories.ad_audience_rule import AdAudienceRuleRepository
from infrastructure.database.repositories.ad_button import AdButtonRepository
from infrastructure.database.repositories.ad_event import AdEventRepository
from infrastructure.database.repositories.advertisement import AdRepository
from infrastructure.database.repositories.audience_expression import AudienceExpressionRepository
from infrastructure.database.repositories.audience_segment import (
    AudienceSegmentMemberRepository,
    AudienceSegmentRepository,
)
from infrastructure.database.repositories.broadcast import BroadcastRepository
from infrastructure.database.repositories.cached_file import CachedFileRepository
from infrastructure.database.repositories.download import DownloadRepository
from infrastructure.database.repositories.error_log import ErrorLogRepository
from infrastructure.database.repositories.job import JobRepository
from infrastructure.database.repositories.job_waiter import JobWaiterRepository
from infrastructure.database.repositories.media import MediaRepository
from infrastructure.database.repositories.message_template import MessageTemplateRepository
from infrastructure.database.repositories.referral import ReferralRepository
from infrastructure.database.repositories.setting import SettingsRepository
from infrastructure.database.repositories.user import UserRepository
from infrastructure.database.repositories.user_preference import UserPreferenceRepository

__all__ = [
    "ActiveDownloadRepository",
    "AdAudienceRuleRepository",
    "AdButtonRepository",
    "AdEventRepository",
    "AdRepository",
    "AudienceExpressionRepository",
    "AudienceSegmentMemberRepository",
    "AudienceSegmentRepository",
    "BroadcastRepository",
    "CachedFileRepository",
    "DownloadRepository",
    "ErrorLogRepository",
    "JobRepository",
    "JobWaiterRepository",
    "MediaRepository",
    "MessageTemplateRepository",
    "ReferralRepository",
    "SettingsRepository",
    "UserPreferenceRepository",
    "UserRepository",
]
