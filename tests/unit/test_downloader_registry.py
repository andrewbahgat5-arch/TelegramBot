"""Unit tests for DownloaderRegistry (MASTER_PLAN 12.6.3, Task 5.2)."""

from __future__ import annotations

from typing import Any, cast

import pytest

from core.redis_keys import RedisKeys
from domain.exceptions import ExtractionFailedError, URLNotSupportedError
from domain.protocols.downloader import (
    ProviderHealth,
    ProviderRetryElsewhere,
    ProviderUnsupported,
)
from infrastructure.downloader.registry import DownloaderRegistry
from tests.unit._fakes import FakeProvider, FakeProviderSettings

_URL = "https://example.org/clip"


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _registry(settings: FakeProviderSettings, *, clock: _Clock | None = None) -> DownloaderRegistry:
    return DownloaderRegistry(settings, redis=None, now=clock or _Clock())


async def test_no_candidates_raises() -> None:
    reg = _registry(FakeProviderSettings(enabled={"ytdlp": False}))
    reg.register(FakeProvider("ytdlp"))
    with pytest.raises(URLNotSupportedError):
        await reg.extract_info(_URL)


async def test_highest_priority_tried_first() -> None:
    high = FakeProvider("high", priority=100)
    low = FakeProvider("low", priority=10)
    reg = _registry(FakeProviderSettings(enabled={"high": True, "low": True}))
    reg.register(low)
    reg.register(high)
    await reg.extract_info(_URL)
    assert high.calls == 1 and low.calls == 0


async def test_unsupported_advances_without_degrading() -> None:
    a = FakeProvider("a", priority=100, error=ProviderUnsupported())
    b = FakeProvider("b", priority=50)
    reg = _registry(FakeProviderSettings(enabled={"a": True, "b": True}))
    reg.register(a)
    reg.register(b)
    await reg.extract_info(_URL)
    assert b.calls == 1
    assert reg.health_of("a") is ProviderHealth.OK  # opt-out is not a failure


async def test_retryable_fails_over_and_degrades() -> None:
    a = FakeProvider("a", priority=100, error=ProviderRetryElsewhere())
    b = FakeProvider("b", priority=50)
    reg = _registry(FakeProviderSettings(enabled={"a": True, "b": True}, threshold=1))
    reg.register(a)
    reg.register(b)
    await reg.extract_info(_URL)
    assert b.calls == 1
    assert reg.health_of("a") is ProviderHealth.DEGRADED


async def test_content_error_stops_failover() -> None:
    a = FakeProvider("a", priority=100, error=ExtractionFailedError("gone"))
    b = FakeProvider("b", priority=50)
    reg = _registry(FakeProviderSettings(enabled={"a": True, "b": True}))
    reg.register(a)
    reg.register(b)
    with pytest.raises(ExtractionFailedError):
        await reg.extract_info(_URL)
    assert b.calls == 0  # content failure → do not try other providers


async def test_failover_disabled_single_attempt() -> None:
    a = FakeProvider("a", priority=100, error=ProviderRetryElsewhere())
    b = FakeProvider("b", priority=50)
    reg = _registry(
        FakeProviderSettings(enabled={"a": True, "b": True}, failover=False, threshold=1)
    )
    reg.register(a)
    reg.register(b)
    with pytest.raises(ProviderRetryElsewhere):
        await reg.extract_info(_URL)
    assert b.calls == 0


async def test_degraded_provider_skipped_until_cooldown_elapses() -> None:
    clock = _Clock()
    a = FakeProvider("a", priority=100, error=ProviderRetryElsewhere())
    b = FakeProvider("b", priority=50)
    reg = _registry(
        FakeProviderSettings(enabled={"a": True, "b": True}, threshold=1, cooldown=60),
        clock=clock,
    )
    reg.register(a)
    reg.register(b)

    await reg.extract_info(_URL)  # a fails → DEGRADED until t+60
    a.calls = 0
    clock.t += 10  # still within cooldown
    await reg.extract_info(_URL)
    assert a.calls == 0  # skipped

    clock.t += 60  # cooldown elapsed
    a._error = None  # now healthy again
    await reg.extract_info(_URL)
    assert a.calls == 1  # retried


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    async def set(self, key: str, value: bytes) -> None:
        self.store[key] = value


async def test_health_persisted_to_redis_on_failure() -> None:
    redis = _FakeRedis()
    a = FakeProvider("a", priority=100, error=ProviderRetryElsewhere())
    b = FakeProvider("b", priority=50)
    reg = DownloaderRegistry(
        FakeProviderSettings(enabled={"a": True, "b": True}, threshold=1),
        redis=cast(Any, redis),
    )
    reg.register(a)
    reg.register(b)
    await reg.extract_info(_URL)
    assert RedisKeys.provider_health("a") in redis.store


async def test_refresh_health_marks_unavailable_excluded() -> None:
    a = FakeProvider("a", priority=100, health=ProviderHealth.UNAVAILABLE)
    b = FakeProvider("b", priority=50)
    reg = _registry(FakeProviderSettings(enabled={"a": True, "b": True}))
    reg.register(a)
    reg.register(b)
    await reg.refresh_health()
    assert reg.health_of("a") is ProviderHealth.UNAVAILABLE
    await reg.extract_info(_URL)
    assert a.calls == 0 and b.calls == 1
