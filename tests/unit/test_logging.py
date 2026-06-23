"""Unit tests for core/logging.py (MASTER_PLAN Task 1.2, 14.3, 15.1, 15.2)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from core.constants import REDACTED
from core.logging import (
    SensitiveScrubber,
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
    correlation_context,
    get_logger,
)


def _emit_json(capsys: pytest.CaptureFixture[str], **fields: Any) -> dict[str, Any]:
    configure_logging("INFO", "json")
    get_logger("test.logger").info("an_event", **fields)
    out = capsys.readouterr().out.strip().splitlines()[-1]
    parsed: dict[str, Any] = json.loads(out)
    return parsed


def test_scrubber_redacts_secret_keys() -> None:
    scrubber = SensitiveScrubber()
    event = {
        "password": "hunter2",
        "bot_token": "12345:abcdef",
        "safe": "value",
        "nested": {"api_key": "k", "ok": "v"},
    }
    result = scrubber(None, "info", event)
    assert result["password"] == REDACTED
    assert result["bot_token"] == REDACTED
    assert result["safe"] == "value"
    assert result["nested"]["api_key"] == REDACTED
    assert result["nested"]["ok"] == "v"


def test_json_output_has_standard_fields(capsys: pytest.CaptureFixture[str]) -> None:
    record = _emit_json(capsys, user_id=42)
    assert record["event"] == "an_event"
    assert record["level"] == "info"
    assert record["logger"] == "test.logger"
    assert record["user_id"] == 42
    assert "timestamp" in record


def test_json_output_redacts_secret_field(capsys: pytest.CaptureFixture[str]) -> None:
    record = _emit_json(capsys, token="super-secret-token")
    assert record["token"] == REDACTED
    assert "super-secret-token" not in json.dumps(record)


def test_correlation_context_binds_and_unbinds(
    capsys: pytest.CaptureFixture[str],
) -> None:
    clear_correlation_id()
    with correlation_context("corr-123"):
        inside = _emit_json(capsys)
    after = _emit_json(capsys)
    assert inside["correlation_id"] == "corr-123"
    assert "correlation_id" not in after


def test_bind_and_clear_correlation_id(capsys: pytest.CaptureFixture[str]) -> None:
    bind_correlation_id("abc")
    bound = _emit_json(capsys)
    assert bound["correlation_id"] == "abc"
    clear_correlation_id()
    cleared = _emit_json(capsys)
    assert "correlation_id" not in cleared
