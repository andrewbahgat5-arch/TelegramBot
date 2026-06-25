"""AdAudienceRuleRepository (MASTER_PLAN Sprint 9.5, D-043)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select

from infrastructure.database.models import AdAudienceRule
from infrastructure.database.repositories.base import SqlAlchemyRepository


class AdAudienceRuleRepository(SqlAlchemyRepository[AdAudienceRule]):
    model = AdAudienceRule

    async def list_for_ad(self, ad_id: int) -> Sequence[AdAudienceRule]:
        result = await self.session.execute(
            select(AdAudienceRule)
            .where(AdAudienceRule.advertisement_id == ad_id)
            .order_by(AdAudienceRule.id.asc())
        )
        return result.scalars().all()

    async def create_rule(
        self, *, advertisement_id: int, effect: str, dimension: str, value: str
    ) -> AdAudienceRule:
        rule = AdAudienceRule(
            advertisement_id=advertisement_id, effect=effect, dimension=dimension, value=value
        )
        return await self.add(rule)

    async def delete_for_ad(self, ad_id: int) -> int:
        result = await self.session.execute(
            delete(AdAudienceRule).where(AdAudienceRule.advertisement_id == ad_id)
        )
        await self.session.flush()
        return result.rowcount or 0
