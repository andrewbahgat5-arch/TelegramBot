"""Unit-level tests for the E2E harness helpers (MASTER_PLAN Task 11.2).

These exercise the harness scaffolding itself (no live bot), so they run in every
suite. The live flow scenarios live in the sibling flow/scenario packages and skip
until Phase B.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import Settings
from tests.e2e.harness import (
    AccountPool,
    DeterministicDelays,
    SandboxAccount,
    sandbox_ready,
)

ENV_EXAMPLE = str(Path(__file__).resolve().parents[2] / ".env.example")


def _settings() -> Settings:
    return Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]


def test_sandbox_not_ready_in_development() -> None:
    assert sandbox_ready(_settings()) is False


def test_sandbox_requires_both_test_env_and_optin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2E_LIVE", "1")
    # Still development → not ready (the env gate alone is insufficient).
    assert sandbox_ready(_settings()) is False
    monkeypatch.setenv("DEPLOY_ENV", "test")
    assert sandbox_ready(_settings()) is True
    monkeypatch.delenv("E2E_LIVE", raising=False)
    assert sandbox_ready(_settings()) is False


def test_account_pool_round_robin() -> None:
    pool = AccountPool([SandboxAccount(1, "a"), SandboxAccount(2, "b")])
    assert len(pool) == 2
    ids = [pool.acquire().account_id for _ in range(5)]
    assert ids == [1, 2, 1, 2, 1]


def test_empty_pool_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        AccountPool([])


def test_delays_are_deterministic_and_bounded() -> None:
    a = [DeterministicDelays(seed=7).next() for _ in range(5)]
    b = [DeterministicDelays(seed=7).next() for _ in range(5)]
    assert a == b
    assert all(0.2 <= d <= 1.5 for d in a)
