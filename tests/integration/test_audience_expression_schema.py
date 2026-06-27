"""Integration: the unified audience-expression schema + backfill (Sprint 9.6 C2, D-055).

Verifies the ``audience_expressions`` / ``audience_rules`` tables and the nullable
``audience_expression_id`` FK on ``advertisements`` / ``broadcasts`` behave as designed
(cascade on expression delete, SET NULL on the owners), and that the migration's
``_backfill`` copies a legacy ``ad_audience_rules`` set into an equivalent expression.

Runs inside the rolled-back ``db_session`` transaction; auto-skips without Postgres.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import (
    AdAudienceRule,
    Advertisement,
    AudienceExpression,
    AudienceRule,
    User,
)

pytestmark = pytest.mark.asyncio

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "202606270001_unified_audience.py"
)


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("mig_unified_audience", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _make_user(session: AsyncSession, telegram_id: int) -> User:
    user = User(telegram_id=telegram_id, role="user")
    session.add(user)
    await session.flush()
    return user


async def test_expression_rules_roundtrip_and_cascade(db_session: AsyncSession) -> None:
    expr = AudienceExpression(mode="include")
    db_session.add(expr)
    await db_session.flush()
    db_session.add_all(
        [
            AudienceRule(
                expression_id=expr.id, effect="include", dimension="plan", value="premium"
            ),
            AudienceRule(expression_id=expr.id, effect="exclude", dimension="language", value="ar"),
        ]
    )
    await db_session.flush()

    count = await db_session.scalar(
        select(func.count()).select_from(AudienceRule).where(AudienceRule.expression_id == expr.id)
    )
    assert count == 2

    # ON DELETE CASCADE: deleting the expression removes its rules.
    await db_session.delete(expr)
    await db_session.flush()
    remaining = await db_session.scalar(
        select(func.count()).select_from(AudienceRule).where(AudienceRule.expression_id == expr.id)
    )
    assert remaining == 0


async def test_advertisement_fk_set_null_on_expression_delete(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, 880001)
    expr = AudienceExpression(mode="all")
    db_session.add(expr)
    await db_session.flush()
    ad = Advertisement(title="promo", created_by=user.id, audience_expression_id=expr.id)
    db_session.add(ad)
    await db_session.flush()
    assert ad.audience_expression_id == expr.id

    await db_session.delete(expr)
    await db_session.flush()
    await db_session.refresh(ad)
    assert ad.audience_expression_id is None  # SET NULL, ad survives


async def test_backfill_copies_legacy_rules_into_expression(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, 880002)
    ad = Advertisement(title="legacy", created_by=user.id, audience_mode="exclude")
    db_session.add(ad)
    await db_session.flush()
    db_session.add_all(
        [
            AdAudienceRule(
                advertisement_id=ad.id, effect="exclude", dimension="plan", value="premium"
            ),
            AdAudienceRule(
                advertisement_id=ad.id, effect="include", dimension="role", value="user"
            ),
        ]
    )
    await db_session.flush()

    migration = _load_migration()
    await db_session.run_sync(lambda sync_session: migration._backfill(sync_session))  # type: ignore[attr-defined]

    await db_session.refresh(ad)
    assert ad.audience_expression_id is not None
    expr = await db_session.get(AudienceExpression, ad.audience_expression_id)
    assert expr is not None and expr.mode == "exclude"  # mode carried from the ad

    rules = (
        await db_session.scalars(
            select(AudienceRule)
            .where(AudienceRule.expression_id == expr.id)
            .order_by(AudienceRule.dimension)
        )
    ).all()
    copied = {(r.effect, r.dimension, r.value) for r in rules}
    assert copied == {("exclude", "plan", "premium"), ("include", "role", "user")}
