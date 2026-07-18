"""Unit tests for CookieProber — automatic recovery of EXPIRED cookies (§7)."""

from __future__ import annotations

import datetime
from pathlib import Path

from domain.entities.cookie import CookieSnapshot
from domain.enums.cookie_health import CookieHealth
from workers.cookie_prober import CookieProber

_NOW = datetime.datetime(2026, 7, 18, 12, 0, tzinfo=datetime.UTC)


def _snap(**kw: object) -> CookieSnapshot:
    base: dict[str, object] = {
        "id": 1,
        "label": "yt-01",
        "status": CookieHealth.EXPIRED,
        "file_version": 1,
        "egress_id": "warp-1",
    }
    base.update(kw)
    return CookieSnapshot(**base)  # type: ignore[arg-type]


class _FakeRepo:
    def __init__(self, cookies: list[CookieSnapshot]) -> None:
        self._cookies = cookies
        self.statuses: list[tuple[int, CookieHealth]] = []
        self.events: list[str] = []

    async def list_all(self) -> list[CookieSnapshot]:
        return list(self._cookies)

    async def set_status(self, cookie_id: int, *, status: CookieHealth, **_kw: object) -> None:
        self.statuses.append((cookie_id, status))

    async def add_event(self, cookie_id: int, *, event: str, **_kw: object) -> None:
        self.events.append(event)


class _FakeStore:
    def __init__(self, *, present: bool = True) -> None:
        self._present = present

    async def exists(self, label: str, version: int) -> bool:
        return self._present

    async def materialise(self, label: str, version: int) -> Path:
        return Path(f"/var/tmp/{label}.v{version}.txt")  # noqa: S108 - fake


class _FakeCanary:
    def __init__(self, *, ok: bool) -> None:
        self.ok = ok
        self.calls: list[str | None] = []

    async def canary_check(
        self, *, cookie_path: Path, egress_id: str | None = None
    ) -> tuple[bool, str]:
        self.calls.append(egress_id)
        return self.ok, "37 formats via warp-1" if self.ok else "still blocked"


def _prober(
    repo: _FakeRepo,
    *,
    ok: bool = True,
    store: _FakeStore | None = None,
    on_recovered: object = None,
) -> CookieProber:
    return CookieProber(
        repo,  # type: ignore[arg-type]
        store or _FakeStore(),  # type: ignore[arg-type]
        _FakeCanary(ok=ok),  # type: ignore[arg-type]
        on_recovered=on_recovered,  # type: ignore[arg-type]
    )


async def test_a_working_expired_cookie_is_restored() -> None:
    repo = _FakeRepo([_snap()])
    assert await _prober(repo).probe_once() == 1
    assert repo.statuses == [(1, CookieHealth.HEALTHY)]
    assert "cookie_recovered" in repo.events


async def test_a_still_broken_cookie_stays_expired() -> None:
    repo = _FakeRepo([_snap()])
    assert await _prober(repo, ok=False).probe_once() == 0
    assert repo.statuses == []  # untouched
    assert repo.events == ["cookie_probe_failed"]


async def test_invalid_and_disabled_are_never_probed() -> None:
    """INVALID cannot be fixed by probing, and DISABLED is a human decision the system
    must not overrule."""
    repo = _FakeRepo(
        [
            _snap(id=1, status=CookieHealth.INVALID),
            _snap(id=2, status=CookieHealth.DISABLED),
            _snap(id=3, status=CookieHealth.HEALTHY),
            _snap(id=4, status=CookieHealth.WARNING),
        ]
    )
    assert await _prober(repo).probe_once() == 0
    assert repo.statuses == []


async def test_probe_uses_the_cookies_own_egress() -> None:
    repo = _FakeRepo([_snap(egress_id="proxy-res-1")])
    canary = _FakeCanary(ok=True)
    prober = CookieProber(repo, _FakeStore(), canary)  # type: ignore[arg-type]
    await prober.probe_once()
    assert canary.calls == ["proxy-res-1"]


async def test_a_row_whose_file_vanished_becomes_invalid_not_probed() -> None:
    repo = _FakeRepo([_snap()])
    result = await _prober(repo, store=_FakeStore(present=False)).probe_once()
    assert result == 0
    assert repo.statuses == [(1, CookieHealth.INVALID)]


async def test_only_one_cookie_is_probed_per_cycle() -> None:
    # Firing several authenticated requests in a burst is the opposite of what a
    # cooled-off session needs.
    repo = _FakeRepo([_snap(id=1, label="a"), _snap(id=2, label="b"), _snap(id=3, label="c")])
    assert await _prober(repo).probe_once() == 1


async def test_oldest_failure_is_probed_first() -> None:
    old = _NOW - datetime.timedelta(days=1)
    repo = _FakeRepo(
        [
            _snap(id=1, label="recent", last_failure_at=_NOW),
            _snap(id=2, label="oldest", last_failure_at=old),
        ]
    )
    await _prober(repo).probe_once()
    assert repo.statuses == [(2, CookieHealth.HEALTHY)]  # the stale one


async def test_empty_pool_is_a_no_op() -> None:
    assert await _prober(_FakeRepo([])).probe_once() == 0


async def test_recovery_hook_failure_does_not_undo_the_recovery() -> None:
    async def boom(_label: str) -> None:
        raise RuntimeError("telegram down")

    repo = _FakeRepo([_snap()])
    assert await _prober(repo, on_recovered=boom).probe_once() == 1
    assert repo.statuses == [(1, CookieHealth.HEALTHY)]
