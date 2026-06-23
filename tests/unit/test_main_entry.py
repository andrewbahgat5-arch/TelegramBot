"""Unit test for the core smoke entry point (MASTER_PLAN Task 1.8)."""

from __future__ import annotations

import json

import pytest

from core.__main__ import main


def test_main_emits_one_structured_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    main()
    lines = [line for line in capsys.readouterr().out.strip().splitlines() if line]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "logging_smoke_ok"
    assert record["component"] == "core"
    # main() binds a fresh UUIDv7 correlation id.
    assert "correlation_id" in record
