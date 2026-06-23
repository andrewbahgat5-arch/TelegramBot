"""Unit tests for core/sentry.py (MASTER_PLAN Task 1.3, 15.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import sentry_sdk
from sentry_sdk.integrations import Integration

from core.config import Settings
from core.constants import REDACTED
from core.sentry import _available_integrations, _before_send, init_sentry

ENV_EXAMPLE = str(Path(__file__).resolve().parents[2] / ".env.example")


def _settings() -> Settings:
    return Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]


def test_init_is_noop_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
    assert init_sentry(_settings()) is False
    assert calls == []


def test_init_called_with_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
    dsn = "https://abc@o0.ingest.sentry.io/1"
    monkeypatch.setenv("SENTRY_DSN", dsn)
    assert init_sentry(_settings()) is True
    assert len(calls) == 1
    assert calls[0]["dsn"] == dsn
    assert calls[0]["before_send"] is _before_send
    assert calls[0]["send_default_pii"] is False


def test_before_send_scrubs_secrets() -> None:
    event: Any = {
        "message": "ok",
        "extra": {"token": "abc", "user": "u"},
        "tags": [{"password": "p"}],
    }
    result: Any = _before_send(event, {})
    assert result is not None
    assert result["extra"]["token"] == REDACTED
    assert result["extra"]["user"] == "u"
    assert result["tags"][0]["password"] == REDACTED
    assert result["message"] == "ok"


def test_available_integrations_returns_integration_instances() -> None:
    integrations = _available_integrations()
    # At minimum the asyncio integration is importable in any environment.
    assert len(integrations) >= 1
    assert all(isinstance(i, Integration) for i in integrations)
