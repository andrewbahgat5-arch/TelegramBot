"""Unit tests for the V2 feature-flag mechanism (VERSION_2_MASTER_PLAN §5.8)."""

from __future__ import annotations

from services.feature_flag_service import FeatureFlag, FeatureFlagService
from services.settings_service import SettingsService
from tests.unit._fakes import FakeCache, FakeSettingsStore


def _service(seed: dict[str, tuple[str, str]] | None = None) -> FeatureFlagService:
    store = FakeSettingsStore(seed or {})
    settings = SettingsService(store, FakeCache())
    return FeatureFlagService(settings)


async def test_missing_flag_reads_as_off() -> None:
    # No seed row at all: the app is safe to run before the seed migration lands.
    service = _service()
    assert await service.is_enabled(FeatureFlag.SUBSCRIPTIONS) is False


async def test_seeded_flag_off_reads_false() -> None:
    service = _service({FeatureFlag.MULTILINK.value: ("false", "bool")})
    assert await service.is_enabled(FeatureFlag.MULTILINK) is False


async def test_seeded_flag_on_reads_true() -> None:
    service = _service({FeatureFlag.AD_ANALYTICS.value: ("true", "bool")})
    assert await service.is_enabled(FeatureFlag.AD_ANALYTICS) is True


async def test_set_enabled_toggles_and_takes_effect() -> None:
    # Row must pre-exist (settings set is LOCKED); seed it off, then toggle on.
    service = _service({FeatureFlag.EXPIRY_NOTIFICATIONS.value: ("false", "bool")})
    assert await service.is_enabled(FeatureFlag.EXPIRY_NOTIFICATIONS) is False

    await service.set_enabled(FeatureFlag.EXPIRY_NOTIFICATIONS, True, updated_by=42)
    assert await service.is_enabled(FeatureFlag.EXPIRY_NOTIFICATIONS) is True

    await service.set_enabled(FeatureFlag.EXPIRY_NOTIFICATIONS, False, updated_by=42)
    assert await service.is_enabled(FeatureFlag.EXPIRY_NOTIFICATIONS) is False


async def test_every_flag_has_a_distinct_settings_key() -> None:
    keys = [flag.value for flag in FeatureFlag]
    assert len(keys) == len(set(keys))
    assert all(key.endswith("_enabled") for key in keys)
