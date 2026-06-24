"""Unit tests for SettingsService admin write-path validation (MASTER_PLAN Task 8.2)."""

from __future__ import annotations

import pytest

from services.settings_service import (
    InvalidSettingValueError,
    SettingNotFoundError,
    SettingsService,
)
from tests.unit._fakes import FakeCache, FakeSettingsStore

_DATA = {
    "free_daily_limit": ("10", "int"),
    "ads_enabled": ("true", "bool"),
    "providers_enabled": ('{"ytdlp": true}', "json"),
    "sentry_traces_sample_rate": ("0.1", "float"),
}


def _service() -> SettingsService:
    return SettingsService(FakeSettingsStore(dict(_DATA)), FakeCache(), cache_ttl=60)


async def test_list_all_returns_every_key_sorted() -> None:
    views = await _service().list_all()
    keys = [v.key for v in views]
    assert keys == sorted(keys)
    assert {"free_daily_limit", "ads_enabled", "providers_enabled"} <= set(keys)


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("free_daily_limit", "25", 25),
        ("ads_enabled", "false", False),
        ("ads_enabled", "on", True),
        ("providers_enabled", '{"ytdlp": false}', {"ytdlp": False}),
        ("sentry_traces_sample_rate", "0.5", 0.5),
    ],
)
async def test_set_validated_accepts_and_casts(key: str, value: str, expected: object) -> None:
    service = _service()
    assert await service.set_validated(key, value) == expected
    assert await service.get(key) == expected  # persisted + re-read


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("free_daily_limit", "not-an-int"),
        ("ads_enabled", "maybe"),
        ("providers_enabled", "{not json"),
        ("sentry_traces_sample_rate", "high"),
    ],
)
async def test_set_validated_rejects_bad_input(key: str, value: str) -> None:
    with pytest.raises(InvalidSettingValueError):
        await _service().set_validated(key, value)


async def test_set_validated_rejects_unknown_key() -> None:
    with pytest.raises(SettingNotFoundError):
        await _service().set_validated("not_a_real_key", "1")
