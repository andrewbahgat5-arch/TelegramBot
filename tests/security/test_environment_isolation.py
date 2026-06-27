"""Security: test-environment isolation (MASTER_PLAN §25.9.4, §25.6, D-032/D-060).

The production-fingerprint boot assertion must refuse to start a ``DEPLOY_ENV=test``
deployment that is pointed at the production bot, and must stay out of the way in
every other configuration. This is the first occupant of the ``tests/security/``
collection root (§25.2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import Settings
from core.environment import EnvironmentMisconfiguredError
from core.security import token_fingerprint

ENV_EXAMPLE = str(Path(__file__).resolve().parents[2] / ".env.example")
# The BOT_TOKEN placeholder shipped in .env.example.
EXAMPLE_BOT_TOKEN = "bot-token-test-XXXX"


def _settings() -> Settings:
    return Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]


def test_test_env_against_production_token_refuses_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The running BOT_TOKEN (from .env.example) is declared as the production token.
    monkeypatch.setenv("DEPLOY_ENV", "test")
    monkeypatch.setenv("PROD_BOT_TOKEN_FINGERPRINT", token_fingerprint(EXAMPLE_BOT_TOKEN))
    with pytest.raises(EnvironmentMisconfiguredError) as excinfo:
        _settings()
    assert any("production bot" in v for v in excinfo.value.violations)


def test_test_env_with_sandbox_token_boots(monkeypatch: pytest.MonkeyPatch) -> None:
    # A test deployment whose BOT_TOKEN differs from production boots normally.
    monkeypatch.setenv("DEPLOY_ENV", "test")
    monkeypatch.setenv(
        "PROD_BOT_TOKEN_FINGERPRINT", token_fingerprint("a-different-production-token")
    )
    settings = _settings()
    assert settings.is_test_env is True


def test_production_env_ignores_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    # The guard only applies to the test environment, never to production itself.
    monkeypatch.setenv("DEPLOY_ENV", "production")
    monkeypatch.setenv("PROD_BOT_TOKEN_FINGERPRINT", token_fingerprint(EXAMPLE_BOT_TOKEN))
    settings = _settings()
    assert settings.is_production is True


def test_test_env_without_fingerprint_boots(monkeypatch: pytest.MonkeyPatch) -> None:
    # No configured production fingerprint → the check is a no-op.
    monkeypatch.setenv("DEPLOY_ENV", "test")
    monkeypatch.delenv("PROD_BOT_TOKEN_FINGERPRINT", raising=False)
    settings = _settings()
    assert settings.is_test_env is True
