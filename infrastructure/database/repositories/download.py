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
        result = await self.session.execute(
            select(func.count()).select_from(Download).where(Download.user_id == user_id)
        )
        return int(result.scalar_one())

    async def list_for_user(
        self,
        user_id: int,
        *,
        limit: int = 10,
        offset: int = 0,
        format_filter: str | None = None,
    ) -> Sequence[Download]:
        stmt = (
            select(Download)
            .where(Download.user_id == user_id)
        )
        if format_filter is not None:
            stmt = stmt.where(Download.format == format_filter)
        stmt = (
            stmt.order_by(Download.created_at.desc(), Download.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_for_user(self, download_id: int, user_id: int) -> Download | None:
        result = await self.session.execute(
            select(Download).where(Download.id == download_id, Download.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def count_by_format(self, user_id: int) -> dict[str, int]:
        result = await self.session.execute(
            select(Download.format, func.count())
            .select_from(Download)
            .where(Download.user_id == user_id)
            .group_by(Download.format)
        )
        return {str(fmt): int(cnt) for fmt, cnt in result.all()}

    async def count_by_platform(
        self, *, since: datetime.datetime | None = None
    ) -> list[tuple[str, int]]:
        stmt = select(Download.platform, func.count()).select_from(Download)
        if since is not None:
            stmt = stmt.where(Download.created_at >= since)
        stmt = stmt.group_by(Download.platform).order_by(func.count().desc())
        result = await self.session.execute(stmt)
        return [(str(platform), int(count)) for platform, count in result.all()]

    async def total_count(self, *, since: datetime.datetime | None = None) -> int:
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
        title: str | None = None,
        source_url: str | None = None,
        duration_seconds: int | None = None,
        size_bytes: int | None = None,
    ) -> Download:
        download = Download(
            user_id=user_id,
            cached_file_id=cached_file_id,
            platform=platform,
            format=format_,
            quality=quality,
            file_size=file_size,
            status=status,
            title=title,
            source_url=source_url,
            duration_seconds=duration_seconds,
            size_bytes=size_bytes,
        )
        return await self.add(download)
