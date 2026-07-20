"""DownloaderRegistry (MASTER_PLAN 12.6.3, Task 5.2, LOCKED behavior).

The registry is the single ``DownloaderProtocol`` the service layer sees: it detects
the platform, selects candidate providers (enabled + supports-platform + healthy),
tries them in ``priority DESC, name ASC`` order, fails over on retryable errors, and
tracks per-provider health (in-memory mirror + Redis, D-028). No service ever names
a provider (D-029).

Health for candidate filtering is read from the in-memory mirror; the periodic
``refresh_health`` task (worker process) calls each provider's ``health_check`` to
refresh it. A retryable request failure bumps the provider's error streak and, once
it crosses ``provider_failure_threshold``, marks it DEGRADED for
``provider_cooldown_seconds``.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import orjson
import redis.asyncio as aioredis

from core.logging import get_logger
from core.redis_keys import RedisKeys
from core.urls import detect_platform
from domain.entities.media import DownloadedFile, MediaInfo
from domain.enums import MediaFormat, Quality
from domain.exceptions import InfrastructureError, URLNotSupportedError
from domain.protocols.downloader import (
    Capability,
    DownloaderProtocol,
    DownloadProgress,
    ProviderHealth,
    ProviderRetryElsewhere,
    ProviderSettingsProtocol,
    ProviderUnsupported,
)

_log = get_logger("infrastructure.downloader.registry")

T = TypeVar("T")


@dataclass
class _HealthState:
    status: ProviderHealth = ProviderHealth.OK
    error_streak: int = 0
    degraded_until: float = 0.0
    last_check_ts: float = 0.0
    last_error: str | None = None


class DownloaderRegistry:
    """Provider selection + failover + health tracking (a ``DownloaderProtocol``)."""

    def __init__(
        self,
        settings: ProviderSettingsProtocol,
        *,
        redis: aioredis.Redis | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        # Facade attributes so services may depend on ``DownloaderProtocol`` directly.
        self.name = "__registry__"
        self.supported_platforms = {"*"}
        self.capabilities: set[Capability] = set()
        self.priority = 0
        self._settings = settings
        self._redis = redis
        self._now = now
        self._providers: list[DownloaderProtocol] = []
        self._health: dict[str, _HealthState] = {}

    # --- registration -----------------------------------------------------
    def register(self, provider: DownloaderProtocol) -> None:
        self._providers.append(provider)
        self._health.setdefault(provider.name, _HealthState())

    def health_of(self, name: str) -> ProviderHealth:
        state = self._health.get(name)
        return state.status if state else ProviderHealth.OK

    # --- DownloaderProtocol surface ---------------------------------------
    async def extract_info(self, url: str, *, item_index: int | None = None) -> MediaInfo:
        return await self._run(
            detect_platform(url), lambda p: p.extract_info(url, item_index=item_index)
        )

    async def download(
        self,
        media: MediaInfo,
        format_: MediaFormat,
        quality: Quality,
        dest: Path,
        *,
        progress_cb: DownloadProgress | None = None,
    ) -> DownloadedFile:
        return await self._run(
            media.platform,
            lambda p: p.download(media, format_, quality, dest, progress_cb=progress_cb),
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth.OK

    # --- core selection + failover ----------------------------------------
    async def _run(self, platform: str, op: Callable[[DownloaderProtocol], Awaitable[T]]) -> T:
        candidates = await self._candidates(platform)
        if not candidates:
            raise URLNotSupportedError("No download provider can handle this URL.")

        failover = await self._settings.failover_enabled()
        first_error: Exception | None = None
        notes: list[str] = []

        for provider in candidates:
            try:
                result = await op(provider)
            except ProviderUnsupported as exc:  # opt-out: try next, no penalty
                first_error = first_error or exc
                notes.append(f"{provider.name}: unsupported")
                continue
            except (ProviderRetryElsewhere, InfrastructureError) as exc:  # transient
                await self._on_retryable_failure(provider, exc)
                first_error = first_error or exc
                notes.append(f"{provider.name}: {type(exc).__name__}")
                if not failover:
                    raise
                continue
            else:
                await self._on_success(provider)
                return result

        # Every candidate failed. Surface the first error with the others attached.
        # (first_error is always set here: the loop ran at least once and every
        # non-returning branch records it; the None-guard satisfies the type checker.)
        if first_error is None:  # pragma: no cover - unreachable given candidates exist
            raise URLNotSupportedError("No download provider could handle this URL.")
        first_error.__notes__ = notes
        raise first_error

    async def _candidates(self, platform: str) -> list[DownloaderProtocol]:
        enabled = await self._settings.providers_enabled()
        overrides = await self._settings.priority_overrides()
        usable = [
            p
            for p in self._providers
            if enabled.get(p.name, False)
            and ("*" in p.supported_platforms or platform in p.supported_platforms)
            and self._is_usable(p.name)
        ]
        usable.sort(key=lambda p: (-overrides.get(p.name, p.priority), p.name))
        return usable

    def _is_usable(self, name: str) -> bool:
        state = self._health.get(name)
        if state is None or state.status is ProviderHealth.OK:
            return True
        if state.status is ProviderHealth.UNAVAILABLE:
            return False
        # DEGRADED: skip until the cooldown elapses, then give it another chance.
        return self._now() >= state.degraded_until

    # --- health tracking --------------------------------------------------
    async def _on_success(self, provider: DownloaderProtocol) -> None:
        state = self._health.setdefault(provider.name, _HealthState())
        if state.status is not ProviderHealth.OK or state.error_streak:
            self._transition(provider.name, ProviderHealth.OK)
            state.error_streak = 0
            state.degraded_until = 0.0
            state.last_error = None
            await self._persist(provider.name)

    async def _on_retryable_failure(self, provider: DownloaderProtocol, exc: Exception) -> None:
        threshold = await self._settings.failure_threshold()
        cooldown = await self._settings.cooldown_seconds()
        state = self._health.setdefault(provider.name, _HealthState())
        state.error_streak += 1
        state.last_error = str(exc)
        state.last_check_ts = self._now()
        if state.error_streak >= threshold:
            self._transition(provider.name, ProviderHealth.DEGRADED)
            state.degraded_until = self._now() + cooldown
        await self._persist(provider.name)

    async def refresh_health(self) -> None:
        """Periodic refresh: probe every provider's ``health_check`` (Section 12.6.4)."""
        for provider in self._providers:
            try:
                health = await provider.health_check()
            except Exception as exc:  # a crashing health check ⇒ unavailable
                health = ProviderHealth.UNAVAILABLE
                _log.warning("provider_health_check_failed", provider=provider.name, error=str(exc))
            state = self._health.setdefault(provider.name, _HealthState())
            state.last_check_ts = self._now()
            if health is ProviderHealth.OK:
                state.error_streak = 0
                state.degraded_until = 0.0
            self._transition(provider.name, health)
            await self._persist(provider.name)

    def _transition(self, name: str, new: ProviderHealth) -> None:
        state = self._health[name]
        if state.status is not new:
            _log.info("provider_health_changed", provider=name, **{"from": state.status, "to": new})
        state.status = new

    async def _persist(self, name: str) -> None:
        if self._redis is None:
            return
        state = self._health[name]
        payload = orjson.dumps(
            {
                "status": state.status.value,
                "last_check_ts": state.last_check_ts,
                "error_streak": state.error_streak,
                "last_error": state.last_error,
            }
        )
        await self._redis.set(RedisKeys.provider_health(name), payload)
