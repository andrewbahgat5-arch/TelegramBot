"""Unit tests for AdEventRecorder (MASTER_PLAN Task 9.5.9, D-052).

The recorder is fire-and-forget: ``record_*`` schedules a background ``ad_events`` write
on its own session and returns immediately, so the analytics write is off the delivery
hot path. These tests drive it with a fake session factory (no DB) and verify the write
content, the deferral (nothing written until the loop runs the task), and that failures
(or no running loop) are swallowed.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from infrastructure.database.ad_event_recorder import AdEventRecorder

pytestmark = pytest.mark.asyncio


class _FakeSession:
    def __init__(self, sink: list[Any], *, fail: bool = False) -> None:
        self._sink = sink
        self._fail = fail
        self.committed = False

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    def add(self, obj: Any) -> None:
        self._sink.append(obj)

    async def flush(self) -> None:
        if self._fail:
            raise RuntimeError("db down")

    async def commit(self) -> None:
        self.committed = True


def _factory(sink: list[Any], *, fail: bool = False) -> Any:
    def make() -> _FakeSession:
        return _FakeSession(sink, fail=fail)

    return make


async def test_record_impression_writes_event_off_path() -> None:
    sink: list[Any] = []
    recorder = AdEventRecorder(_factory(sink))

    recorder.record_impression(advertisement_id=7, user_id=42, placement="post_download")
    assert sink == []  # deferred: returns before the background write runs

    await recorder.aclose()
    assert len(sink) == 1
    event = sink[0]
    assert event.advertisement_id == 7
    assert event.user_id == 42
    assert event.event_type == "impression"
    assert event.placement == "post_download"
    assert event.button_id is None


async def test_record_click_writes_event() -> None:
    sink: list[Any] = []
    recorder = AdEventRecorder(_factory(sink))

    recorder.record_click(advertisement_id=3, user_id=None, button_id=9)
    await recorder.aclose()

    event = sink[0]
    assert event.event_type == "click"
    assert event.button_id == 9
    assert event.user_id is None
    assert event.placement is None


async def test_write_failure_is_swallowed() -> None:
    recorder = AdEventRecorder(_factory([], fail=True))
    recorder.record_impression(advertisement_id=1, user_id=1, placement=None)
    await recorder.aclose()  # the background write raised; aclose must not propagate it


async def test_no_running_loop_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = AdEventRecorder(_factory([]))

    def _no_loop(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("no running event loop")

    monkeypatch.setattr("infrastructure.database.ad_event_recorder.asyncio.create_task", _no_loop)
    # Must not raise even when a task cannot be scheduled (analytics is best-effort).
    recorder.record_click(advertisement_id=1, user_id=1, button_id=None)
    await asyncio.sleep(0)
