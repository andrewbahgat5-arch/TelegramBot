"""AudienceExpressionRepository (Sprint 9.6, D-055).

CRUD for the unified ``audience_expressions`` + ``audience_rules`` tables: create an
expression, append rules, and read back ``(mode, rules)`` for evaluation. Used on the
write side by ``BroadcastService`` (and, later, the ad wizard) and on the read side by
the ``BroadcastWorker`` to page an audience.
"""

from __future__ import annotations

from sqlalchemy import select

from domain.entities.audience import AudienceRuleSpec
from infrastructure.database.models.audience_expression import AudienceExpression, AudienceRule
from infrastructure.database.repositories.base import SqlAlchemyRepository


class AudienceExpressionRepository(SqlAlchemyRepository[AudienceExpression]):
    model = AudienceExpression

    async def create(self, *, mode: str) -> AudienceExpression:
        return await self.add(AudienceExpression(mode=mode))

    async def add_rule(
        self, expression_id: int, *, effect: str, dimension: str, value: str
    ) -> AudienceRule:
        rule = AudienceRule(
            expression_id=expression_id, effect=effect, dimension=dimension, value=value
        )
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def get_rules(self, expression_id: int) -> tuple[str, list[AudienceRuleSpec]] | None:
        expression = await self.session.get(AudienceExpression, expression_id)
        if expression is None:
            return None
        result = await self.session.execute(
            select(AudienceRule).where(AudienceRule.expression_id == expression_id)
        )
        rules = [
            AudienceRuleSpec(effect=r.effect, dimension=r.dimension, value=r.value)
            for r in result.scalars().all()
        ]
        return expression.mode, rules
