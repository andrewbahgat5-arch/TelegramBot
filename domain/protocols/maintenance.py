"""Database-maintenance port (MASTER_PLAN Task 10.5, Section 8.1).

``CleanupWorker`` lives in ``workers/`` and may not import ``infrastructure``; it
drives partition rollover, retention drops, and orphan sweeps through this port,
whose concrete (``infrastructure.database.maintenance.DbMaintenance``) is injected
by the worker composition root.
"""

from __future__ import annotations

from typing import Protocol


class DbMaintenanceProtocol(Protocol):
    async def ensure_partitions(self) -> list[str]:
        """Pre-create the rolling window of monthly partitions; return their names."""
        ...

    async def drop_expired_partitions(self, retention_days: dict[str, int]) -> list[str]:
        """Drop partitions older than each table's retention; return dropped names.

        ``retention_days`` maps a partitioned table name (``downloads``/``jobs``/
        ``error_logs``) to its retention in days.
        """
        ...

    async def sweep_orphans(self) -> tuple[int, int]:
        """Delete orphaned ``active_downloads`` + ``job_waiters``; return their counts."""
        ...
