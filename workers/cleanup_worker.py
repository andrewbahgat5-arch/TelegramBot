"""CleanupWorker (MASTER_PLAN Component 9.3, Task 6.10 + 10.5).

Two cadences run from one loop:

* **Temp sweep** (every ``interval_seconds``): delete temp download files/dirs older
  than ``max_age_seconds`` (Section 14.6).
* **DB maintenance** (every ``maintenance_interval_seconds``, Task 10.5): pre-create
  the rolling partition window, sweep orphaned ``active_downloads``/``job_waiters``
  (e.g. left by a crashed worker), and drop partitions past each table's retention
  (D-015 partitioned drop). The DB work runs through the injected
  ``DbMaintenanceProtocol`` so this worker keeps the Section 8.1 layering (no
  ``infrastructure`` import).

The minimal Sprint 6 temp-only worker remains the default when no maintenance port is
injected, so existing call sites and tests are unaffected.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from core.logging import get_logger
from domain.protocols.maintenance import DbMaintenanceProtocol

_log = get_logger("workers.cleanup_worker")

RetentionReader = Callable[[], Awaitable[dict[str, int]]]

_DEFAULT_MAINTENANCE_INTERVAL = 3600.0  # hourly; partition/retention work is not hot.
# Backstop only: a job still "processing" this long after it began — with no restart to
# trigger the startup crash-recovery reclaim — is almost certainly dead (a legitimate
# download finishes far sooner). Kept generous so a slow-but-live download is never reaped.
_DEFAULT_STALLED_CEILING = 7200.0  # 2 hours


class CleanupWorker:
    def __init__(
        self,
        temp_dir: Path,
        *,
        max_age_seconds: float = 60.0,
        interval_seconds: float = 60.0,
        maintenance: DbMaintenanceProtocol | None = None,
        retention_reader: RetentionReader | None = None,
        maintenance_interval_seconds: float = _DEFAULT_MAINTENANCE_INTERVAL,
        stalled_job_ceiling_seconds: float = _DEFAULT_STALLED_CEILING,
    ) -> None:
        self._temp_dir = temp_dir
        self._max_age = max_age_seconds
        self._interval = interval_seconds
        self._maintenance = maintenance
        self._retention_reader = retention_reader
        self._maintenance_interval = maintenance_interval_seconds
        self._stalled_ceiling = stalled_job_ceiling_seconds

    def sweep_once(self, *, now: float | None = None) -> int:
        """Remove temp entries older than ``max_age_seconds``; return the count removed."""
        if not self._temp_dir.exists():
            return 0
        cutoff = (now if now is not None else time.time()) - self._max_age
        removed = 0
        for entry in self._temp_dir.iterdir():
            try:
                if entry.stat().st_mtime >= cutoff:
                    continue
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
                removed += 1
            except OSError as exc:  # a vanished/locked entry must not abort the sweep
                _log.warning("cleanup_entry_failed", path=str(entry), error=str(exc))
        if removed:
            _log.info("cleanup_swept", removed=removed)
        return removed

    async def maintain_once(self) -> None:
        """Run partition rollover, orphan sweep, and retention drops (Task 10.5).

        Each duty is isolated: a failure in one is logged and the others still run,
        and the periodic loop is never crashed by a maintenance error.
        """
        if self._maintenance is None:
            return
        try:
            ensured = await self._maintenance.ensure_partitions()
            _log.info("cleanup_partitions_ensured", count=len(ensured))
        except Exception as exc:  # boundary: a maintenance failure must not stop cleanup
            _log.warning("cleanup_partitions_failed", error=str(exc))
        try:
            # Backstop reclaim: fail jobs stuck "processing" past the ceiling (a hang
            # with no restart). Age-gated so a still-running download is never reaped;
            # the aggressive reap-all crash recovery runs once at startup (workers/main).
            reclaimed = await self._maintenance.reclaim_stalled_jobs(
                older_than_seconds=self._stalled_ceiling
            )
            if reclaimed:
                _log.info("cleanup_stalled_jobs_reclaimed", jobs=reclaimed)
        except Exception as exc:  # boundary
            _log.warning("cleanup_reclaim_failed", error=str(exc))
        try:
            active, waiters = await self._maintenance.sweep_orphans()
            if active or waiters:
                _log.info("cleanup_orphans_swept", active_downloads=active, job_waiters=waiters)
        except Exception as exc:  # boundary
            _log.warning("cleanup_orphans_failed", error=str(exc))
        if self._retention_reader is not None:
            try:
                retention = await self._retention_reader()
                dropped = await self._maintenance.drop_expired_partitions(retention)
                if dropped:
                    _log.info("cleanup_partitions_dropped", partitions=dropped)
            except Exception as exc:  # boundary
                _log.warning("cleanup_retention_failed", error=str(exc))

    async def run_forever(self) -> None:  # pragma: no cover - thin loop over the once-methods
        _log.info("cleanup_worker_started", temp_dir=str(self._temp_dir))
        await self.maintain_once()  # run maintenance once at startup, then on its cadence
        last_maintenance = time.monotonic()
        while True:
            self.sweep_once()
            if time.monotonic() - last_maintenance >= self._maintenance_interval:
                await self.maintain_once()
                last_maintenance = time.monotonic()
            await asyncio.sleep(self._interval)
