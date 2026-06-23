"""Sentry initialization (MASTER_PLAN Task 1.3, Section 15.5).

Sentry is a no-op unless ``SENTRY_DSN`` is configured. Integrations are added only
for libraries actually installed, so this module imports cleanly in early sprints
before Aiogram/FastAPI/SQLAlchemy land. ``before_send`` scrubs secret-looking keys
from every outgoing event so tokens and passwords never reach the Sentry backend.
"""

from __future__ import annotations

from typing import Any

import sentry_sdk
from sentry_sdk.integrations import Integration
from sentry_sdk.types import Event, Hint

from core.config import Settings
from core.constants import REDACTED, SECRET_KEY_SUBSTRINGS

# Integration import paths to try, in the order listed in Section 15.5. Each is
# added only if its import succeeds (the underlying library is installed).
_OPTIONAL_INTEGRATIONS: tuple[tuple[str, str], ...] = (
    ("sentry_sdk.integrations.asyncio", "AsyncioIntegration"),
    ("sentry_sdk.integrations.fastapi", "FastApiIntegration"),
    ("sentry_sdk.integrations.sqlalchemy", "SqlalchemyIntegration"),
    ("sentry_sdk.integrations.redis", "RedisIntegration"),
)


def init_sentry(settings: Settings) -> bool:
    """Initialize Sentry if a DSN is set. Returns whether it was initialized."""
    if not settings.sentry_enabled:
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=_available_integrations(),
        before_send=_before_send,
        send_default_pii=False,
    )
    return True


def _available_integrations() -> list[Integration]:
    integrations: list[Integration] = []
    for module_path, class_name in _OPTIONAL_INTEGRATIONS:
        try:
            module = __import__(module_path, fromlist=[class_name])
            integration_cls = getattr(module, class_name)
        except Exception:  # noqa: S112  # nosec B112: missing optional library must not break init
            continue
        integrations.append(integration_cls())
    return integrations


def _before_send(event: Event, _hint: Hint) -> Event | None:
    """Redact secret-looking keys anywhere in the event payload (Section 15.5)."""
    _scrub(event)
    return event


def _scrub(value: Any) -> None:
    if isinstance(value, dict):
        for key, inner in list(value.items()):
            if isinstance(key, str) and _is_secret(key):
                value[key] = REDACTED
            else:
                _scrub(inner)
    elif isinstance(value, list):
        for item in value:
            _scrub(item)


def _is_secret(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in SECRET_KEY_SUBSTRINGS)
