"""MediaRepository (MASTER_PLAN 10.3)."""

from __future__ import annotations

from sqlalchemy import select

from infrastructure.database.models import MediaMetadata
from infrastructure.database.repositories.base import SqlAlchemyRepository


class MediaRepository(SqlAlchemyRepository[MediaMetadata]):
    model = MediaMetadata

    async def get_by_platform_video(self, platform: str, video_id: str) -> MediaMetadata | None:
        result = await self.session.execute(
            select(MediaMetadata).where(
                MediaMetadata.platform == platform,
                MediaMetadata.video_id == video_id,
            )
        )
        return result.scalar_one_or_none()
