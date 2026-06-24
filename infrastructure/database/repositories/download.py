"""DownloadRepository (MASTER_PLAN 10.5, partitioned)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from infrastructure.database.models import Download
from infrastructure.database.repositories.base import SqlAlchemyRepository


class DownloadRepository(SqlAlchemyRepository[Download]):
    model = Download

    async def list_for_user(
        self, user_id: int, *, limit: int = 10, offset: int = 0
    ) -> Sequence[Download]:
        """Paginated history, newest first (uses ix_downloads_user_created).

        ``id`` breaks ``created_at`` ties so the order is total and stable — rows
        created in the same transaction share ``now()``, and a non-deterministic tie
        order would let a row skip or repeat across pages.
        """
        result = await self.session.execute(
            select(Download)
            .where(Download.user_id == user_id)
            .order_by(Download.created_at.desc(), Download.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_for_user(self, download_id: int, user_id: int) -> Download | None:
        """One history row by id, scoped to its owner — never another user's (16.3)."""
        result = await self.session.execute(
            select(Download).where(Download.id == download_id, Download.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_completed(
        self,
        *,
        user_id: int,
        cached_file_id: int | None,
        platform: str,
        format_: str,
        quality: str,
        file_size: int | None,
        status: str = "completed",
    ) -> Download:
        """Insert a denormalized history row for a delivered download (10.5, 16.1 W7)."""
        download = Download(
            user_id=user_id,
            cached_file_id=cached_file_id,
            platform=platform,
            format=format_,
            quality=quality,
            file_size=file_size,
            status=status,
        )
        return await self.add(download)
