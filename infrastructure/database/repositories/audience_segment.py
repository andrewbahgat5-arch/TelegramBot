"""Audience-segment repositories (MASTER_PLAN Sprint 9.5, D-043)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import AudienceSegment, AudienceSegmentMember
from infrastructure.database.repositories.base import SqlAlchemyRepository


class AudienceSegmentRepository(SqlAlchemyRepository[AudienceSegment]):
    model = AudienceSegment

    async def create_segment(
        self, *, name: str, description: str | None, created_by: int
    ) -> AudienceSegment:
        segment = AudienceSegment(name=name, description=description, created_by=created_by)
        return await self.add(segment)

    async def get_by_name(self, name: str) -> AudienceSegment | None:
        result = await self.session.execute(
            select(AudienceSegment).where(AudienceSegment.name == name)
        )
        return result.scalar_one_or_none()

    async def list_all_segments(self) -> Sequence[AudienceSegment]:
        result = await self.session.execute(
            select(AudienceSegment).order_by(AudienceSegment.id.asc())
        )
        return result.scalars().all()


class AudienceSegmentMemberRepository:
    """``AudienceSegmentMemberProtocol`` — a join table, not a single-entity repository."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_member(self, *, segment_id: int, user_id: int) -> bool:
        stmt = (
            pg_insert(AudienceSegmentMember)
            .values(segment_id=segment_id, user_id=user_id)
            .on_conflict_do_nothing(index_elements=["segment_id", "user_id"])
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return bool(result.rowcount)

    async def remove_member(self, *, segment_id: int, user_id: int) -> bool:
        result = await self.session.execute(
            delete(AudienceSegmentMember).where(
                AudienceSegmentMember.segment_id == segment_id,
                AudienceSegmentMember.user_id == user_id,
            )
        )
        await self.session.flush()
        return bool(result.rowcount)

    async def list_segment_ids_for_user(self, user_id: int) -> set[int]:
        result = await self.session.execute(
            select(AudienceSegmentMember.segment_id).where(AudienceSegmentMember.user_id == user_id)
        )
        return set(result.scalars().all())

    async def count_members(self, segment_id: int) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(AudienceSegmentMember)
            .where(AudienceSegmentMember.segment_id == segment_id)
        )
        return int(result.scalar_one())
