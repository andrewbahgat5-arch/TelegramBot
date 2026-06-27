"""E2E fixtures (MASTER_PLAN §25.5, §25.7).

Every E2E test depends on ``harness``; when the live sandbox is not available the
fixture skips the test (Phase B gating). This keeps the E2E scenarios collected,
versioned, and reviewed without making live Telegram calls in ordinary runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import Settings
from tests.e2e.harness import (
    AccountPool,
    E2EHarness,
    SandboxAccount,
    skip_if_sandbox_unavailable,
)

ENV_EXAMPLE = str(Path(__file__).resolve().parents[2] / ".env.example")


@pytest.fixture
def e2e_settings() -> Settings:
    return Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]


@pytest.fixture
def test_account_pool() -> AccountPool:
    return AccountPool(
        [SandboxAccount(account_id=i, label=f"test-account-{i}") for i in range(1, 4)]
    )


@pytest.fixture
def harness(e2e_settings: Settings, test_account_pool: AccountPool) -> E2EHarness:
    skip_if_sandbox_unavailable(e2e_settings)  # Phase B gate
    return E2EHarness(e2e_settings, test_account_pool)
