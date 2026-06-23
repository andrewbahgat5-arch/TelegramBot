"""CachedFileRepository (MASTER_PLAN 10.4)."""

from __future__ import annotations

from sqlalchemy import select

from infrastructure.database.models import CachedFile
from infrastructure.database.repositories.base import SqlAlchemyRepository


class CachedFileRepository(SqlAlchemyRepository[CachedFile]):
    model = CachedFile

    async def get_by_media_format_quality(
        self, media_id: int, format_: str, quality: str
    ) -> CachedFile | None:
        result = await self.session.execute(
            select(CachedFile).where(
                CachedFile.media_id == media_id,
                CachedFile.format == format_,
                CachedFile.quality == quality,
            )
        )
        return result.scalar_one_or_none()
