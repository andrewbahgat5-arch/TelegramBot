"""CookiePoolService — selection, leasing and health for the YouTube cookie pool.

Implements DESIGN_COOKIE_POOL.md §7 (health), §8 (selection/affinity/concurrency) and
§15 (graceful degradation). The provider talks to this through
:class:`~domain.protocols.cookies.CookieProviderProtocol`, so ``infrastructure`` never
imports a service.

Three invariants this module is responsible for:

1. **Only auth signals change health.** ``report`` consults ``verdict.affects_health``;
   route and content failures update statistics and nothing else.
2. **A session stays on one egress.** Selection prefers cookies pinned to the requested
   endpoint; an unpinned cookie is pinned on its first success. Borrowing across
   endpoints is off unless explicitly enabled, and never re-pins.
3. **The pool never blocks a download.** No cookie, no Redis, no rows — ``acquire``
   returns ``None`` and the caller runs anonymously.
"""

from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from core.logging import get_logger
from domain.entities.cookie import CookieImpact, CookieLease, CookieSnapshot, CookieVerdict
from domain.enums.cookie_health import NOTIFY_HEALTH, CookieHealth
from domain.protocols.cookies import CookieRepositoryProtocol, CookieStoreProtocol
from services.cookie_classifier import classify

_log = get_logger("services.cookie_pool")

#: Called when a cookie enters a state the Owner/Moderators must hear about.
HealthChangeHook = Callable[[CookieSnapshot, CookieHealth, str], Awaitable[None]]

#: Supplies the current policy. Injected so the six knobs can be admin-edited at
#: runtime (DESIGN_COOKIE_POOL.md §13) without a redeploy; omitted in tests, which
#: pass a fixed CookiePolicy instead.
PolicyProvider = Callable[[], Awaitable["CookiePolicy"]]


@dataclass(frozen=True, slots=True)
class CookiePolicy:
    """Runtime-tunable policy (DESIGN_COOKIE_POOL.md §13).

    Built from the admin-editable settings so thresholds change without a redeploy.
    """

    strategy: str = "lru"  # lru | round_robin | weighted | sticky
    max_concurrent_leases: int = 1
    warning_threshold: int = 2
    cooldown_threshold: int = 3
    cooldown_seconds: int = 300
    cooldown_max_seconds: int = 3600
    max_cooldown_cycles: int = 3
    lease_ttl_seconds: int = 900
    allow_affinity_break: bool = False

    def backoff_for(self, cycle: int) -> int:
        """Exponential backoff, capped: 5m, 15m, 45m … up to ``cooldown_max_seconds``."""
        seconds: int = self.cooldown_seconds * (3 ** max(cycle, 0))
        return min(seconds, self.cooldown_max_seconds)


class LeaseBackend:
    """Redis-backed exclusive slots per cookie.

    ``max_concurrent_leases`` slots exist per cookie; acquiring takes the first free one.
    The default of 1 is what stops two workers presenting the same Google session at the
    same moment — the pattern that causes rotation races and looks automated. The lock
    TTL returns a slot automatically if a worker dies mid-run.
    """

    def __init__(self, lock: Any) -> None:
        self._lock = lock

    async def acquire(self, cookie_id: int, *, slots: int, ttl: int) -> tuple[str, str] | None:
        for slot in range(max(slots, 1)):
            key = f"cookie:lease:{cookie_id}:{slot}"
            token = await self._lock.acquire(key, ttl=ttl)
            if token:
                return key, token
        return None

    async def release(self, key: str, token: str) -> None:
        try:
            await self._lock.release(key, token)
        except Exception as exc:  # never let lease cleanup break a request
            _log.warning("cookie_lease_release_failed", error=str(exc))


class CookiePoolService:
    def __init__(
        self,
        repo: CookieRepositoryProtocol,
        store: CookieStoreProtocol,
        leases: LeaseBackend,
        policy: CookiePolicy,
        *,
        policy_provider: PolicyProvider | None = None,
        on_health_change: HealthChangeHook | None = None,
        now: Callable[[], datetime.datetime] | None = None,
    ) -> None:
        self._repo = repo
        self._store = store
        self._leases = leases
        self._policy = policy
        self._policy_provider = policy_provider
        self._on_health_change = on_health_change
        self._now = now or (lambda: datetime.datetime.now(datetime.UTC))
        self._lease_keys: dict[int, tuple[str, str]] = {}

    # ---------------------------------------------------------------- selection ---

    async def acquire(self, *, platform: str, egress_id: str) -> CookieLease | None:
        """Lease a cookie for this egress, or None to proceed anonymously.

        Anonymous is a legitimate outcome: measured 2026-07-18, most YouTube videos
        extract fine without cookies, so an exhausted pool must cost logged-in content
        rather than the whole request.
        """
        if platform != "youtube":  # only YouTube uses cookies today
            return None
        await self._refresh_policy()
        try:
            candidates = await self._repo.list_candidates(
                egress_id=egress_id, now=self._now()
            )
        except Exception as exc:  # DB trouble must not block downloads
            _log.warning("cookie_candidates_failed", error=str(exc), egress_id=egress_id)
            return None

        for cookie in self._order(candidates, egress_id=egress_id):
            held = await self._leases.acquire(
                cookie.id,
                slots=self._policy.max_concurrent_leases,
                ttl=self._policy.lease_ttl_seconds,
            )
            if held is None:
                continue  # every slot busy — try the next cookie
            key, token = held
            try:
                path = await self._store.materialise(cookie.label, cookie.file_version)
            except Exception as exc:
                await self._leases.release(key, token)
                _log.warning(
                    "cookie_materialise_failed", label=cookie.label, error=str(exc)
                )
                continue
            self._lease_keys[cookie.id] = (key, token)
            await self._repo.record_use(cookie.id, at=self._now())
            _log.info(
                "cookie_selected",
                cookie_label=cookie.label,
                egress_id=egress_id,
                strategy=self._policy.strategy,
                borrowed=cookie.egress_id not in (None, egress_id),
            )
            return CookieLease(
                cookie_id=cookie.id,
                label=cookie.label,
                path=path,
                file_version=cookie.file_version,
                egress_id=egress_id,
                token=token,
                probationary=cookie.cooldown_cycles > 0,
            )

        _log.info("cookie_pool_empty", egress_id=egress_id, candidates=len(candidates))
        return None

    def _order(
        self, candidates: list[CookieSnapshot], *, egress_id: str
    ) -> list[CookieSnapshot]:
        """Affinity groups first, strategy applied within each group (§8).

        Affine → unpinned → (borrowed, only if explicitly allowed). Borrowing never
        re-pins: silently moving a session between exit IPs is what invalidates it.
        """
        affine = [c for c in candidates if c.egress_id == egress_id]
        unpinned = [c for c in candidates if c.egress_id is None]
        ordered = self._by_strategy(affine) + self._by_strategy(unpinned)
        if self._policy.allow_affinity_break:
            foreign = [
                c for c in candidates if c.egress_id not in (None, egress_id)
            ]
            ordered += self._by_strategy(foreign)
        return ordered

    def _by_strategy(self, group: list[CookieSnapshot]) -> list[CookieSnapshot]:
        strategy = self._policy.strategy
        if strategy == "round_robin":
            # Stable rotation without shared state: order by total uses, so the least
            # exercised cookie is offered first and usage evens out over time.
            return sorted(group, key=lambda c: (c.total_uses, c.id))
        if strategy == "weighted":
            return sorted(group, key=lambda c: (-(c.success_rate or 1.0), c.id))
        if strategy == "sticky":
            return sorted(group, key=lambda c: c.id)
        # Default LRU: maximise the gap between uses of any one session, which is what
        # actually reduces per-account rate-limit pressure. Never-used sorts first.
        never = datetime.datetime.min.replace(tzinfo=datetime.UTC)
        return sorted(group, key=lambda c: (c.last_used_at or never, c.id))

    # ------------------------------------------------------------------ outcome ---

    async def report_run(
        self, lease: CookieLease, *, returncode: int, stderr: str
    ) -> None:
        """Classify one yt-dlp run and apply it (the provider-facing entry point)."""
        await self._refresh_policy()
        await self.report(lease, classify(returncode, stderr))

    async def _refresh_policy(self) -> None:
        """Pick up admin edits to the policy. The provider caches, so this is cheap."""
        if self._policy_provider is None:
            return
        try:
            self._policy = await self._policy_provider()
        except Exception as exc:  # keep the last good policy
            _log.warning("cookie_policy_refresh_failed", error=str(exc))

    async def report(self, lease: CookieLease, verdict: CookieVerdict) -> None:
        """Apply an outcome. Only ``verdict.affects_health`` may change health."""
        try:
            await self._apply(lease, verdict)
        except Exception as exc:  # health bookkeeping must never fail a download
            _log.warning(
                "cookie_report_failed", cookie_label=lease.label, error=str(exc)
            )

    async def _apply(self, lease: CookieLease, verdict: CookieVerdict) -> None:
        cookie = await self._repo.get(lease.cookie_id)
        if cookie is None:
            return
        now = self._now()

        if verdict.impact is CookieImpact.SUCCESS:
            await self._on_success(cookie, lease, now)
            return

        if not verdict.affects_health:
            # Route/content/unknown: statistics only. This is the guarantee.
            await self._repo.record_outcome(
                cookie.id,
                verdict=verdict,
                status=cookie.status,
                cooldown_until=cookie.cooldown_until,
                auth_failures=cookie.auth_failures,
                cooldown_cycles=cookie.cooldown_cycles,
                at=now,
            )
            return

        await self._on_auth_failure(cookie, verdict, now)

    async def _on_success(
        self, cookie: CookieSnapshot, lease: CookieLease, now: datetime.datetime
    ) -> None:
        status = (
            CookieHealth.HEALTHY
            if cookie.status is CookieHealth.WARNING
            else cookie.status
        )
        await self._repo.record_outcome(
            cookie.id,
            verdict=CookieVerdict(CookieImpact.SUCCESS),
            status=status,
            cooldown_until=None,
            auth_failures=0,
            cooldown_cycles=0,
            at=now,
        )
        if cookie.egress_id is None:
            # First successful use pins the session to this endpoint (§8).
            await self._repo.set_egress(cookie.id, lease.egress_id)
            await self._repo.add_event(
                cookie.id, event="cookie_affinity_pinned", egress_id=lease.egress_id
            )
            _log.info(
                "cookie_affinity_pinned",
                cookie_label=cookie.label,
                egress_id=lease.egress_id,
            )
        if cookie.status is not CookieHealth.HEALTHY:
            await self._transition(cookie, CookieHealth.HEALTHY, "recovered after success")

    async def _on_auth_failure(
        self, cookie: CookieSnapshot, verdict: CookieVerdict, now: datetime.datetime
    ) -> None:
        policy = self._policy

        # Terminal verdicts skip the ladder entirely — no cooldown will revive them.
        if verdict.impact in (CookieImpact.EXPIRED, CookieImpact.INVALID):
            target = (
                CookieHealth.EXPIRED
                if verdict.impact is CookieImpact.EXPIRED
                else CookieHealth.INVALID
            )
            await self._repo.record_outcome(
                cookie.id,
                verdict=verdict,
                status=target,
                cooldown_until=None,
                auth_failures=cookie.auth_failures + 1,
                cooldown_cycles=cookie.cooldown_cycles,
                at=now,
            )
            await self._transition(cookie, target, verdict.reason)
            return

        failures = cookie.auth_failures + 1
        cycles = cookie.cooldown_cycles
        status = cookie.status
        cooldown_until: datetime.datetime | None = None

        if failures >= policy.cooldown_threshold:
            cycles += 1
            if cycles > policy.max_cooldown_cycles:
                status = CookieHealth.EXPIRED
            else:
                status = CookieHealth.WARNING
                cooldown_until = now + datetime.timedelta(
                    seconds=policy.backoff_for(cycles - 1)
                )
                failures = 0  # the ladder resets; cycles carry the escalation
        elif failures >= policy.warning_threshold:
            status = CookieHealth.WARNING

        await self._repo.record_outcome(
            cookie.id,
            verdict=verdict,
            status=status,
            cooldown_until=cooldown_until,
            auth_failures=failures,
            cooldown_cycles=cycles,
            at=now,
        )
        if status is not cookie.status:
            await self._transition(cookie, status, verdict.reason)
        elif cooldown_until is not None:
            _log.info(
                "cookie_cooldown_started",
                cookie_label=cookie.label,
                until=cooldown_until.isoformat(),
                cycle=cycles,
            )

    async def _transition(
        self, cookie: CookieSnapshot, to: CookieHealth, reason: str
    ) -> None:
        _log.info(
            "cookie_health_changed",
            cookie_label=cookie.label,
            from_status=str(cookie.status),
            to_status=str(to),
            reason=reason[:200],
        )
        await self._repo.add_event(
            cookie.id,
            event="cookie_health_changed",
            from_status=cookie.status,
            to_status=to,
            reason=reason[:200],
            egress_id=cookie.egress_id,
        )
        if to in NOTIFY_HEALTH and self._on_health_change is not None:
            try:
                await self._on_health_change(cookie, to, reason)
            except Exception as exc:  # a failed notification must not break the flow
                _log.warning("cookie_notify_failed", error=str(exc))

    # ------------------------------------------------------------------ release ---

    async def release(self, lease: CookieLease) -> None:
        """Release the lease slot. Safe to call twice; never raises."""
        held = self._lease_keys.pop(lease.cookie_id, None)
        if held is None:
            return
        await self._leases.release(*held)
