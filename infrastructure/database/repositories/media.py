"""MediaRepository (MASTER_PLAN 10.3, D-011)."""

from __future__ import annotations

import datetime
from typing import Any

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

    async def upsert_metadata(
        self,
        *,
        platform: str,
        video_id: str,
        title: str,
        source_url: str,
        duration: int | None = None,
        thumbnail_url: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> MediaMetadata:
        """Insert or merge a ``media_metadata`` row (D-011: COALESCE merge).

        On update, ``metadata_json`` is merged so a thinner re-extraction never
        clobbers a richer prior one — existing keys win, new keys are added.
        Scalar fields are only filled when currently absent.
        """
        row = await self.get_by_platform_video(platform, video_id)
        if row is None:
            return await self.add(
                MediaMetadata(
                    platform=platform,
                    video_id=video_id,
                    title=title,
                    source_url=source_url,
                    duration=duration,
                    thumbnail_url=thumbnail_url,
                    metadata_json=metadata_json,
                )
            )
        if duration is not None and row.duration is None:
            row.duration = duration
        if thumbnail_url is not None and row.thumbnail_url is None:
            row.thumbnail_url = thumbnail_url
        # COALESCE merge: existing (richer) values take precedence over the new blob.
        row.metadata_json = {**(metadata_json or {}), **(row.metadata_json or {})}
        row.updated_at = datetime.datetime.now(datetime.UTC)
        await self.session.flush()
        return row
