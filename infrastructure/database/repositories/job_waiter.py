"""JobWaiterRepository (MASTER_PLAN 10.8, 12.4)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from infrastructure.database.models import JobWaiter
from infrastructure.database.repositories.base import SqlAlchemyRepository


class JobWaiterRepository(SqlAlchemyRepository[JobWaiter]):
    model = JobWaiter

    async def list_for_job(self, job_id: uuid.UUID) -> Sequence[JobWaiter]:
        result = await self.session.execute(select(JobWaiter).where(JobWaiter.job_id == job_id))
        return result.scalars().all()

    async def add_waiter(
        self, *, job_id: uuid.UUID, user_id: int, correlation_id: uuid.UUID | None
    ) -> bool:
        """Attach a user to a job at most once (uq_job_waiter); True if newly added."""
        stmt = (
            pg_insert(JobWaiter)
            .values(job_id=job_id, user_id=user_id, correlation_id=correlation_id)
            .on_conflict_do_nothing(constraint="uq_job_waiter")
            .returning(JobWaiter.id)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one_or_none() is not None

    async def delete_for_job(self, job_id: uuid.UUID) -> int:
        """Delete all waiters for a job in one statement; return rows removed."""
        result = await self.session.execute(delete(JobWaiter).where(JobWaiter.job_id == job_id))
        await self.session.flush()
        return result.rowcount
