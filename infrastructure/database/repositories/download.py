"""DownloadRepository (MASTER_PLAN 10.5, partitioned)."""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from sqlalchemy import func, select

from infrastructure.database.models import Download
from infrastructure.database.repositories.base import SqlAlchemyRepository


class DownloadRepository(SqlAlchemyRepository[Download]):
    model = Download

    async def count_for_user(self, user_id: int) -> int:
        """Total lifetime history rows for a user (admin User Info, Sprint 9.6)."""
        result = await self.session.execute(
            select(func.count()).select_from(Download).where(Download.user_id == user_id)
        )
        return int(result.scalar_one())

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

    async def count_by_platform(
        self, *, since: datetime.datetime | None = None
    ) -> list[tuple[str, int]]:
        """``(platform, count)`` pairs, most downloads first (Sprint 13.3 analytics).

        Optionally restricted to rows created at/after ``since`` (a period filter).
        """
        stmt = select(Download.platform, func.count()).select_from(Download)
        if since is not None:
            stmt = stmt.where(Download.created_at >= since)
        stmt = stmt.group_by(Download.platform).order_by(func.count().desc())
        result = await self.session.execute(stmt)
        return [(str(platform), int(count)) for platform, count in result.all()]

    async def total_count(self, *, since: datetime.datetime | None = None) -> int:
        """Total download rows, optionally restricted to ``since`` (Sprint 13.3)."""
        stmt = select(func.count()).select_from(Download)
        if since is not None:
            stmt = stmt.where(Download.created_at >= since)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

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
