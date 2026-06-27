"""Unit tests for core/environment.py (MASTER_PLAN Task 11.1, D-060, D-032).

These exercise the safety-rule *mechanism* with lightweight stand-ins; the
end-to-end refuse-to-boot behavior against a real ``Settings`` lives in
``tests/security/test_environment_isolation.py``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from core.config import Settings
from core.environment import (
    ENVIRONMENT_SAFETY_RULES,
    EnvironmentMisconfiguredError,
    EnvironmentSafetyRule,
    evaluate_environment_safety,
)
from core.security import token_fingerprint


def _fake_settings(*, deploy_env: str, bot_token: str, fingerprint: str) -> Settings:
    """A minimal stand-in carrying only the attributes the rules read."""
    fake = SimpleNamespace(
        deploy_env=deploy_env,
        prod_bot_token_fingerprint=fingerprint,
        bot_token=SimpleNamespace(get_secret_value=lambda: bot_token),
    )
    return cast("Settings", fake)


def test_registry_contains_the_production_bot_rule() -> None:
    names = {rule.name for rule in ENVIRONMENT_SAFETY_RULES}
    assert "test_env_not_production_bot" in names


def test_safe_when_not_test_env() -> None:
    settings = _fake_settings(
        deploy_env="production",
        bot_token="prod-token",
        fingerprint=token_fingerprint("prod-token"),
    )
    assert evaluate_environment_safety(settings) == []


def test_safe_when_no_fingerprint_configured() -> None:
    settings = _fake_settings(deploy_env="test", bot_token="any-token", fingerprint="")
    assert evaluate_environment_safety(settings) == []


def test_safe_when_test_token_differs_from_production() -> None:
    settings = _fake_settings(
        deploy_env="test",
        bot_token="sandbox-token",
        fingerprint=token_fingerprint("prod-token"),
    )
    assert evaluate_environment_safety(settings) == []


def test_violation_when_test_uses_production_token() -> None:
    settings = _fake_settings(
        deploy_env="test",
        bot_token="prod-token",
        fingerprint=token_fingerprint("prod-token"),
    )
    violations = evaluate_environment_safety(settings)
    assert len(violations) == 1
    assert "production bot" in violations[0]


def test_error_carries_all_violations() -> None:
    error = EnvironmentMisconfiguredError(["rule-a failed", "rule-b failed"])
    assert error.violations == ["rule-a failed", "rule-b failed"]
    assert "rule-a failed" in str(error)
    assert "rule-b failed" in str(error)


def test_evaluate_aggregates_multiple_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    rules = (
        EnvironmentSafetyRule(name="always_fails_1", check=lambda _s: "first"),
        EnvironmentSafetyRule(name="passes", check=lambda _s: None),
        EnvironmentSafetyRule(name="always_fails_2", check=lambda _s: "second"),
    )
    monkeypatch.setattr("core.environment.ENVIRONMENT_SAFETY_RULES", rules)
    settings = _fake_settings(deploy_env="development", bot_token="x", fingerprint="")
    assert evaluate_environment_safety(settings) == ["first", "second"]
