"""Telegram Bot User Simulator transports (MASTER_PLAN §25.15.2).

``BotClient`` is the transport seam. ``StubBotClient`` is a deterministic in-memory
implementation for dry-runs and CI: it performs NO network I/O and models the
bot's core abuse defenses (per-user message-rate ceiling, per-user daily-download
cap, rapid-fire download rejection) so the Abuse profile is provably blocked
without a live bot. The live ``SandboxBotClient`` that drives the real @BotFather
sandbox bot is Phase B (it depends on the Task 11.1 sandbox provisioning).
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from tests.simulation.actions import ActionKind, ActionResult, SimulatedAction

# A download whose think-time is below this (seconds) is treated as rapid-fire abuse.
RAPID_FIRE_THRESHOLD_S = 1.0


class BotClient(ABC):
    """Abstract transport that performs a simulated action against the bot."""

    @abstractmethod
    async def perform(self, user_id: int, action: SimulatedAction) -> ActionResult:
        """Perform one action and report its outcome."""

    async def aclose(self) -> None:  # pragma: no cover - default no-op
        """Release any resources. Live transports override this."""
        return None


class StubBotClient(BotClient):
    """Deterministic, network-free transport modeling the bot's abuse defenses."""

    def __init__(
        self,
        *,
        rng: random.Random,
        messages_per_minute: int = 30,
        daily_limit: int = 10,
        base_latency_s: float = 0.02,
        jitter_s: float = 0.05,
    ) -> None:
        self._rng = rng
        self._mpm = messages_per_minute
        self._daily_limit = daily_limit
        self._base = base_latency_s
        self._jitter = jitter_s
        self._messages: dict[int, int] = {}
        self._downloads: dict[int, int] = {}

    async def perform(self, user_id: int, action: SimulatedAction) -> ActionResult:
        latency = self._base + self._rng.random() * self._jitter
        messages = self._messages.get(user_id, 0) + 1
        self._messages[user_id] = messages
        over_rate = messages > self._mpm

        if action.is_download:
            downloads = self._downloads.get(user_id, 0) + 1
            self._downloads[user_id] = downloads
            rapid = action.delay_before < RAPID_FIRE_THRESHOLD_S
            over_daily = downloads > self._daily_limit
            if over_rate or rapid or over_daily:
                reason = "rate_limited" if over_rate else ("rapid_fire" if rapid else "daily_limit")
                return ActionResult(action.kind, False, True, latency, error=reason)
            return ActionResult(action.kind, True, False, latency)

        if over_rate:
            return ActionResult(action.kind, False, True, latency, error="rate_limited")
        return ActionResult(action.kind, True, False, latency)


class SandboxBotClient(BotClient):  # pragma: no cover - Phase B, requires live infra
    """Live transport against the @BotFather sandbox bot (Phase B).

    Deferred until the sandbox bot + isolated test infra are provisioned (Task 11.1
    Phase B). Instantiation fails loudly so a misconfigured run cannot silently
    pretend to be live.
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "SandboxBotClient requires the provisioned sandbox bot + test infra "
            "(Sprint 11 Phase B); use StubBotClient for dry-runs."
        )

    async def perform(self, user_id: int, action: SimulatedAction) -> ActionResult:
        raise NotImplementedError


# Re-exported for callers that branch on kind without importing actions directly.
__all__ = ["ActionKind", "BotClient", "SandboxBotClient", "StubBotClient"]
