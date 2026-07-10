"""Database maintenance adapter (MASTER_PLAN Task 10.5, D-015/D-016).

Implements ``DbMaintenanceProtocol`` for the CleanupWorker: pre-creates the rolling
partition window, drops partitions past each table's retention (storage reclaimed in
O(1) per month, D-015), and sweeps orphaned ``active_downloads`` / ``job_waiters``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from infrastructure.database.partitioning import (
    RUNTIME_PARTITIONED_TABLES,
    drop_partitions_older_than,
    ensure_partitions_for_next_n_months,
)
from infrastructure.database.repositories.active_download import ActiveDownloadRepository
from infrastructure.database.repositories.job import JobRepository
from infrastructure.database.repositories.job_waiter import JobWaiterRepository


class DbMaintenance:
    def __init__(
        self,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        lookahead_months: int = 12,
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory
        self._lookahead = lookahead_months

    async def ensure_partitions(self) -> list[str]:
        async with self._engine.begin() as conn:
            return await ensure_partitions_for_next_n_months(conn, self._lookahead)

    async def drop_expired_partitions(self, retention_days: dict[str, int]) -> list[str]:
        today = datetime.now(UTC).date()
        dropped: list[str] = []
        async with self._engine.begin() as conn:
            for table in RUNTIME_PARTITIONED_TABLES:
                days = retention_days.get(table)
                if not days or days <= 0:
                    continue
                cutoff = today - timedelta(days=days)
                dropped.extend(await drop_partitions_older_than(conn, table, cutoff=cutoff))
        return dropped

    async def sweep_orphans(self) -> tuple[int, int]:
        async with self._session_factory() as session:
            active = await ActiveDownloadRepository(session).delete_orphaned()
            waiters = await JobWaiterRepository(session).delete_orphaned()
            await session.commit()
        return active, waiters

    async def reclaim_stalled_jobs(self, *, older_than_seconds: float | None = None) -> int:
        async with self._session_factory() as session:
            reclaimed = await JobRepository(session).fail_stalled_inflight(
                older_than_seconds=older_than_seconds
            )
            await session.commit()
        return reclaimed
