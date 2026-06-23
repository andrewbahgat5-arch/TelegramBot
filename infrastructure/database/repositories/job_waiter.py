"""JobWaiterRepository (MASTER_PLAN 10.8, 12.4)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select

from infrastructure.database.models import JobWaiter
from infrastructure.database.repositories.base import SqlAlchemyRepository


class JobWaiterRepository(SqlAlchemyRepository[JobWaiter]):
    model = JobWaiter

    async def list_for_job(self, job_id: uuid.UUID) -> Sequence[JobWaiter]:
        result = await self.session.execute(select(JobWaiter).where(JobWaiter.job_id == job_id))
        return result.scalars().all()

    async def delete_for_job(self, job_id: uuid.UUID) -> int:
        """Delete all waiters for a job in one statement; return rows removed."""
        result = await self.session.execute(delete(JobWaiter).where(JobWaiter.job_id == job_id))
        await self.session.flush()
        return result.rowcount
