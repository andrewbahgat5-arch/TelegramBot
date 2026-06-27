"""Integration: multi-placement dual-read + internal ad metadata (Sprint 9.6 C4).

Verifies ``AdRepository.list_active_for_placement`` reads the ``ad_placements`` join
table when present and falls back to the scalar ``placement`` column for legacy ads
(D-056), and that ``internal_name`` / ``internal_notes`` persist (D-058). Runs in the
rolled-back ``db_session``; auto-skips without Postgres.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import User
from infrastructure.database.repositories.advertisement import AdRepository

pytestmark = pytest.mark.asyncio


async def _make_owner(session: AsyncSession) -> User:
    user = User(telegram_id=860001, role="owner")
    session.add(user)
    await session.flush()
    return user


async def _new_ad(repo: AdRepository, created_by: int, **kw: object) -> object:
    return await repo.create_ad(
        title=kw.get("title", "ad"),  # type: ignore[arg-type]
        ad_type="text",
        content_text="hi",
        content_media_file_id=None,
        button_text=None,
        button_url=None,
        target_role=None,
        show_every_n_downloads=1,
        priority=0,
        created_by=created_by,
        placement=kw.get("placement", "post_download"),  # type: ignore[arg-type]
        internal_name=kw.get("internal_name"),  # type: ignore[arg-type]
        internal_notes=kw.get("internal_notes"),  # type: ignore[arg-type]
    )


async def test_legacy_ad_without_links_matches_by_scalar_column(db_session: AsyncSession) -> None:
    repo = AdRepository(db_session)
    owner = await _make_owner(db_session)
    ad = await _new_ad(repo, owner.id, placement="post_download")
    await db_session.flush()

    matched = {a.id for a in await repo.list_active_for_placement("post_download")}
    assert ad.id in matched  # dual-read fallback to the column


async def test_placement_rows_win_over_column(db_session: AsyncSession) -> None:
    repo = AdRepository(db_session)
    owner = await _make_owner(db_session)
    ad = await _new_ad(repo, owner.id, placement="post_download")
    await db_session.flush()

    await repo.set_placements(ad.id, ["video_delivery", "audio_delivery"])
    assert await repo.list_placements(ad.id) == ["audio_delivery", "video_delivery"]

    for placement in ("video_delivery", "audio_delivery"):
        assert ad.id in {a.id for a in await repo.list_active_for_placement(placement)}
    # Once explicit rows exist, the scalar column no longer matches.
    assert ad.id not in {a.id for a in await repo.list_active_for_placement("post_download")}


async def test_internal_metadata_persists(db_session: AsyncSession) -> None:
    repo = AdRepository(db_session)
    owner = await _make_owner(db_session)
    ad = await _new_ad(repo, owner.id, internal_name="Black Friday", internal_notes="VIP only")
    await db_session.flush()

    fresh = await repo.get_by_id(ad.id)
    assert fresh is not None
    assert fresh.internal_name == "Black Friday"
    assert fresh.internal_notes == "VIP only"
