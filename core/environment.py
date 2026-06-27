"""Environment safety rules (MASTER_PLAN Task 11.1, D-060, D-032).

A small, extensible registry of startup safety checks. Each rule inspects the
fully-parsed ``Settings`` and returns a human-readable violation message (or
``None`` when satisfied). The ``Settings`` model-validator runs every rule at
construction time, so any process that builds ``Settings`` (bot, worker, api, the
simulation runner, the e2e harness) is protected identically and future entry
points inherit the checks for free.

Adding a new safety guarantee is a single registry append — the startup
architecture does not change (Owner directive, Sprint 11). The first rule
realizes D-032: a test deployment must never run against the production bot. The
mechanism is deliberately generic so later rules (test must not use a production
database / Redis / storage bucket / webhook URL, etc.) drop in the same way.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.security import token_fingerprint

if TYPE_CHECKING:
    from core.config import Settings


class EnvironmentMisconfiguredError(Exception):
    """Raised at startup when one or more environment safety rules are violated.

    Carries every violation message so an operator sees all problems at once.
    Deliberately *not* a ``ValueError`` subclass: pydantic wraps only
    ``ValueError``/``AssertionError`` raised inside validators, so a plain
    exception propagates out of ``Settings()`` unchanged — the process refuses to
    boot with a clear, typed, catchable error rather than a generic
    ``ValidationError`` (D-060).
    """

    def __init__(self, violations: list[str]) -> None:
        self.violations = list(violations)
        super().__init__("Environment safety check failed: " + "; ".join(self.violations))


@dataclass(frozen=True)
class EnvironmentSafetyRule:
    """One startup safety check.

    ``check`` returns a violation message when the rule is broken, or ``None``
    when it is satisfied (including when the rule does not apply to the current
    environment).
    """

    name: str
    check: Callable[[Settings], str | None]


def _test_env_not_production_bot(settings: Settings) -> str | None:
    """A ``DEPLOY_ENV=test`` deployment must never use the production bot (D-032).

    Compares the configured ``BOT_TOKEN``'s fingerprint against the operator-
    supplied ``PROD_BOT_TOKEN_FINGERPRINT``. The check is a no-op outside the test
    environment and when no production fingerprint is configured.
    """
    if settings.deploy_env != "test":
        return None
    expected = settings.prod_bot_token_fingerprint.strip()
    if not expected:
        return None
    if token_fingerprint(settings.bot_token.get_secret_value()) == expected:
        return (
            "DEPLOY_ENV=test but BOT_TOKEN matches the configured production bot "
            "fingerprint (PROD_BOT_TOKEN_FINGERPRINT); refusing to boot a test "
            "deployment against the production bot."
        )
    return None


# The registry. Append new rules here; nothing else in the startup path changes.
ENVIRONMENT_SAFETY_RULES: tuple[EnvironmentSafetyRule, ...] = (
    EnvironmentSafetyRule(
        name="test_env_not_production_bot",
        check=_test_env_not_production_bot,
    ),
)


def evaluate_environment_safety(settings: Settings) -> list[str]:
    """Run every registered safety rule; return all violation messages.

    An empty list means the environment is safe to boot.
    """
    violations: list[str] = []
    for rule in ENVIRONMENT_SAFETY_RULES:
        message = rule.check(settings)
        if message is not None:
            violations.append(message)
    return violations
