"""CachedFileRepository (MASTER_PLAN 10.4)."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

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

    async def upsert(
        self,
        *,
        media_id: int,
        format_: str,
        quality: str,
        telegram_file_id: str,
        telegram_unique_file_id: str,
        file_size: int | None,
    ) -> CachedFile:
        """UPSERT keyed on the unique ``(media_id, format, quality)`` (10.4, 16.1 W5).

        Idempotent: a re-processed job refreshes the file ids and bumps usage.
        """
        stmt = (
            pg_insert(CachedFile)
            .values(
                media_id=media_id,
                format=format_,
                quality=quality,
                telegram_file_id=telegram_file_id,
                telegram_unique_file_id=telegram_unique_file_id,
                file_size=file_size,
                usage_count=1,
                last_used_at=func.now(),
            )
            .on_conflict_do_update(
                constraint="uq_cached_media_format_quality",
                set_={
                    "telegram_file_id": telegram_file_id,
                    "telegram_unique_file_id": telegram_unique_file_id,
                    "file_size": file_size,
                    "usage_count": CachedFile.usage_count + 1,
                    "last_used_at": func.now(),
                },
            )
            .returning(CachedFile)
            # On conflict the row may already be in the identity map (e.g. a retry in
            # the same session); populate_existing refreshes it from the RETURNING
            # values so the caller sees the new file_id / usage_count, not a stale copy.
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one()

    async def bump_usage(self, cached_file_id: int) -> None:
        """Cache-hit accounting: usage_count += 1, last_used_at = NOW() (16.2)."""
        await self.session.execute(
            update(CachedFile)
            .where(CachedFile.id == cached_file_id)
            .values(usage_count=CachedFile.usage_count + 1, last_used_at=func.now())
        )
        await self.session.flush()
