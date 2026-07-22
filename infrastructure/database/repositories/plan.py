"""PlanRepository (VERSION_2_MASTER_PLAN §5.1)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from infrastructure.database.models import Plan
from infrastructure.database.repositories.base import SqlAlchemyRepository


class PlanRepository(SqlAlchemyRepository[Plan]):
    model = Plan

    async def list_all(self) -> Sequence[Plan]:
        """Every plan row, ordered by ``sort_order`` (for the startup load + validation)."""
        result = await self.session.execute(select(Plan).order_by(Plan.sort_order, Plan.id))
        return result.scalars().all()

    async def get_by_code(self, code: str) -> Plan | None:
        result = await self.session.execute(select(Plan).where(Plan.code == code).limit(1))
        return result.scalar_one_or_none()
