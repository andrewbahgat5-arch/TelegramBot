"""ActiveDownloadRepository (MASTER_PLAN 10.7)."""

from __future__ import annotations

from sqlalchemy import select

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
