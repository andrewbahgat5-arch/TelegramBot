"""CleanupWorker (MASTER_PLAN Component 9.3, Task 6.10).

Sprint 6 ships the minimal sweep: delete temp download files/dirs older than
``max_age_seconds`` (default 60 s, Section 14.6). The full duties — partition
pre-creation, stale ``active_downloads``/``job_waiters`` reconciliation, and
retention drops — are added in Sprint 10 (Task 10.5).
"""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path

from core.logging import get_logger

_log = get_logger("workers.cleanup_worker")


class CleanupWorker:
    def __init__(
        self,
        temp_dir: Path,
        *,
        max_age_seconds: float = 60.0,
        interval_seconds: float = 60.0,
    ) -> None:
        self._temp_dir = temp_dir
        self._max_age = max_age_seconds
        self._interval = interval_seconds

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

    async def run_forever(self) -> None:  # pragma: no cover - thin loop over sweep_once
        _log.info("cleanup_worker_started", temp_dir=str(self._temp_dir))
        while True:
            self.sweep_once()
            await asyncio.sleep(self._interval)
