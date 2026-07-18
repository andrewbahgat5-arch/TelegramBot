"""Unit tests for CookiePoolService (DESIGN_COOKIE_POOL.md §7, §8, §15)."""

from __future__ import annotations

import datetime
from pathlib import Path

from domain.entities.cookie import CookieImpact, CookieSnapshot, CookieVerdict
from domain.enums.cookie_health import CookieHealth
from services.cookie_pool_service import CookiePolicy, CookiePoolService, LeaseBackend

_NOW = datetime.datetime(2026, 7, 18, 12, 0, tzinfo=datetime.UTC)


def _snap(**kw: object) -> CookieSnapshot:
    base: dict[str, object] = {
        "id": 1,
        "label": "yt-01",
        "status": CookieHealth.HEALTHY,
        "file_version": 1,
    }
    base.update(kw)
    return CookieSnapshot(**base)  # type: ignore[arg-type]


class _FakeRepo:
    def __init__(self, cookies: list[CookieSnapshot]) -> None:
        self.cookies = {c.id: c for c in cookies}
        self.outcomes: list[dict[str, object]] = []
        self.events: list[dict[str, object]] = []
        self.egress_set: list[tuple[int, str]] = []
        self.uses: list[int] = []

    async def list_candidates(self, *, egress_id: str, now: datetime.datetime):
        return [c for c in self.cookies.values() if c.is_selectable(now=now)]

    async def get(self, cookie_id: int) -> CookieSnapshot | None:
        return self.cookies.get(cookie_id)

    async def record_use(self, cookie_id: int, *, at: datetime.datetime) -> None:
        self.uses.append(cookie_id)

    async def record_outcome(self, cookie_id: int, **kw: object) -> None:
        self.outcomes.append({"cookie_id": cookie_id, **kw})

    async def set_egress(self, cookie_id: int, egress_id: str) -> None:
        self.egress_set.append((cookie_id, egress_id))

    async def add_event(self, cookie_id: int, **kw: object) -> None:
        self.events.append({"cookie_id": cookie_id, **kw})


class _FakeStore:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def materialise(self, label: str, version: int) -> Path:
        if self._fail:
            raise RuntimeError("store down")
        return Path(f"/var/tmp/{label}.v{version}.txt")  # noqa: S108 - fake, never written


class _FakeLock:
    """Minimal RedisLock stand-in with real slot semantics."""

    def __init__(self, *, busy: set[str] | None = None) -> None:
        self.held: set[str] = set(busy or ())
        self.released: list[str] = []

    async def acquire(self, key: str, *, ttl: int) -> str | None:
        if key in self.held:
            return None
        self.held.add(key)
        return f"token-{key}"

    async def release(self, key: str, token: str) -> bool:
        self.held.discard(key)
        self.released.append(key)
        return True


def _service(
    repo: _FakeRepo,
    *,
    policy: CookiePolicy | None = None,
    lock: _FakeLock | None = None,
    store: _FakeStore | None = None,
    hook: object = None,
) -> CookiePoolService:
    return CookiePoolService(
        repo,  # type: ignore[arg-type]
        store or _FakeStore(),  # type: ignore[arg-type]
        LeaseBackend(lock or _FakeLock()),
        policy or CookiePolicy(),
        on_health_change=hook,  # type: ignore[arg-type]
        now=lambda: _NOW,
    )


# ------------------------------------------------------------------ selection ---


async def test_prefers_a_cookie_pinned_to_the_requested_egress() -> None:
    repo = _FakeRepo(
        [
            _snap(id=1, label="yt-01", egress_id="proxy-res-1"),
            _snap(id=2, label="yt-02", egress_id="warp-1"),
        ]
    )
    lease = await _service(repo).acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None and lease.label == "yt-02"


async def test_unpinned_cookie_is_used_when_no_affine_one_exists() -> None:
    repo = _FakeRepo([_snap(id=1, egress_id="proxy-res-1"), _snap(id=2, egress_id=None)])
    lease = await _service(repo).acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None and lease.cookie_id == 2


async def test_foreign_cookie_is_not_borrowed_by_default() -> None:
    # Silently moving a session between exit IPs is what invalidates it.
    repo = _FakeRepo([_snap(id=1, egress_id="proxy-res-1")])
    assert await _service(repo).acquire(platform="youtube", egress_id="warp-1") is None


async def test_foreign_cookie_is_borrowed_when_explicitly_allowed() -> None:
    repo = _FakeRepo([_snap(id=1, egress_id="proxy-res-1")])
    service = _service(repo, policy=CookiePolicy(allow_affinity_break=True))
    lease = await service.acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None
    assert repo.egress_set == []  # borrowing must NOT re-pin


async def test_lru_offers_the_least_recently_used_first() -> None:
    older = _NOW - datetime.timedelta(hours=2)
    repo = _FakeRepo(
        [
            _snap(id=1, label="recent", egress_id="warp-1", last_used_at=_NOW),
            _snap(id=2, label="stale", egress_id="warp-1", last_used_at=older),
        ]
    )
    lease = await _service(repo).acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None and lease.label == "stale"


async def test_never_used_cookie_sorts_ahead_under_lru() -> None:
    repo = _FakeRepo(
        [
            _snap(id=1, label="used", egress_id="warp-1", last_used_at=_NOW),
            _snap(id=2, label="fresh", egress_id="warp-1", last_used_at=None),
        ]
    )
    lease = await _service(repo).acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None and lease.label == "fresh"


async def test_busy_cookie_is_skipped_for_the_next_one() -> None:
    # The lease cap is what stops two workers presenting one session simultaneously.
    lock = _FakeLock(busy={"cookie:lease:1:0"})
    repo = _FakeRepo(
        [
            _snap(id=1, label="busy", egress_id="warp-1", last_used_at=None),
            _snap(id=2, label="free", egress_id="warp-1", last_used_at=_NOW),
        ]
    )
    lease = await _service(repo, lock=lock).acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None and lease.label == "free"


async def test_cooling_down_cookie_is_not_selectable() -> None:
    repo = _FakeRepo(
        [
            _snap(
                id=1,
                egress_id="warp-1",
                cooldown_until=_NOW + datetime.timedelta(minutes=5),
            )
        ]
    )
    assert await _service(repo).acquire(platform="youtube", egress_id="warp-1") is None


async def test_expired_and_disabled_cookies_are_not_selectable() -> None:
    repo = _FakeRepo(
        [
            _snap(id=1, status=CookieHealth.EXPIRED, egress_id="warp-1"),
            _snap(id=2, status=CookieHealth.DISABLED, egress_id="warp-1"),
            _snap(id=3, status=CookieHealth.INVALID, egress_id="warp-1"),
        ]
    )
    assert await _service(repo).acquire(platform="youtube", egress_id="warp-1") is None


# --------------------------------------------------------- graceful degradation ---


async def test_empty_pool_returns_none_so_the_caller_runs_anonymously() -> None:
    assert await _service(_FakeRepo([])).acquire(platform="youtube", egress_id="warp-1") is None


async def test_repo_failure_degrades_to_anonymous_rather_than_raising() -> None:
    class _Broken(_FakeRepo):
        async def list_candidates(self, **_kw: object):
            raise RuntimeError("db down")

    assert await _service(_Broken([])).acquire(platform="youtube", egress_id="warp-1") is None


async def test_store_failure_releases_the_lease_and_moves_on() -> None:
    lock = _FakeLock()
    repo = _FakeRepo([_snap(id=1, egress_id="warp-1")])
    service = _service(repo, lock=lock, store=_FakeStore(fail=True))
    assert await service.acquire(platform="youtube", egress_id="warp-1") is None
    assert lock.released == ["cookie:lease:1:0"]  # no slot leaked


async def test_non_youtube_platforms_never_take_a_cookie() -> None:
    repo = _FakeRepo([_snap(id=1, egress_id="direct")])
    assert await _service(repo).acquire(platform="tiktok", egress_id="direct") is None


# ---------------------------------------------------------------------- health ---


async def test_route_failure_leaves_health_completely_untouched() -> None:
    """THE guarantee. A bot-check wall must not cost the cookie anything."""
    repo = _FakeRepo([_snap(id=1, egress_id="warp-1", auth_failures=1)])
    service = _service(repo)
    lease = await service.acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None
    await service.report(lease, CookieVerdict(CookieImpact.NONE, "route/network failure"))
    outcome = repo.outcomes[-1]
    assert outcome["status"] is CookieHealth.HEALTHY
    assert outcome["auth_failures"] == 1  # unchanged
    assert outcome["cooldown_until"] is None
    assert repo.events == []  # no health transition recorded


async def test_auth_failures_climb_to_warning_then_cooldown() -> None:
    policy = CookiePolicy(warning_threshold=2, cooldown_threshold=3, cooldown_seconds=300)
    repo = _FakeRepo([_snap(id=1, egress_id="warp-1", auth_failures=1)])
    service = _service(repo, policy=policy)
    lease = await service.acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None
    await service.report(lease, CookieVerdict(CookieImpact.AUTH_FAILURE, "please sign in"))
    assert repo.outcomes[-1]["status"] is CookieHealth.WARNING

    repo.cookies[1] = _snap(
        id=1, egress_id="warp-1", status=CookieHealth.WARNING, auth_failures=2
    )
    await service.report(lease, CookieVerdict(CookieImpact.AUTH_FAILURE, "please sign in"))
    last = repo.outcomes[-1]
    assert last["cooldown_until"] == _NOW + datetime.timedelta(seconds=300)
    assert last["cooldown_cycles"] == 1


async def test_cooldown_backoff_grows_with_each_cycle() -> None:
    policy = CookiePolicy(cooldown_threshold=1, cooldown_seconds=300, cooldown_max_seconds=3600)
    repo = _FakeRepo([_snap(id=1, egress_id="warp-1", cooldown_cycles=1)])
    service = _service(repo, policy=policy)
    lease = await service.acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None
    await service.report(lease, CookieVerdict(CookieImpact.AUTH_FAILURE, "401"))
    # second cycle -> 300 * 3 = 900s
    assert repo.outcomes[-1]["cooldown_until"] == _NOW + datetime.timedelta(seconds=900)


async def test_too_many_cooldown_cycles_expires_the_cookie() -> None:
    policy = CookiePolicy(cooldown_threshold=1, max_cooldown_cycles=2)
    repo = _FakeRepo([_snap(id=1, egress_id="warp-1", cooldown_cycles=2)])
    service = _service(repo, policy=policy)
    lease = await service.acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None
    await service.report(lease, CookieVerdict(CookieImpact.AUTH_FAILURE, "401"))
    assert repo.outcomes[-1]["status"] is CookieHealth.EXPIRED


async def test_rotated_session_expires_immediately_without_cooldown() -> None:
    repo = _FakeRepo([_snap(id=1, egress_id="warp-1")])
    service = _service(repo)
    lease = await service.acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None
    await service.report(lease, CookieVerdict(CookieImpact.EXPIRED, "no longer valid"))
    assert repo.outcomes[-1]["status"] is CookieHealth.EXPIRED
    assert repo.outcomes[-1]["cooldown_until"] is None


async def test_success_clears_failures_and_restores_health() -> None:
    repo = _FakeRepo(
        [_snap(id=1, egress_id="warp-1", status=CookieHealth.WARNING, auth_failures=2)]
    )
    service = _service(repo)
    lease = await service.acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None
    await service.report(lease, CookieVerdict(CookieImpact.SUCCESS))
    outcome = repo.outcomes[-1]
    assert outcome["status"] is CookieHealth.HEALTHY
    assert outcome["auth_failures"] == 0
    assert outcome["cooldown_cycles"] == 0


async def test_first_success_pins_an_unpinned_cookie_to_its_egress() -> None:
    repo = _FakeRepo([_snap(id=1, egress_id=None)])
    service = _service(repo)
    lease = await service.acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None
    await service.report(lease, CookieVerdict(CookieImpact.SUCCESS))
    assert repo.egress_set == [(1, "warp-1")]


async def test_terminal_states_invoke_the_notification_hook() -> None:
    seen: list[tuple[str, CookieHealth]] = []

    async def hook(cookie: CookieSnapshot, to: CookieHealth, reason: str) -> None:
        seen.append((cookie.label, to))

    repo = _FakeRepo([_snap(id=1, egress_id="warp-1")])
    service = _service(repo, hook=hook)
    lease = await service.acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None
    await service.report(lease, CookieVerdict(CookieImpact.INVALID, "malformed"))
    assert seen == [("yt-01", CookieHealth.INVALID)]


async def test_a_failing_notification_never_breaks_the_flow() -> None:
    async def hook(*_a: object, **_k: object) -> None:
        raise RuntimeError("telegram down")

    repo = _FakeRepo([_snap(id=1, egress_id="warp-1")])
    service = _service(repo, hook=hook)
    lease = await service.acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None
    await service.report(lease, CookieVerdict(CookieImpact.EXPIRED, "dead"))  # must not raise


async def test_release_frees_the_slot_and_is_idempotent() -> None:
    lock = _FakeLock()
    repo = _FakeRepo([_snap(id=1, egress_id="warp-1")])
    service = _service(repo, lock=lock)
    lease = await service.acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None
    await service.release(lease)
    await service.release(lease)  # second call is a no-op
    assert lock.released == ["cookie:lease:1:0"]


async def test_pool_rotates_instead_of_hammering_one_pinned_cookie() -> None:
    """REGRESSION (found in production): with one pinned cookie and several fresh ones,
    ranking unpinned below affine made the pinned cookie win every request — six
    consecutive leases all returned yt-01 while the others sat idle. Load spreading is
    the entire point of the pool, so all usable cookies compete under the strategy."""
    older = _NOW - datetime.timedelta(hours=1)
    repo = _FakeRepo(
        [
            _snap(id=1, label="yt-01", egress_id="warp-1", last_used_at=_NOW),
            _snap(id=2, label="yt-02", egress_id=None, last_used_at=None),
            _snap(id=3, label="yt-03", egress_id=None, last_used_at=older),
        ]
    )
    service = _service(repo)
    lease = await service.acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None
    # Never-used first, then the hour-old one — the recently-used pinned cookie is last.
    assert lease.label == "yt-02"


async def test_unpinned_cookie_outranks_a_recently_used_affine_one() -> None:
    repo = _FakeRepo(
        [
            _snap(id=1, label="affine-fresh", egress_id="warp-1", last_used_at=_NOW),
            _snap(id=2, label="unpinned-stale", egress_id=None, last_used_at=None),
        ]
    )
    lease = await _service(repo).acquire(platform="youtube", egress_id="warp-1")
    assert lease is not None and lease.label == "unpinned-stale"
