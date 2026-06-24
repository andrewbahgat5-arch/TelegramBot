"""ActiveDownloadRepository (MASTER_PLAN 10.7)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from infrastructure.database.models import ActiveDownload
from infrastructure.database.repositories.base import SqlAlchemyRepository


class ActiveDownloadRepository(SqlAlchemyRepository[ActiveDownload]):
    model = ActiveDownload

    async def get_by_media_format_quality(
        self, media_id: int, format_: str, quality: str
    ) -> ActiveDownload | None:
        result = await self.session.execute(
            select(ActiveDownload).where(
                ActiveDownload.media_id == media_id,
                ActiveDownload.format == format_,
                ActiveDownload.quality == quality,
            )
        )
        return result.scalar_one_or_none()

    async def insert_if_absent(
        self, *, media_id: int, format_: str, quality: str, job_id: uuid.UUID
    ) -> bool:
        """Claim the (media, format, quality) slot. False means a duplicate is active.

        The ``uq_active_media_format_quality`` constraint serializes concurrent
        requests for the same content (16.1 T2 / fan-out trigger 16.4).
        """
        stmt = (
            pg_insert(ActiveDownload)
            .values(media_id=media_id, format=format_, quality=quality, job_id=job_id)
            .on_conflict_do_nothing(constraint="uq_active_media_format_quality")
            .returning(ActiveDownload.id)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one_or_none() is not None

    async def delete_by_job(self, job_id: uuid.UUID) -> int:
        result = await self.session.execute(
            delete(ActiveDownload).where(ActiveDownload.job_id == job_id)
        )
        await self.session.flush()
        return result.rowcount
