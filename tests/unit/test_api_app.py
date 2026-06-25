"""Unit tests for the FastAPI app (MASTER_PLAN Task 10.2 / 10.4, Section 20.2).

The app is driven directly over ASGI (no httpx/TestClient dependency): a minimal
in-process client sends an HTTP scope and collects the response messages.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from api.app import create_app
from api.readiness import ReadinessChecker
from core import metrics

pytestmark = pytest.mark.asyncio


async def _get(app: Any, path: str) -> tuple[int, dict[str, str], bytes]:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "server": ("test", 80),
        "client": ("test", 12345),
    }
    code = 0
    raw_headers: list[tuple[bytes, bytes]] = []
    chunks: list[bytes] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        nonlocal code, raw_headers
        if message["type"] == "http.response.start":
            code = message["status"]
            raw_headers = message["headers"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    headers = {k.decode(): v.decode() for k, v in raw_headers}
    return code, headers, b"".join(chunks)


async def _ok() -> None:
    return None


def _count(value: int) -> Any:
    async def probe() -> int:
        return value

    return probe


def _ready_checker() -> ReadinessChecker:
    return ReadinessChecker(
        db_ping=_ok, redis_ping=_ok, queue_depth=_count(1), active_workers=_count(1)
    )


def _unready_checker() -> ReadinessChecker:
    return ReadinessChecker(
        db_ping=_ok, redis_ping=_ok, queue_depth=_count(0), active_workers=_count(0)
    )


async def _noop_refresh() -> None:
    return None


async def test_health_is_ok() -> None:
    app = create_app(checker=_ready_checker(), refresh_metrics=_noop_refresh)
    code, _headers, body = await _get(app, "/v1/health")
    assert code == 200
    assert json.loads(body) == {"status": "ok"}


async def test_ready_returns_200_when_all_pass() -> None:
    app = create_app(checker=_ready_checker(), refresh_metrics=_noop_refresh)
    code, _headers, body = await _get(app, "/v1/ready")
    assert code == 200
    payload = json.loads(body)
    assert payload["ready"] is True
    assert payload["checks"]["database"]["ok"] is True


async def test_ready_returns_503_when_a_check_fails() -> None:
    app = create_app(checker=_unready_checker(), refresh_metrics=_noop_refresh)
    code, _headers, body = await _get(app, "/v1/ready")
    assert code == 503
    assert json.loads(body)["ready"] is False


async def test_metrics_endpoint_renders_exposition_and_refreshes() -> None:
    refreshed: list[bool] = []

    async def refresh() -> None:
        metrics.set_live_gauges(
            queue_depth_value=4,
            active_workers_value=1,
            db_pool_in_use_value=0,
            redis_connected_value=True,
        )
        refreshed.append(True)

    app = create_app(checker=_ready_checker(), refresh_metrics=refresh)
    code, headers, body = await _get(app, "/v1/metrics")
    assert code == 200
    assert headers["content-type"].startswith("text/plain")
    assert refreshed == [True]
    assert b"queue_depth 4.0" in body
