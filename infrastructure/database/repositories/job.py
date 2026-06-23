"""JobRepository (MASTER_PLAN 10.6).

``jobs.id`` is an application-generated UUIDv7 (D-013); ``create`` therefore
accepts a pre-built ``Job`` whose ``id`` was assigned by ``core.uuid7``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from infrastructure.database.models import Job
from infrastructure.database.repositories.base import SqlAlchemyRepository


class JobRepository(SqlAlchemyRepository[Job]):
    model = Job

    async def get_by_uuid(self, job_id: uuid.UUID) -> Job | None:
        result = await self.session.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()
