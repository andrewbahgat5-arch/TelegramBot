"""CookieProber — bring EXPIRED cookies back automatically (DESIGN_COOKIE_POOL.md §7).

A YouTube session that Google rejected today is often accepted again later: rotation
settles, a rate-limit window passes, a flagged exit IP cools off. Without this, every
such cookie waits for a human to notice and re-upload something that was never actually
broken.

Scope is deliberately narrow — **only ``EXPIRED``**:

* ``INVALID`` means the file itself is unusable or the account is gone. Probing cannot
  fix either, and retrying a terminated account is exactly the kind of traffic that
  draws attention.
* ``DISABLED`` is a human decision. Silently re-enabling it would be the system
  overruling an admin.

Its own loop rather than a branch inside ``CleanupWorker``: the cadence is different
(hourly-ish vs. minutes), it makes real network calls, and a hung probe must not delay
temp-file cleanup or partition maintenance.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from core.logging import get_logger
from domain.enums.cookie_health import RECOVERABLE_HEALTH, CookieHealth
from domain.protocols.cookies import (
    CookieCanaryProtocol,
    CookieRepositoryProtocol,
    CookieStoreProtocol,
)

_log = get_logger("workers.cookie_prober")

#: Reads the probe interval so an admin can retune it without a restart.
IntervalReader = Callable[[], Awaitable[int]]

_DEFAULT_INTERVAL = 3600
#: Probe one cookie per cycle. Recovery is not urgent, and firing several authenticated
#: requests at YouTube in a burst is the opposite of what a cooled-off session needs.
_PROBES_PER_CYCLE = 1


class CookieProber:
    def __init__(
        self,
        repo: CookieRepositoryProtocol,
        store: CookieStoreProtocol,
        canary: CookieCanaryProtocol,
        *,
        interval_reader: IntervalReader | None = None,
        interval_seconds: int = _DEFAULT_INTERVAL,
        on_recovered: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._repo = repo
        self._store = store
        self._canary = canary
        self._interval_reader = interval_reader
        self._interval = interval_seconds
        self._on_recovered = on_recovered

    async def run(self) -> None:
        """Loop forever. Never raises: a probe failure must not kill the worker."""
        while True:
            try:
                await self.probe_once()
            except Exception as exc:
                _log.warning("cookie_probe_cycle_failed", error=str(exc))
            await asyncio.sleep(await self._current_interval())

    async def probe_once(self) -> int:
        """Probe up to ``_PROBES_PER_CYCLE`` recoverable cookies. Returns how many recovered."""
        candidates = [
            c for c in await self._repo.list_all() if c.status in RECOVERABLE_HEALTH
        ]
        if not candidates:
            return 0

        # Oldest failure first: the one most likely to have cooled off.
        candidates.sort(key=lambda c: (c.last_failure_at is not None, c.last_failure_at))
        recovered = 0
        for cookie in candidates[:_PROBES_PER_CYCLE]:
            if not await self._store.exists(cookie.label, cookie.file_version):
                # The row outlived its file — mark it rather than probing a missing path.
                await self._repo.set_status(
                    cookie.id,
                    status=CookieHealth.INVALID,
                    reason="cookie file missing at probe time",
                )
                continue
            path = await self._store.materialise(cookie.label, cookie.file_version)
            ok, detail = await self._canary.canary_check(
                cookie_path=path, egress_id=cookie.egress_id
            )
            _log.info(
                "cookie_probed",
                cookie_label=cookie.label,
                ok=ok,
                detail=detail[:120],
                egress_id=cookie.egress_id,
            )
            if not ok:
                await self._repo.add_event(
                    cookie.id,
                    event="cookie_probe_failed",
                    reason=detail[:200],
                    egress_id=cookie.egress_id,
                )
                continue

            await self._repo.set_status(
                cookie.id,
                status=CookieHealth.HEALTHY,
                reason=f"recovered by probe: {detail[:120]}",
            )
            await self._repo.add_event(
                cookie.id,
                event="cookie_recovered",
                to_status=CookieHealth.HEALTHY,
                reason=detail[:200],
                egress_id=cookie.egress_id,
            )
            _log.info("cookie_recovered", cookie_label=cookie.label, detail=detail[:120])
            recovered += 1
            if self._on_recovered is not None:
                try:
                    await self._on_recovered(cookie.label)
                except Exception as exc:  # a failed notice must not undo the recovery
                    _log.warning("cookie_recovered_notify_failed", error=str(exc))
        return recovered

    async def _current_interval(self) -> int:
        if self._interval_reader is None:
            return self._interval
        try:
            return max(await self._interval_reader(), 60)
        except Exception as exc:
            _log.warning("cookie_probe_interval_read_failed", error=str(exc))
            return self._interval
