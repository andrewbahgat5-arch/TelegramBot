"""Telegram E2E test harness (MASTER_PLAN Task 11.2, §25.7, D-038).

Wraps the @BotFather sandbox bot client and a fixed pool of test accounts, with
deterministic inter-action delays. The live transport is Phase B: it is only
exercised when running against the provisioned sandbox + isolated test infra
(`DEPLOY_ENV=test` and the `E2E_LIVE=1` opt-in). Until then every E2E test skips
cleanly via :func:`skip_if_sandbox_unavailable`, so the suite stays green while the
scenarios are versioned and reviewed now.

The opt-in switch ``E2E_LIVE`` is a test-only environment toggle (read directly,
not part of the LOCKED §13.2 Settings) so a normal run can never accidentally make
live Telegram calls.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass

import pytest

from core.config import Settings

E2E_LIVE_ENV = "E2E_LIVE"


def sandbox_ready(settings: Settings) -> bool:
    """True only when the sandbox + test infra are provisioned and opted in."""
    return settings.is_test_env and os.environ.get(E2E_LIVE_ENV) == "1"


def skip_if_sandbox_unavailable(settings: Settings) -> None:
    """Skip the calling test unless the live sandbox is ready (Phase B)."""
    if not sandbox_ready(settings):
        pytest.skip(
            "E2E sandbox not available: set DEPLOY_ENV=test + E2E_LIVE=1 against the "
            "provisioned @BotFather sandbox bot and isolated test infra (Phase B)."
        )


@dataclass(frozen=True, slots=True)
class SandboxAccount:
    """One fixed test account from the pool (D-038)."""

    account_id: int
    label: str


class AccountPool:
    """A fixed pool of test accounts, acquired/released round-robin."""

    def __init__(self, accounts: list[SandboxAccount]) -> None:
        if not accounts:
            raise ValueError("test account pool must be non-empty")
        self._accounts = accounts
        self._cursor = 0

    def __len__(self) -> int:
        return len(self._accounts)

    def acquire(self) -> SandboxAccount:
        account = self._accounts[self._cursor % len(self._accounts)]
        self._cursor += 1
        return account


class DeterministicDelays:
    """Seeded, realistic inter-action delays (so live runs are reproducible)."""

    def __init__(self, seed: int = 0, low: float = 0.2, high: float = 1.5) -> None:
        self._rng = random.Random(seed)  # noqa: S311 - timing jitter, not crypto
        self._low = low
        self._high = high

    def next(self) -> float:
        return self._rng.uniform(self._low, self._high)


class E2EHarness:
    """Sandbox-bot client wrapper (live transport implemented in Phase B).

    Construction is cheap and side-effect free; :meth:`connect` (which opens the
    real sandbox session) is Phase B. E2E tests skip before reaching it.
    """

    def __init__(self, settings: Settings, pool: AccountPool) -> None:
        self._settings = settings
        self._pool = pool
        self._delays = DeterministicDelays()

    @property
    def pool(self) -> AccountPool:
        return self._pool

    async def connect(self) -> None:  # pragma: no cover - Phase B (requires live infra)
        raise NotImplementedError(
            "E2EHarness.connect requires the provisioned sandbox bot + test infra "
            "(Sprint 11 Phase B)."
        )

    async def aclose(self) -> None:  # pragma: no cover - Phase B
        return None
