"""Unit tests for CookieAdminService — the add/replace gates (DESIGN_COOKIE_POOL.md §10).

The property under test throughout: **a rejected upload must leave the existing cookie
exactly where it was.** Validation, canary and compare-and-swap each get a case proving
the live cookie survived the failure.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from domain.entities.cookie import CookieSnapshot
from domain.enums.cookie_health import CookieHealth
from services.cookie_admin_service import CookieAdminService

_HEADER = "# Netscape HTTP Cookie File\n"


def _valid_export(marker: str = "x") -> bytes:
    body = "".join(
        f".youtube.com\tTRUE\t/\tTRUE\t1799790689\t{n}\t{marker}\n"
        for n in ("SID", "HSID", "SSID", "APISID", "SAPISID", "PREF")
    )
    return (_HEADER + body).encode()


def _snap(**kw: object) -> CookieSnapshot:
    base: dict[str, object] = {
        "id": 1,
        "label": "yt-01",
        "status": CookieHealth.EXPIRED,
        "file_version": 3,
        "egress_id": "warp-1",
    }
    base.update(kw)
    return CookieSnapshot(**base)  # type: ignore[arg-type]


class _FakeRepo:
    def __init__(self, cookies: list[CookieSnapshot] | None = None) -> None:
        self.cookies = {c.id: c for c in (cookies or [])}
        self.replaced: list[dict[str, object]] = []
        self.created: list[dict[str, object]] = []
        self.events: list[str] = []
        self.statuses: list[tuple[int, CookieHealth]] = []
        self.swap_ok = True

    async def list_all(self) -> list[CookieSnapshot]:
        return list(self.cookies.values())

    async def get(self, cookie_id: int) -> CookieSnapshot | None:
        return self.cookies.get(cookie_id)

    async def get_by_label(self, label: str) -> CookieSnapshot | None:
        return next((c for c in self.cookies.values() if c.label == label), None)

    async def create(self, **kw: object) -> CookieSnapshot:
        self.created.append(kw)
        return _snap(id=99, label=str(kw["label"]), status=CookieHealth.HEALTHY, file_version=1)

    async def replace_file(self, cookie_id: int, **kw: object) -> bool:
        self.replaced.append({"cookie_id": cookie_id, **kw})
        return self.swap_ok

    async def add_event(self, cookie_id: int, *, event: str, **_kw: object) -> None:
        self.events.append(event)

    async def set_status(self, cookie_id: int, *, status: CookieHealth, **_kw: object) -> None:
        self.statuses.append((cookie_id, status))
        current = self.cookies.get(cookie_id)
        if current is not None:
            self.cookies[cookie_id] = _snap(
                id=current.id, label=current.label, status=status,
                file_version=current.file_version, egress_id=current.egress_id,
            )


class _FakeStore:
    def __init__(self) -> None:
        self.files: dict[tuple[str, int], bytes] = {}
        self.deleted: list[tuple[str, int]] = []
        self.pruned: list[str] = []

    async def write(self, label: str, version: int, content: bytes) -> str:
        self.files[(label, version)] = content
        return f"hash-{len(content)}"

    async def materialise(self, label: str, version: int) -> Path:
        return Path(f"/var/tmp/{label}.v{version}.txt")  # noqa: S108 - fake

    async def delete(self, label: str, version: int) -> None:
        self.deleted.append((label, version))
        self.files.pop((label, version), None)

    async def exists(self, label: str, version: int) -> bool:
        return (label, version) in self.files

    async def prune(self, label: str, *, keep_from_version: int, keep: int = 2) -> None:
        self.pruned.append(label)


class _FakeCanary:
    def __init__(self, *, ok: bool = True, detail: str = "27 formats via warp-1") -> None:
        self.ok = ok
        self.detail = detail
        self.calls: list[tuple[Path, str | None]] = []

    async def canary_check(
        self, *, cookie_path: Path, egress_id: str | None = None
    ) -> tuple[bool, str]:
        self.calls.append((cookie_path, egress_id))
        return self.ok, self.detail


def _service(
    repo: _FakeRepo, store: _FakeStore | None = None, canary: _FakeCanary | None = None
) -> CookieAdminService:
    return CookieAdminService(
        repo,  # type: ignore[arg-type]
        store or _FakeStore(),  # type: ignore[arg-type]
        canary or _FakeCanary(),  # type: ignore[arg-type]
    )


# ------------------------------------------------------------------- replace ---


async def test_replace_writes_a_new_version_and_resets_health() -> None:
    repo, store, canary = _FakeRepo([_snap()]), _FakeStore(), _FakeCanary()
    result = await _service(repo, store, canary).replace(1, _valid_export("new"), actor_user_id=7)
    assert result.ok and result.kind == "replaced"
    assert result.version == 4  # v3 -> v4
    assert store.files[("yt-01", 4)] == _valid_export("new")
    swap = repo.replaced[0]
    assert swap["expected_version"] == 3  # compare-and-swap against what we read
    assert swap["actor_user_id"] == 7


async def test_replace_runs_the_canary_on_the_cookies_own_egress() -> None:
    # Affinity matters for the test too: verify the session where it will actually be used.
    repo, canary = _FakeRepo([_snap(egress_id="proxy-res-1")]), _FakeCanary()
    await _service(repo, canary=canary).replace(1, _valid_export())
    assert canary.calls and canary.calls[0][1] == "proxy-res-1"


async def test_invalid_upload_never_touches_the_live_cookie() -> None:
    repo, store, canary = _FakeRepo([_snap()]), _FakeStore(), _FakeCanary()
    result = await _service(repo, store, canary).replace(1, b"not a cookie file at all")
    assert not result.ok and result.kind == "invalid"
    assert repo.replaced == []          # nothing swapped
    assert ("yt-01", 4) not in store.files  # no new version written
    assert canary.calls == []           # not even tested — validation is the cheap gate


async def test_canary_failure_never_touches_the_live_cookie() -> None:
    repo, store = _FakeRepo([_snap()]), _FakeStore()
    canary = _FakeCanary(ok=False, detail="Sign in to confirm you are not a bot")
    result = await _service(repo, store, canary).replace(1, _valid_export())
    assert not result.ok and result.kind == "canary_failed"
    assert "not a bot" in result.detail  # the admin is told exactly what failed
    assert repo.replaced == []
    assert ("yt-01", 4) not in store.files


async def test_concurrent_replace_is_rejected_and_cleans_up_its_file() -> None:
    """Someone else replaced the same cookie mid-upload: report it, and do not leave
    an orphan version file behind."""
    repo, store = _FakeRepo([_snap()]), _FakeStore()
    repo.swap_ok = False
    result = await _service(repo, store).replace(1, _valid_export())
    assert not result.ok and result.kind == "conflict"
    assert ("yt-01", 4) in store.deleted


async def test_replace_of_a_missing_cookie_is_reported_not_crashed() -> None:
    result = await _service(_FakeRepo()).replace(42, _valid_export())
    assert not result.ok and result.kind == "error"


async def test_candidate_file_is_cleaned_up_after_the_gate() -> None:
    # The scratch candidate must never linger in the pool directory.
    repo, store = _FakeRepo([_snap()]), _FakeStore()
    await _service(repo, store).replace(1, _valid_export())
    assert any(label == "_candidate" for label, _ in store.deleted)


# ----------------------------------------------------------------------- add ---


async def test_add_assigns_the_next_free_label() -> None:
    repo = _FakeRepo([_snap(id=1, label="yt-01"), _snap(id=2, label="yt-02")])
    result = await _service(repo).add(_valid_export())
    assert result.ok and result.label == "yt-03"
    assert repo.events == ["cookie_added"]


async def test_add_rejects_an_invalid_file_without_creating_a_row() -> None:
    repo = _FakeRepo()
    result = await _service(repo).add(b"nope")
    assert not result.ok
    assert repo.created == []


# ------------------------------------------------------------ enable/disable ---


async def test_disable_and_enable_move_the_status() -> None:
    repo = _FakeRepo([_snap(status=CookieHealth.HEALTHY)])
    service = _service(repo)
    await service.set_enabled(1, enabled=False, actor_user_id=5)
    assert repo.statuses[-1] == (1, CookieHealth.DISABLED)
    await service.set_enabled(1, enabled=True, actor_user_id=5)
    assert repo.statuses[-1] == (1, CookieHealth.HEALTHY)


async def test_pool_summary_counts_only_selectable_cookies() -> None:
    repo = _FakeRepo(
        [
            _snap(id=1, label="a", status=CookieHealth.HEALTHY),
            _snap(id=2, label="b", status=CookieHealth.WARNING),
            _snap(id=3, label="c", status=CookieHealth.EXPIRED),
            _snap(id=4, label="d", status=CookieHealth.DISABLED),
        ]
    )
    assert await _service(repo).pool_summary() == (2, 4)


async def test_test_action_reports_the_canary_detail() -> None:
    repo = _FakeRepo([_snap()])
    canary = _FakeCanary(ok=True, detail="27 formats via warp-1")
    result = await _service(repo, canary=canary).test(1)
    assert result.ok and "27 formats" in result.detail


def test_snapshot_success_rate_is_none_before_first_use() -> None:
    assert _snap().success_rate is None
    used = _snap(total_success=9, total_auth_failures=1, last_used_at=datetime.datetime.now(
        datetime.UTC
    ))
    assert used.success_rate == 0.9
