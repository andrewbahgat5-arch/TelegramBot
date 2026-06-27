"""Integration: the SQL audience compiler ≡ the Python matcher (design invariant #17).

Seeds the shared truth-table users (``tests/audience_cases.py``) in Postgres, then for
every scenario asserts that the set selected by ``compile_audience_predicate`` (SQL)
equals the set selected by ``evaluate_audience`` (Python) — and both equal the hand-
computed ``expected_keys``. Runs inside the rolled-back ``db_session`` transaction; the
suite auto-skips when Postgres is unavailable (see ``tests/integration/conftest.py``).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.audience import AudienceRuleSpec
from domain.enums import AudienceDimension, AudienceEffect, AudienceMode
from infrastructure.database.audience_query import compile_audience_predicate
from infrastructure.database.models import User
from infrastructure.database.models.audience_segment import (
    AudienceSegment,
    AudienceSegmentMember,
)
from infrastructure.database.repositories.user import UserRepository
from services.audience_service import evaluate_audience
from tests.audience_cases import NOW, SCENARIOS, USERS, Scenario, ctx_for

pytestmark = pytest.mark.asyncio

_TIDS = [u.telegram_id for u in USERS]


async def _seed(session: AsyncSession) -> dict[str, User]:
    rows: dict[str, User] = {}
    for attrs in USERS:
        row = User(
            telegram_id=attrs.telegram_id,
            username=None,
            first_name=None,
            language=attrs.language,
            role=attrs.role,
            is_premium=attrs.is_premium,
            premium_expires_at=attrs.premium_expires_at,
        )
        session.add(row)
        rows[attrs.key] = row
    await session.flush()
    return rows


async def _sql_selected(
    session: AsyncSession, scenario_mode: str, rules: list[AudienceRuleSpec]
) -> set[int]:
    predicate = compile_audience_predicate(scenario_mode, rules, now=NOW)
    result = await session.execute(
        select(User.telegram_id).where(predicate, User.telegram_id.in_(_TIDS))
    )
    return set(result.scalars().all())


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
async def test_sql_compiler_matches_python_evaluator(
    db_session: AsyncSession, scenario: Scenario
) -> None:
    await _seed(db_session)
    rules = list(scenario.rules)

    python_keys = {
        u.key for u in USERS if evaluate_audience(scenario.mode, rules, ctx_for(u, NOW), set())
    }
    sql_tids = await _sql_selected(db_session, scenario.mode, rules)
    sql_keys = {u.key for u in USERS if u.telegram_id in sql_tids}

    assert sql_keys == python_keys, f"SQL/Python drift in {scenario.name}"
    assert sql_keys == set(scenario.expected_keys)


async def test_segment_rule_selects_segment_members(db_session: AsyncSession) -> None:
    rows = await _seed(db_session)
    segment = AudienceSegment(
        name=f"truthtable-{uuid.uuid4().hex[:8]}",
        description=None,
        created_by=rows["owner"].id,
    )
    db_session.add(segment)
    await db_session.flush()
    members = {"prem_en", "free_ar"}
    for key in members:
        db_session.add(AudienceSegmentMember(segment_id=segment.id, user_id=rows[key].id))
    await db_session.flush()

    rule = AudienceRuleSpec(
        AudienceEffect.INCLUDE.value, AudienceDimension.SEGMENT.value, str(segment.id)
    )
    sql_tids = await _sql_selected(db_session, AudienceMode.INCLUDE.value, [rule])
    sql_keys = {u.key for u in USERS if u.telegram_id in sql_tids}
    assert sql_keys == members


async def test_broadcast_guards_exclude_banned_and_staff(db_session: AsyncSession) -> None:
    """`page_for_audience` never returns banned users, and excludes staff unless named."""
    seeded = {
        "free": User(telegram_id=870001, role="user", is_premium=False, language="en"),
        "prem": User(telegram_id=870002, role="user", is_premium=True, language="en"),
        "mod": User(telegram_id=870003, role="moderator", is_premium=False, language="en"),
        "owner": User(telegram_id=870004, role="owner", is_premium=True, language="en"),
        "banned": User(
            telegram_id=870005, role="user", is_premium=False, is_banned=True, language="en"
        ),
    }
    db_session.add_all(list(seeded.values()))
    await db_session.flush()
    mine = {u.telegram_id for u in seeded.values()}
    repo = UserRepository(db_session)

    async def selected(mode: str, rules: list[AudienceRuleSpec]) -> set[int]:
        page = await repo.page_for_audience(
            after_id=0, limit=10_000, mode=mode, rules=rules, now=NOW
        )
        return {u.telegram_id for u in page} & mine

    # mode=all, no rules: non-banned, non-staff only.
    assert await selected(AudienceMode.ALL.value, []) == {
        seeded["free"].telegram_id,
        seeded["prem"].telegram_id,
    }
    # An explicit include role=moderator lets that staff role through (and only it).
    moderator_rule = [
        AudienceRuleSpec(AudienceEffect.INCLUDE.value, AudienceDimension.ROLE.value, "moderator")
    ]
    assert await selected(AudienceMode.INCLUDE.value, moderator_rule) == {seeded["mod"].telegram_id}
