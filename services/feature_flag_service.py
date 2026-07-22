"""Feature-flag mechanism (VERSION_2_MASTER_PLAN §5.8, V2-D-031).

Every major V2 feature ships behind an individually toggleable flag for staged
rollout and deploy-free rollback. The mechanism is deliberately zero-infrastructure:
each flag is a ``bool`` row in the existing ``settings`` table, read through the
existing cached :class:`SettingsService`, so a toggle takes effect within the
settings-cache TTL without a redeploy.

Design rules carried from the plan:

* **Off by default.** A missing row reads as ``False`` — every flag's off-state is a
  defined, tested behavior, and the code is safe to run before the seed migration.
* **Entry-point gating.** Callers check a flag once at a feature's boundary, never
  scatter the check across branches.
* **Audited toggles.** :meth:`set_enabled` records who changed which flag from what to
  what (structured log + the ``settings.updated_by`` actor column).
* **Removal, not accretion.** Each flag is deleted the release after its feature is
  declared stable (plan §5.8); this registry is where that retirement happens.
"""

from __future__ import annotations

from enum import StrEnum

from core.logging import get_logger
from services.settings_service import SettingNotFoundError, SettingsService

_log = get_logger("services.feature_flags")


class FeatureFlag(StrEnum):
    """The V2 feature flags (§5.8). Value = the ``settings`` key that backs the flag."""

    SUBSCRIPTIONS = "feature_subscriptions_enabled"
    MULTILINK = "feature_multilink_enabled"
    PREMIUM_QUALITY_GATING = "feature_premium_quality_gating_enabled"
    AD_ANALYTICS = "feature_ad_analytics_enabled"
    EXPIRY_NOTIFICATIONS = "feature_expiry_notifications_enabled"
    ANALYZER_RAW_METADATA = "analyzer_raw_metadata_enabled"


class FeatureFlagService:
    """Cached reads and audited writes for the V2 feature flags."""

    def __init__(self, settings: SettingsService) -> None:
        self._settings = settings

    async def is_enabled(self, flag: FeatureFlag) -> bool:
        """Whether ``flag`` is on. A missing row reads as off (defined off-state)."""
        try:
            return bool(await self._settings.get(flag.value))
        except SettingNotFoundError:
            return False

    async def set_enabled(self, flag: FeatureFlag, enabled: bool, *, updated_by: int) -> None:
        """Toggle ``flag`` and audit the change (who, which flag, old -> new).

        Persists through :meth:`SettingsService.set_validated`, which requires the row
        to already exist (the settings set is LOCKED, §13.4) — the seed migration
        creates every flag row, so a toggle can never invent a key.
        """
        old = await self.is_enabled(flag)
        await self._settings.set_validated(
            flag.value, "true" if enabled else "false", updated_by=updated_by
        )
        _log.info(
            "feature_flag_changed",
            flag=flag.value,
            old=old,
            new=enabled,
            updated_by=updated_by,
        )
