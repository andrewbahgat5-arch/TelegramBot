"""Unit tests for the HTTP admin API (MASTER_PLAN Task 8.3, Section 20.2 / 20.3, D-051).

The app is driven directly over ASGI (no httpx/TestClient dependency): a minimal
in-process client sends an HTTP scope + body and collects the response. Routes are
exercised against **real** services (UserService, SettingsService, QueueService,
AdminService) wired to the in-memory fakes, so the delegation path is covered end to
end. Auth, the 404-when-disabled behavior, and the per-endpoint contracts are checked.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, cast

import pytest

from api.app import create_app
from api.readiness import ReadinessChecker
from api.routes.admin import create_admin_router
from services.admin_service import AdminService
from services.queue_service import QueueService
from services.settings_service import SettingsService
from services.user_service import UserService
from tests.unit._fakes import (
    FakeCache,
    FakeQueueBackend,
    FakeSettingsStore,
    FakeUser,
    FakeUserRepo,
    make_cache_service,
)

pytestmark = pytest.mark.asyncio

_KEY = "s3cret-admin-key"


# --- In-process ASGI client -----------------------------------------------------------


async def _request(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, bytes]:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": raw_headers,
        "server": ("test", 80),
        "client": ("test", 12345),
    }
    code = 0
    chunks: list[bytes] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        nonlocal code
        if message["type"] == "http.response.start":
            code = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    return code, b"".join(chunks)


# --- Fakes specific to the admin reads ------------------------------------------------


class _FakeJobRow:
    def __init__(self, **kw: Any) -> None:
        self.id = kw["id"]
        self.user_id = kw.get("user_id", 1)
        self.media_id = kw.get("media_id", 10)
        self.format = kw.get("format", "mp4")
        self.quality = kw.get("quality", "720p")
        self.status = kw.get("status", "queued")
        self.priority = kw.get("priority", 1000)
        self.retry_count = kw.get("retry_count", 0)
        self.error_message = kw.get("error_message")
        self.created_at = kw.get("created_at", datetime.datetime(2026, 6, 25, tzinfo=datetime.UTC))
        self.started_at = kw.get("started_at")
        self.finished_at = kw.get("finished_at")


class _FakeJobReadRepo:
    def __init__(self, rows: list[_FakeJobRow]) -> None:
        self._rows = rows

    async def list_recent(
        self, *, limit: int = 50, offset: int = 0, status: str | None = None
    ) -> list[_FakeJobRow]:
        rows = [r for r in self._rows if status is None or r.status == status]
        return rows[offset : offset + limit]


class _FakeErrorRow:
    def __init__(self, **kw: Any) -> None:
        self.id = kw["id"]
        self.user_id = kw.get("user_id")
        self.job_id = kw.get("job_id")
        self.correlation_id = kw.get("correlation_id")
        self.error_type = kw.get("error_type", "download_failed")
        self.message = kw.get("message", "boom")
        self.created_at = kw.get("created_at", datetime.datetime(2026, 6, 25, tzinfo=datetime.UTC))


class _FakeErrorReadRepo:
    def __init__(self, rows: list[_FakeErrorRow]) -> None:
        self._rows = rows

    async def list_recent(
        self, *, limit: int = 50, offset: int = 0, error_type: str | None = None
    ) -> list[_FakeErrorRow]:
        rows = [r for r in self._rows if error_type is None or r.error_type == error_type]
        return rows[offset : offset + limit]


class _FakeSession:
    """An async-context-manager session whose commit/rollback are no-ops."""

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _session_factory() -> _FakeSession:
    return _FakeSession()


# --- App assembly ---------------------------------------------------------------------


async def _ok() -> None:
    return None


def _count(value: int) -> Any:
    async def probe() -> int:
        return value

    return probe


def _checker() -> ReadinessChecker:
    return ReadinessChecker(
        db_ping=_ok, redis_ping=_ok, queue_depth=_count(1), active_workers=_count(1)
    )


async def _noop_refresh() -> None:
    return None


_SETTINGS = {"free_daily_limit": ("10", "int"), "ads_enabled": ("true", "bool")}


def _build_app(
    *,
    users: FakeUserRepo | None = None,
    jobs: list[_FakeJobRow] | None = None,
    errors: list[_FakeErrorRow] | None = None,
    settings_data: dict[str, tuple[str, str]] | None = None,
    queue: FakeQueueBackend | None = None,
    mounted: bool = True,
) -> Any:
    users = users if users is not None else FakeUserRepo()
    queue_service = QueueService(queue if queue is not None else FakeQueueBackend())
    cache, _ = make_cache_service()
    store = FakeSettingsStore(settings_data if settings_data is not None else dict(_SETTINGS))
    job_repo = _FakeJobReadRepo(jobs or [])
    error_repo = _FakeErrorReadRepo(errors or [])

    def make_user_service(_session: Any) -> UserService:
        return UserService(users, cache, owner_telegram_id=999)

    def make_settings_service(_session: Any) -> SettingsService:
        return SettingsService(store, FakeCache(), cache_ttl=60)

    def make_admin_service(_session: Any) -> AdminService:
        return AdminService(job_repo=job_repo, error_repo=error_repo)

    router = None
    if mounted:
        router = create_admin_router(
            api_key=_KEY,
            session_factory=cast(Any, _session_factory),
            user_service_factory=make_user_service,
            settings_service_factory=make_settings_service,
            admin_service_factory=make_admin_service,
            queue_service=queue_service,
        )
    return create_app(checker=_checker(), refresh_metrics=_noop_refresh, admin_router=router)


def _auth() -> dict[str, str]:
    return {"X-API-Key": _KEY}


# --- Auth + mount gating --------------------------------------------------------------


async def test_admin_paths_404_when_router_not_mounted() -> None:
    app = _build_app(mounted=False)
    code, _ = await _request(app, "GET", "/v1/admin/stats", headers=_auth())
    assert code == 404  # surface does not exist when ADMIN_API_KEY is unset


async def test_missing_key_returns_401() -> None:
    app = _build_app()
    code, _ = await _request(app, "GET", "/v1/admin/stats")
    assert code == 401


async def test_wrong_key_returns_401() -> None:
    app = _build_app()
    code, _ = await _request(app, "GET", "/v1/admin/stats", headers={"X-API-Key": "nope"})
    assert code == 401


async def test_public_endpoints_need_no_key() -> None:
    app = _build_app()
    code, body = await _request(app, "GET", "/v1/health")
    assert code == 200
    assert json.loads(body) == {"status": "ok"}


# --- /stats + /queue ------------------------------------------------------------------


async def test_stats_reports_totals_and_queue() -> None:
    users = FakeUserRepo()
    users.by_tid[1] = FakeUser(id=1, telegram_id=1, total_downloads=5)
    users.by_tid[2] = FakeUser(id=2, telegram_id=2, total_downloads=3, is_banned=True)
    queue = FakeQueueBackend()
    await queue.enqueue("j1", score=1.0)
    app = _build_app(users=users, queue=queue)

    code, body = await _request(app, "GET", "/v1/admin/stats", headers=_auth())
    payload = json.loads(body)
    assert code == 200
    assert payload["total_users"] == 2
    assert payload["banned_users"] == 1
    assert payload["total_downloads"] == 8
    assert payload["queue_depth"] == 1


async def test_queue_summary() -> None:
    queue = FakeQueueBackend()
    await queue.enqueue("a", score=1.0)
    await queue.enqueue("b", score=2.0)
    app = _build_app(queue=queue)

    code, body = await _request(app, "GET", "/v1/admin/queue", headers=_auth())
    assert code == 200
    assert json.loads(body)["depth"] == 2


# --- /users ---------------------------------------------------------------------------


async def test_list_users_returns_page() -> None:
    users = FakeUserRepo()
    users.by_tid[1] = FakeUser(id=1, telegram_id=1, username="a")
    users.by_tid[2] = FakeUser(id=2, telegram_id=2, username="b")
    app = _build_app(users=users)

    code, body = await _request(app, "GET", "/v1/admin/users", headers=_auth())
    payload = json.loads(body)
    assert code == 200
    assert {u["telegram_id"] for u in payload} == {1, 2}


async def test_users_search_by_telegram_id() -> None:
    users = FakeUserRepo()
    users.by_tid[55] = FakeUser(id=9, telegram_id=55, first_name="Sam")
    app = _build_app(users=users)

    code, body = await _request(
        app, "GET", "/v1/admin/users", query="telegram_id=55", headers=_auth()
    )
    payload = json.loads(body)
    assert code == 200
    assert len(payload) == 1 and payload[0]["telegram_id"] == 55

    code, body = await _request(
        app, "GET", "/v1/admin/users", query="telegram_id=999", headers=_auth()
    )
    assert code == 200 and json.loads(body) == []


async def test_user_detail_and_404() -> None:
    users = FakeUserRepo()
    users.by_tid[7] = FakeUser(id=3, telegram_id=7, first_name="Kim")
    app = _build_app(users=users)

    code, body = await _request(app, "GET", "/v1/admin/users/7", headers=_auth())
    assert code == 200 and json.loads(body)["first_name"] == "Kim"

    code, _ = await _request(app, "GET", "/v1/admin/users/404", headers=_auth())
    assert code == 404


async def test_ban_and_unban_with_audit() -> None:
    users = FakeUserRepo()
    users.by_tid[7] = FakeUser(id=3, telegram_id=7)
    app = _build_app(users=users)

    code, body = await _request(
        app,
        "POST",
        "/v1/admin/users/7/ban",
        headers={**_auth(), "content-type": "application/json"},
        body=json.dumps({"reason": "spam"}).encode(),
    )
    assert code == 200 and json.loads(body)["is_banned"] is True
    assert users.by_tid[7].ban_reason == "spam"

    code, body = await _request(app, "POST", "/v1/admin/users/7/unban", headers=_auth())
    assert code == 200 and json.loads(body)["is_banned"] is False


async def test_ban_without_body_is_allowed() -> None:
    users = FakeUserRepo()
    users.by_tid[7] = FakeUser(id=3, telegram_id=7)
    app = _build_app(users=users)
    code, body = await _request(app, "POST", "/v1/admin/users/7/ban", headers=_auth())
    assert code == 200 and json.loads(body)["is_banned"] is True


async def test_ban_unknown_user_404() -> None:
    app = _build_app()
    code, _ = await _request(app, "POST", "/v1/admin/users/123/ban", headers=_auth())
    assert code == 404


# --- /jobs + /errors ------------------------------------------------------------------


async def test_list_jobs_and_status_filter() -> None:
    jobs = [
        _FakeJobRow(id="j1", status="completed"),
        _FakeJobRow(id="j2", status="failed", error_message="x"),
    ]
    app = _build_app(jobs=jobs)

    code, body = await _request(app, "GET", "/v1/admin/jobs", headers=_auth())
    assert code == 200 and len(json.loads(body)) == 2

    code, body = await _request(
        app, "GET", "/v1/admin/jobs", query="status=failed", headers=_auth()
    )
    payload = json.loads(body)
    assert code == 200 and len(payload) == 1 and payload[0]["id"] == "j2"


async def test_browse_errors_and_type_filter() -> None:
    errors = [
        _FakeErrorRow(id=1, error_type="download_failed", message="a"),
        _FakeErrorRow(id=2, error_type="provider_error", message="b"),
    ]
    app = _build_app(errors=errors)

    code, body = await _request(app, "GET", "/v1/admin/errors", headers=_auth())
    assert code == 200 and len(json.loads(body)) == 2

    code, body = await _request(
        app, "GET", "/v1/admin/errors", query="error_type=provider_error", headers=_auth()
    )
    payload = json.loads(body)
    assert code == 200 and len(payload) == 1 and payload[0]["id"] == 2


# --- /settings ------------------------------------------------------------------------


async def test_list_settings() -> None:
    app = _build_app()
    code, body = await _request(app, "GET", "/v1/admin/settings", headers=_auth())
    payload = json.loads(body)
    assert code == 200
    keys = {row["key"] for row in payload}
    assert {"free_daily_limit", "ads_enabled"} <= keys


async def test_update_setting_ok() -> None:
    app = _build_app()
    code, body = await _request(
        app,
        "PUT",
        "/v1/admin/settings/free_daily_limit",
        headers={**_auth(), "content-type": "application/json"},
        body=json.dumps({"value": "25"}).encode(),
    )
    payload = json.loads(body)
    assert code == 200
    assert payload["key"] == "free_daily_limit" and payload["value"] == "25"


async def test_update_unknown_setting_404() -> None:
    app = _build_app()
    code, _ = await _request(
        app,
        "PUT",
        "/v1/admin/settings/not_a_key",
        headers={**_auth(), "content-type": "application/json"},
        body=json.dumps({"value": "1"}).encode(),
    )
    assert code == 404


async def test_update_setting_invalid_value_400() -> None:
    app = _build_app()
    code, _ = await _request(
        app,
        "PUT",
        "/v1/admin/settings/free_daily_limit",
        headers={**_auth(), "content-type": "application/json"},
        body=json.dumps({"value": "not-an-int"}).encode(),
    )
    assert code == 400
